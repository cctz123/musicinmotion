"""Motion Sensor Fusion Layer - MediaPipe + Dual IMUs.

This module extracts and fuses motion features from MediaPipe pose detection
and IMU sensors into a normalized MotionState representation.
"""

import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from collections import deque


@dataclass
class MotionState:
    """Normalized motion state (all values [0,1])."""
    # Pose features (MediaPipe-derived)
    hand_height_L: float = 0.5
    hand_height_R: float = 0.5
    arm_extension_L: float = 0.5
    arm_extension_R: float = 0.5
    elbow_bend_L: float = 0.5
    elbow_bend_R: float = 0.5
    hand_spread: float = 0.5
    lateral_offset_L: float = 0.5
    lateral_offset_R: float = 0.5
    
    # Dynamics features (IMU-derived)
    activity_L: float = 0.0
    activity_R: float = 0.0
    activity_global: float = 0.0
    jerk_L: float = 0.0
    jerk_R: float = 0.0
    shake_energy_L: float = 0.0
    shake_energy_R: float = 0.0
    
    # Confidence values
    mediapipe_confidence: float = 0.0
    imu_confidence_L: float = 0.0
    imu_confidence_R: float = 0.0


class HighPassFilter:
    """One-pole high-pass filter for gravity removal."""
    
    def __init__(self, cutoff_hz: float, sample_rate: float):
        self.cutoff_hz = cutoff_hz
        self.sample_rate = sample_rate
        self.alpha = 1.0 / (1.0 + 2.0 * math.pi * cutoff_hz / sample_rate)
        self.prev_input = 0.0
        self.prev_output = 0.0
    
    def process(self, value: float) -> float:
        """Process a single sample."""
        output = self.alpha * (self.prev_output + value - self.prev_input)
        self.prev_input = value
        self.prev_output = output
        return output
    
    def reset(self):
        """Reset filter state."""
        self.prev_input = 0.0
        self.prev_output = 0.0


class BandpassFilter:
    """Simple bandpass (high-pass + low-pass) for shake detection."""
    
    def __init__(self, low_cutoff: float, high_cutoff: float, sample_rate: float):
        self.low_cutoff = low_cutoff
        self.high_cutoff = high_cutoff
        self.sample_rate = sample_rate
        # One-pole filters
        self.hp_alpha = 1.0 / (1.0 + 2.0 * math.pi * low_cutoff / sample_rate)
        self.lp_alpha = 2.0 * math.pi * high_cutoff / sample_rate
        self.hp_state = 0.0
        self.lp_state = 0.0
        self.hp_prev = 0.0
    
    def process(self, value: float) -> float:
        """Process a single sample."""
        # High-pass
        hp_out = self.hp_alpha * (self.hp_state + value - self.hp_prev)
        self.hp_prev = value
        self.hp_state = hp_out
        
        # Low-pass
        self.lp_state += self.lp_alpha * (hp_out - self.lp_state)
        return self.lp_state
    
    def reset(self):
        """Reset filter state."""
        self.hp_state = 0.0
        self.lp_state = 0.0
        self.hp_prev = 0.0


class TwoStageSmoother:
    """Two-stage smoothing: median-of-3 + two-speed one-pole."""
    
    def __init__(self, tau_up_ms=50.0, tau_down_ms=200.0, fps=30.0):
        self.tau_up_ms = tau_up_ms
        self.tau_down_ms = tau_down_ms
        self.dt = 1.0 / fps
        self.history = deque(maxlen=3)  # Median window
        self.smoothed = 0.5  # Initial value
    
    def update(self, new_value: float) -> float:
        """Update with new value, return smoothed result."""
        # Stage 1: Median-of-3
        self.history.append(new_value)
        if len(self.history) == 3:
            median_value = sorted(self.history)[1]
        else:
            median_value = new_value
        
        # Stage 2: Two-speed one-pole
        tau_ms = self.tau_up_ms if median_value > self.smoothed else self.tau_down_ms
        tau = tau_ms / 1000.0
        alpha = 1.0 - math.exp(-self.dt / max(tau, 1e-6))
        self.smoothed = self.smoothed + alpha * (median_value - self.smoothed)
        
        return self.smoothed
    
    def reset(self, value: float = 0.5):
        """Reset smoother to a specific value."""
        self.history.clear()
        self.smoothed = value


class ConfidenceWeightedValue:
    """Handles confidence-weighted return-to-neutral."""
    
    def __init__(self, neutral_value=0.5, grace_period_s=0.2, decay_time_s=1.0):
        self.neutral_value = neutral_value
        self.grace_period_s = grace_period_s
        self.decay_time_s = decay_time_s
        self.last_good_value = neutral_value
        self.last_good_time = 0.0
    
    def update(self, new_value: float, confidence: float, current_time: float) -> float:
        """Update value with confidence weighting."""
        if confidence > 0.5:  # Good detection
            self.last_good_value = new_value
            self.last_good_time = current_time
            return new_value
        else:  # Low confidence
            time_since_good = current_time - self.last_good_time
            
            if time_since_good < self.grace_period_s:
                # Grace period: use last good value
                return self.last_good_value
            else:
                # Decay to neutral
                decay_progress = min(1.0, 
                    (time_since_good - self.grace_period_s) / self.decay_time_s)
                return (self.last_good_value + 
                       (self.neutral_value - self.last_good_value) * decay_progress)
    
    def reset(self, value: float = 0.5):
        """Reset to a specific value."""
        self.last_good_value = value
        self.last_good_time = time.time()


class MotionFeatureExtractor:
    """Extracts and fuses MediaPipe + IMU features into MotionState."""
    
    def __init__(self, fps=30.0):
        self.fps = fps
        self.dt = 1.0 / fps
        
        # MediaPipe state
        self.mp_pose_module = None  # MediaPipe pose module (for PoseLandmark enum)
        self.mp_drawing = None
        self.pose_detector = None  # MediaPipe Pose instance
        
        # IMU readers
        self.imu_reader_L = None  # Left IMU
        self.imu_reader_R = None  # Right IMU
        
        # IMU filters and state
        self.hp_filters_L = [HighPassFilter(0.5, 100.0) for _ in range(3)]
        self.hp_filters_R = [HighPassFilter(0.5, 100.0) for _ in range(3)]
        self.bandpass_L = BandpassFilter(3.0, 10.0, 100.0)
        self.bandpass_R = BandpassFilter(3.0, 10.0, 100.0)
        
        # Smoothing for each feature
        self.smoothers = {}  # Dict[str, TwoStageSmoother]
        self.confidence_handlers = {}  # Dict[str, ConfidenceWeightedValue]
        
        # Initialize smoothers for all pose features
        pose_features = [
            'hand_height_L', 'hand_height_R',
            'arm_extension_L', 'arm_extension_R',
            'elbow_bend_L', 'elbow_bend_R',
            'hand_spread', 'lateral_offset_L', 'lateral_offset_R'
        ]
        for feature in pose_features:
            self.smoothers[feature] = TwoStageSmoother(tau_up_ms=50.0, tau_down_ms=200.0, fps=fps)
            self.confidence_handlers[feature] = ConfidenceWeightedValue(
                neutral_value=0.5, grace_period_s=0.2, decay_time_s=1.0
            )
        
        # Initialize smoothers for dynamics features
        dynamics_features = [
            'activity_L', 'activity_R', 'activity_global',
            'jerk_L', 'jerk_R',
            'shake_energy_L', 'shake_energy_R'
        ]
        for feature in dynamics_features:
            self.smoothers[feature] = TwoStageSmoother(tau_up_ms=50.0, tau_down_ms=200.0, fps=fps)
            self.confidence_handlers[feature] = ConfidenceWeightedValue(
                neutral_value=0.0, grace_period_s=0.2, decay_time_s=1.0
            )
        
        # History for calculations
        self.accel_mag_history_L = deque(maxlen=30)
        self.accel_mag_history_R = deque(maxlen=30)
        self.prev_accel_mag_L = 0.0
        self.prev_accel_mag_R = 0.0
        self.last_imu_time_L = 0.0
        self.last_imu_time_R = 0.0
        
        # Current state
        self.motion_state = MotionState()
    
    def initialize_mediapipe(self, mp_pose_module, mp_drawing, pose_detector):
        """Initialize MediaPipe pose detector.
        
        Args:
            mp_pose_module: MediaPipe pose module (for PoseLandmark enum)
            mp_drawing: MediaPipe drawing utilities
            pose_detector: MediaPipe Pose instance (for processing frames)
        """
        self.mp_pose_module = mp_pose_module
        self.mp_drawing = mp_drawing
        self.pose_detector = pose_detector
    
    def initialize_imu(self, imu_reader_L, imu_reader_R=None):
        """Initialize IMU readers."""
        self.imu_reader_L = imu_reader_L
        self.imu_reader_R = imu_reader_R
    
    def update(self, frame_rgb, current_time: float) -> MotionState:
        """Update motion state from MediaPipe frame and IMU data."""
        # 1. Extract MediaPipe features
        mp_features = self._extract_mediapipe_features(frame_rgb, current_time)
        
        # 2. Extract IMU features (single device in AP mode → same sample for both L and R)
        if self.imu_reader_L is not None and self.imu_reader_L is self.imu_reader_R:
            imu_features_L = self._extract_imu_features('L', current_time)
            imu_features_R = imu_features_L
        else:
            imu_features_L = self._extract_imu_features('L', current_time)
            imu_features_R = self._extract_imu_features('R', current_time)
        
        # 3. Fuse features into MotionState
        self.motion_state = self._fuse_features(
            mp_features, imu_features_L, imu_features_R, current_time
        )
        
        return self.motion_state
    
    def _calculate_shoulder_width(self, landmarks):
        """Calculate shoulder width for normalization."""
        if not landmarks:
            return 0.01
        
        left_shoulder = landmarks[self.mp_pose_module.PoseLandmark.LEFT_SHOULDER]
        right_shoulder = landmarks[self.mp_pose_module.PoseLandmark.RIGHT_SHOULDER]
        dx = right_shoulder.x - left_shoulder.x
        dy = right_shoulder.y - left_shoulder.y
        width = math.sqrt(dx*dx + dy*dy)
        return max(width, 0.01)  # Epsilon to avoid division by zero
    
    def _calculate_torso_center(self, landmarks) -> Tuple[float, float]:
        """Calculate torso center (midpoint of shoulders and hips)."""
        if not landmarks:
            return (0.5, 0.5)  # Default center
        
        left_shoulder = landmarks[self.mp_pose_module.PoseLandmark.LEFT_SHOULDER]
        right_shoulder = landmarks[self.mp_pose_module.PoseLandmark.RIGHT_SHOULDER]
        left_hip = landmarks[self.mp_pose_module.PoseLandmark.LEFT_HIP]
        right_hip = landmarks[self.mp_pose_module.PoseLandmark.RIGHT_HIP]
        
        mid_shoulders = ((left_shoulder.x + right_shoulder.x) / 2,
                         (left_shoulder.y + right_shoulder.y) / 2)
        mid_hips = ((left_hip.x + right_hip.x) / 2,
                    (left_hip.y + right_hip.y) / 2)
        
        return ((mid_shoulders[0] + mid_hips[0]) / 2,
                (mid_shoulders[1] + mid_hips[1]) / 2)
    
    def _calculate_arm_extension(self, wrist, shoulder, shoulder_width):
        """Calculate arm extension (0=close, 1=fully extended)."""
        dx = wrist.x - shoulder.x
        dy = wrist.y - shoulder.y
        d = math.sqrt(dx*dx + dy*dy)
        ext_raw = d / shoulder_width
        ext = max(0.0, min(1.0, (ext_raw - 0.6) / (2.2 - 0.6)))
        return ext
    
    def _calculate_elbow_bend(self, shoulder, elbow, wrist):
        """Calculate elbow bend (0=straight, 1=strongly bent)."""
        # Vectors from elbow
        ux = shoulder.x - elbow.x
        uy = shoulder.y - elbow.y
        vx = wrist.x - elbow.x
        vy = wrist.y - elbow.y
        
        # Dot product and magnitudes
        dot = ux*vx + uy*vy
        mag_u = math.sqrt(ux*ux + uy*uy)
        mag_v = math.sqrt(vx*vx + vy*vy)
        
        if mag_u < 0.001 or mag_v < 0.001:
            return 0.5  # Default if vectors too small
        
        cos_theta = max(-1.0, min(1.0, dot / (mag_u * mag_v)))
        theta_rad = math.acos(cos_theta)
        theta_deg = math.degrees(theta_rad)
        
        # Normalize: 170° (straight) → 0, 60° (bent) → 1
        bend = max(0.0, min(1.0, (170.0 - theta_deg) / (170.0 - 60.0)))
        return bend
    
    def _calculate_lateral_offset(self, wrist, torso_center, shoulder_width):
        """Calculate lateral offset (0.5=center, 0=left, 1=right)."""
        dx = wrist.x - torso_center[0]
        offset = dx / shoulder_width
        offset_clamped = max(-1.0, min(1.0, offset))
        offset01 = 0.5 + 0.5 * offset_clamped
        return offset01
    
    def _calculate_mediapipe_confidence(self, landmarks):
        """Calculate aggregate MediaPipe confidence."""
        if not landmarks:
            return 0.0
        
        key_landmarks = [
            self.mp_pose_module.PoseLandmark.LEFT_WRIST,
            self.mp_pose_module.PoseLandmark.RIGHT_WRIST,
            self.mp_pose_module.PoseLandmark.LEFT_SHOULDER,
            self.mp_pose_module.PoseLandmark.RIGHT_SHOULDER,
            self.mp_pose_module.PoseLandmark.LEFT_ELBOW,
            self.mp_pose_module.PoseLandmark.RIGHT_ELBOW,
            self.mp_pose_module.PoseLandmark.LEFT_HIP,
            self.mp_pose_module.PoseLandmark.RIGHT_HIP,
        ]
        
        visibilities = []
        for landmark_idx in key_landmarks:
            landmark = landmarks[landmark_idx]
            if hasattr(landmark, 'visibility'):
                visibilities.append(landmark.visibility)
        
        return sum(visibilities) / len(visibilities) if visibilities else 0.0
    
    def _calculate_hand_height(self, wrist, landmarks):
        """Calculate hand height (0=hip, 1=head)."""
        if not landmarks:
            return 0.5
        
        left_shoulder = landmarks[self.mp_pose_module.PoseLandmark.LEFT_SHOULDER]
        right_shoulder = landmarks[self.mp_pose_module.PoseLandmark.RIGHT_SHOULDER]
        left_hip = landmarks[self.mp_pose_module.PoseLandmark.LEFT_HIP]
        right_hip = landmarks[self.mp_pose_module.PoseLandmark.RIGHT_HIP]
        
        head_y = (left_shoulder.y + right_shoulder.y) / 2
        hip_y = (left_hip.y + right_hip.y) / 2
        
        if abs(hip_y - head_y) < 0.001:
            return 0.5
        
        # Normalized height (inverted because y increases downward)
        hand_height = max(0.0, min(1.0, (hip_y - wrist.y) / (hip_y - head_y)))
        return hand_height
    
    def _calculate_hand_spread(self, left_wrist, right_wrist, shoulder_width):
        """Calculate hand spread (distance between wrists / shoulder width)."""
        dx = right_wrist.x - left_wrist.x
        dy = right_wrist.y - left_wrist.y
        d = math.sqrt(dx*dx + dy*dy)
        spread = d / shoulder_width
        # Clamp to reasonable upper bound
        return min(spread, 3.0) / 3.0  # Normalize to [0,1]
    
    def _calculate_accel_magnitude(self, accel_g, hp_filters):
        """Calculate high-passed acceleration magnitude."""
        # Apply high-pass filter to each component
        ax_hp = hp_filters[0].process(accel_g[0])
        ay_hp = hp_filters[1].process(accel_g[1])
        az_hp = hp_filters[2].process(accel_g[2])
        
        # Magnitude
        mag = math.sqrt(ax_hp*ax_hp + ay_hp*ay_hp + az_hp*az_hp)
        
        # Normalize: 0.5g (rest) to 3.0g (fast)
        normalized = max(0.0, min(1.0, (mag - 0.5) / (3.0 - 0.5)))
        return normalized
    
    def _calculate_gyro_magnitude(self, gyro_dps):
        """Calculate angular velocity magnitude."""
        gx, gy, gz = gyro_dps
        mag = math.sqrt(gx*gx + gy*gy + gz*gz)
        
        # Normalize: 0 deg/s (rest) to 2000 deg/s (max)
        normalized = max(0.0, min(1.0, mag / 2000.0))
        return normalized
    
    def _calculate_jerk(self, accel_mag_current, accel_mag_previous, dt):
        """Calculate jerk (rate of change of acceleration)."""
        if dt < 0.001:  # Avoid division by zero
            return 0.0
        
        jerk = abs(accel_mag_current - accel_mag_previous) / dt
        
        # Normalize: 0 g/s to 50 g/s
        normalized = max(0.0, min(1.0, jerk / 50.0))
        return normalized
    
    def _calculate_shake_energy(self, accel_mag_history, bandpass_filter):
        """Calculate RMS energy in shake band."""
        if len(accel_mag_history) < 10:
            return 0.0
        
        # Apply bandpass and compute RMS
        filtered_samples = []
        for mag in list(accel_mag_history)[-30:]:
            filtered_samples.append(bandpass_filter.process(mag))
        
        if not filtered_samples:
            return 0.0
        
        rms = math.sqrt(sum(x*x for x in filtered_samples) / len(filtered_samples))
        
        # Normalize (empirical: max RMS ≈ 0.5g in shake band)
        normalized = max(0.0, min(1.0, rms / 0.5))
        return normalized
    
    def _calculate_activity_scalar(self, accel_norm, gyro_norm):
        """Weighted blend of acceleration and gyro energy."""
        # Weighted blend: 60% accel, 40% gyro
        activity = 0.6 * accel_norm + 0.4 * gyro_norm
        
        # Already normalized (both inputs are [0,1])
        return max(0.0, min(1.0, activity))
    
    def _calculate_imu_confidence(self, last_sample_time, current_time, max_age_seconds=0.5):
        """Calculate IMU confidence based on data freshness."""
        if last_sample_time == 0.0:
            return 0.0
        
        age = current_time - last_sample_time
        if age > max_age_seconds:
            return 0.0
        # Linear decay from 1.0 to 0.0 over max_age_seconds
        return max(0.0, 1.0 - (age / max_age_seconds))
    
    def _extract_mediapipe_features(self, frame_rgb, current_time):
        """Extract MediaPipe pose features."""
        features = {
            'hand_height_L': 0.5,
            'hand_height_R': 0.5,
            'arm_extension_L': 0.5,
            'arm_extension_R': 0.5,
            'elbow_bend_L': 0.5,
            'elbow_bend_R': 0.5,
            'hand_spread': 0.5,
            'lateral_offset_L': 0.5,
            'lateral_offset_R': 0.5,
            'confidence': 0.0
        }
        
        if not self.pose_detector:
            return features
        
        results = self.pose_detector.process(frame_rgb)
        
        if not results.pose_landmarks:
            return features
        
        landmarks = results.pose_landmarks.landmark
        
        # Calculate common values
        shoulder_width = self._calculate_shoulder_width(landmarks)
        torso_center = self._calculate_torso_center(landmarks)
        confidence = self._calculate_mediapipe_confidence(landmarks)
        
        features['confidence'] = confidence
        
        # Sensor L/R = user's left/right. Use MediaPipe left/right as-is so that
        # hand_height_L responds to the user's left hand, hand_height_R to the right.
        # (If your left hand drives R, the frame may be unmirrored at pose time; we can swap here if needed.)
        
        # Left side features (MediaPipe LEFT_* = image left → user left when display is mirrored)
        left_wrist = landmarks[self.mp_pose_module.PoseLandmark.LEFT_WRIST]
        left_shoulder = landmarks[self.mp_pose_module.PoseLandmark.LEFT_SHOULDER]
        left_elbow = landmarks[self.mp_pose_module.PoseLandmark.LEFT_ELBOW]
        
        features['hand_height_L'] = self._calculate_hand_height(left_wrist, landmarks)
        features['arm_extension_L'] = self._calculate_arm_extension(
            left_wrist, left_shoulder, shoulder_width
        )
        features['elbow_bend_L'] = self._calculate_elbow_bend(
            left_shoulder, left_elbow, left_wrist
        )
        features['lateral_offset_L'] = self._calculate_lateral_offset(
            left_wrist, torso_center, shoulder_width
        )
        
        # Right side features (MediaPipe RIGHT_* = image right → user right when display is mirrored)
        right_wrist = landmarks[self.mp_pose_module.PoseLandmark.RIGHT_WRIST]
        right_shoulder = landmarks[self.mp_pose_module.PoseLandmark.RIGHT_SHOULDER]
        right_elbow = landmarks[self.mp_pose_module.PoseLandmark.RIGHT_ELBOW]
        
        features['hand_height_R'] = self._calculate_hand_height(right_wrist, landmarks)
        features['arm_extension_R'] = self._calculate_arm_extension(
            right_wrist, right_shoulder, shoulder_width
        )
        features['elbow_bend_R'] = self._calculate_elbow_bend(
            right_shoulder, right_elbow, right_wrist
        )
        features['lateral_offset_R'] = self._calculate_lateral_offset(
            right_wrist, torso_center, shoulder_width
        )
        
        # Hand spread
        features['hand_spread'] = self._calculate_hand_spread(
            left_wrist, right_wrist, shoulder_width
        )
        
        return features
    
    def _extract_imu_features(self, side: str, current_time: float):
        """Extract IMU features for left or right hand."""
        features = {
            'accel_magnitude': 0.0,
            'gyro_magnitude': 0.0,
            'jerk': 0.0,
            'shake_energy': 0.0,
            'activity': 0.0,
            'confidence': 0.0
        }
        
        # Select IMU reader and filters based on side
        if side == 'L':
            imu_reader = self.imu_reader_L
            hp_filters = self.hp_filters_L
            bandpass = self.bandpass_L
            accel_history = self.accel_mag_history_L
            prev_accel = self.prev_accel_mag_L
            last_time = self.last_imu_time_L
        else:  # 'R'
            imu_reader = self.imu_reader_R
            hp_filters = self.hp_filters_R
            bandpass = self.bandpass_R
            accel_history = self.accel_mag_history_R
            prev_accel = self.prev_accel_mag_R
            last_time = self.last_imu_time_R
        
        if not imu_reader:
            return features
        
        # Get latest IMU sample (non-blocking)
        try:
            from imu_viewer.models import ImuSample
            sample = imu_reader.get_sample(timeout=0.0)
            
            if sample and isinstance(sample, ImuSample):
                # Calculate time delta
                dt = current_time - last_time if last_time > 0 else 0.01
                if dt < 0.001:
                    dt = 0.01
                
                # Update last time
                if side == 'L':
                    self.last_imu_time_L = current_time
                else:
                    self.last_imu_time_R = current_time
                
                # Acceleration magnitude
                accel_mag = self._calculate_accel_magnitude(sample.accel_g, hp_filters)
                features['accel_magnitude'] = accel_mag
                
                # Update history
                accel_history.append(accel_mag)
                
                # Jerk
                if prev_accel > 0.0:
                    features['jerk'] = self._calculate_jerk(accel_mag, prev_accel, dt)
                
                # Update previous
                if side == 'L':
                    self.prev_accel_mag_L = accel_mag
                else:
                    self.prev_accel_mag_R = accel_mag
                
                # Gyro magnitude
                gyro_mag = self._calculate_gyro_magnitude(sample.gyro_dps)
                features['gyro_magnitude'] = gyro_mag
                
                # Activity scalar
                features['activity'] = self._calculate_activity_scalar(accel_mag, gyro_mag)
                
                # Shake energy
                features['shake_energy'] = self._calculate_shake_energy(accel_history, bandpass)
                
                # Confidence
                features['confidence'] = self._calculate_imu_confidence(
                    last_time, current_time
                )
        except Exception as e:
            # If IMU reading fails, return default features
            pass
        
        return features
    
    def _fuse_features(self, mp_features, imu_features_L, imu_features_R, current_time):
        """Fuse MediaPipe and IMU features into MotionState."""
        state = MotionState()
        
        # MediaPipe confidence
        mp_confidence = mp_features.get('confidence', 0.0)
        state.mediapipe_confidence = mp_confidence
        
        # Pose features (MediaPipe-derived, smoothed and confidence-weighted)
        pose_features = [
            'hand_height_L', 'hand_height_R',
            'arm_extension_L', 'arm_extension_R',
            'elbow_bend_L', 'elbow_bend_R',
            'hand_spread', 'lateral_offset_L', 'lateral_offset_R'
        ]
        
        for feature in pose_features:
            raw_value = mp_features.get(feature, 0.5)
            # Apply smoothing
            smoothed = self.smoothers[feature].update(raw_value)
            # Apply confidence weighting
            final_value = self.confidence_handlers[feature].update(
                smoothed, mp_confidence, current_time
            )
            setattr(state, feature, final_value)
        
        # IMU features (dynamics, smoothed and confidence-weighted)
        imu_confidence_L = imu_features_L.get('confidence', 0.0)
        imu_confidence_R = imu_features_R.get('confidence', 0.0)
        
        state.imu_confidence_L = imu_confidence_L
        state.imu_confidence_R = imu_confidence_R
        
        # Left IMU features
        activity_L_raw = imu_features_L.get('activity', 0.0)
        activity_L_smoothed = self.smoothers['activity_L'].update(activity_L_raw)
        state.activity_L = self.confidence_handlers['activity_L'].update(
            activity_L_smoothed, imu_confidence_L, current_time
        )
        
        jerk_L_raw = imu_features_L.get('jerk', 0.0)
        jerk_L_smoothed = self.smoothers['jerk_L'].update(jerk_L_raw)
        state.jerk_L = self.confidence_handlers['jerk_L'].update(
            jerk_L_smoothed, imu_confidence_L, current_time
        )
        
        shake_L_raw = imu_features_L.get('shake_energy', 0.0)
        shake_L_smoothed = self.smoothers['shake_energy_L'].update(shake_L_raw)
        state.shake_energy_L = self.confidence_handlers['shake_energy_L'].update(
            shake_L_smoothed, imu_confidence_L, current_time
        )
        
        # Right IMU features
        activity_R_raw = imu_features_R.get('activity', 0.0)
        activity_R_smoothed = self.smoothers['activity_R'].update(activity_R_raw)
        state.activity_R = self.confidence_handlers['activity_R'].update(
            activity_R_smoothed, imu_confidence_R, current_time
        )
        
        jerk_R_raw = imu_features_R.get('jerk', 0.0)
        jerk_R_smoothed = self.smoothers['jerk_R'].update(jerk_R_raw)
        state.jerk_R = self.confidence_handlers['jerk_R'].update(
            jerk_R_smoothed, imu_confidence_R, current_time
        )
        
        shake_R_raw = imu_features_R.get('shake_energy', 0.0)
        shake_R_smoothed = self.smoothers['shake_energy_R'].update(shake_R_raw)
        state.shake_energy_R = self.confidence_handlers['shake_energy_R'].update(
            shake_R_smoothed, imu_confidence_R, current_time
        )
        
        # When single IMU drives both (imu_features_L is imu_features_R), force L to match R
        # so _L indicators move; L smoothers/handlers may have stale state from when only R had data.
        if imu_features_L is imu_features_R:
            state.activity_L = state.activity_R
            state.jerk_L = state.jerk_R
            state.shake_energy_L = state.shake_energy_R
            state.imu_confidence_L = state.imu_confidence_R

        # Global activity (average of left and right)
        state.activity_global = (state.activity_L + state.activity_R) / 2.0
        
        return state
