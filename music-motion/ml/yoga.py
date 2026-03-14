"""Yoga pose detection logic using MediaPipe."""

import math
from ..utils.math_utils import calculate_angle


def detect_tree_pose(landmarks, mp_pose):
    """
    Detect if the current pose matches a tree pose.
    
    Tree pose criteria:
    - One foot lifted and placed near the standing leg's inner thigh
    - Standing leg is straight (knee angle > 170 degrees)
    - Body is vertically aligned (shoulders over hips)
    
    Args:
        landmarks: MediaPipe pose landmarks
        mp_pose: MediaPipe pose solution
        
    Returns:
        True if tree pose is detected, False otherwise
    """
    # Extract key body landmarks
    left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
    right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
    left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]
    right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
    left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
    right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
    
    # Determine which leg is the standing leg (lower ankle position)
    if left_ankle.y > right_ankle.y:
        standing_leg = "LEFT"
        lifted_ankle = right_ankle
        standing_knee = left_knee
        standing_hip = left_hip
    else:
        standing_leg = "RIGHT"
        lifted_ankle = left_ankle
        standing_knee = right_knee
        standing_hip = right_hip
    
    # Check 1: Lifted foot horizontal proximity to standing leg knee
    horizontal_distance = abs(lifted_ankle.x - standing_knee.x)
    
    # Check 2: Lifted foot vertical position (should be between hip and knee)
    vertical_position_ok = standing_hip.y < lifted_ankle.y < standing_knee.y
    
    # Check 3: Standing leg straightness
    if standing_leg == "LEFT":
        knee_angle = calculate_angle(left_hip, left_knee, left_ankle)
    else:
        knee_angle = calculate_angle(right_hip, right_knee, right_ankle)
    
    # Check 4: Body vertical alignment
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2
    hip_center_x = (left_hip.x + right_hip.x) / 2
    vertical_alignment = abs(shoulder_center_x - hip_center_x)
    
    # All criteria must be met
    is_tree_pose = (
        horizontal_distance < 0.1 and
        vertical_position_ok and
        knee_angle > 170 and
        vertical_alignment < 0.05
    )
    
    return is_tree_pose


def detect_downward_dog(landmarks, mp_pose):
    """
    Detect if the current pose matches a downward dog pose.
    
    Downward dog criteria:
    - Hips are higher than both shoulders and ankles (inverted V shape)
    - Both arms are straight (elbow angles > 160 degrees)
    - Both legs are straight (knee angles > 160 degrees)
    """
    left_wrist = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
    right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
    right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
    left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]
    right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
    left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
    right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
    left_elbow = landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value]
    right_elbow = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]
    
    wrist_center_y = (left_wrist.y + right_wrist.y) / 2
    shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2
    hip_center_y = (left_hip.y + right_hip.y) / 2
    ankle_center_y = (left_ankle.y + right_ankle.y) / 2
    
    hip_highest = (hip_center_y < shoulder_center_y and hip_center_y < ankle_center_y)
    
    left_arm_angle = calculate_angle(left_shoulder, left_elbow, left_wrist)
    right_arm_angle = calculate_angle(right_shoulder, right_elbow, right_wrist)
    left_leg_angle = calculate_angle(left_hip, left_knee, left_ankle)
    right_leg_angle = calculate_angle(right_hip, right_knee, right_ankle)
    
    is_downward_dog = (
        hip_highest and
        left_arm_angle > 160 and
        right_arm_angle > 160 and
        left_leg_angle > 160 and
        right_leg_angle > 160
    )
    
    return is_downward_dog


def detect_warrior_i(landmarks, mp_pose):
    """
    Detect if the current pose matches a warrior I pose.
    
    Warrior I criteria:
    - Front leg bent at approximately 90 degrees
    - Back leg is straight
    - Front knee is aligned over front ankle
    - Body is upright (shoulders over hips)
    - Arms are raised above shoulders
    """
    left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
    right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
    left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]
    right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
    left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
    right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    left_wrist = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
    right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]
    
    # Determine front leg
    if left_knee.x < right_knee.x:
        front_leg = "LEFT"
        front_knee = left_knee
        front_ankle = left_ankle
        front_hip = left_hip
        back_knee = right_knee
        back_ankle = right_ankle
        back_hip = right_hip
    else:
        front_leg = "RIGHT"
        front_knee = right_knee
        front_ankle = right_ankle
        front_hip = right_hip
        back_knee = left_knee
        back_ankle = left_ankle
        back_hip = left_hip
    
    front_knee_angle = calculate_angle(front_hip, front_knee, front_ankle)
    back_knee_angle = calculate_angle(back_hip, back_knee, back_ankle)
    knee_ankle_alignment = abs(front_knee.x - front_ankle.x)
    
    shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2
    hip_center_x = (left_hip.x + right_hip.x) / 2
    vertical_alignment = abs(shoulder_center_x - hip_center_x)
    
    wrists_above_shoulders = (left_wrist.y < left_shoulder.y and
                             right_wrist.y < right_shoulder.y)
    
    is_warrior_i = (
        75 < front_knee_angle < 105 and
        back_knee_angle > 170 and
        knee_ankle_alignment < 0.05 and
        vertical_alignment < 0.04 and
        wrists_above_shoulders
    )
    
    return is_warrior_i


def detect_side_angle(landmarks, mp_pose):
    """
    Detect if the current pose matches a side angle pose.
    
    Side angle criteria:
    - Front leg bent at approximately 90 degrees, knee over ankle
    - Back leg is straight
    - Body is bent sideways (torso angled more than 45 degrees)
    - Lower arm (on front leg side) is down near the ground
    - Body alignment forms a straight line
    """
    left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
    right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
    left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]
    right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
    left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
    right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
    left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
    right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
    left_wrist = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
    right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]
    
    left_knee_angle = calculate_angle(left_hip, left_knee, left_ankle)
    right_knee_angle = calculate_angle(right_hip, right_knee, right_ankle)
    
    is_left_bent = 75 < left_knee_angle < 105
    is_right_bent = 75 < right_knee_angle < 105
    
    if is_left_bent and not is_right_bent:
        front_leg = "LEFT"
    elif is_right_bent and not is_left_bent:
        front_leg = "RIGHT"
    else:
        if left_knee.x < right_knee.x:
            front_leg = "LEFT"
        else:
            front_leg = "RIGHT"
    
    if front_leg == "LEFT":
        front_knee = left_knee
        front_ankle = left_ankle
        front_hip = left_hip
        back_knee = right_knee
        back_ankle = right_ankle
        back_hip = right_hip
        lower_arm_wrist = left_wrist
        upper_arm_wrist = right_wrist
    else:
        front_knee = right_knee
        front_ankle = right_ankle
        front_hip = right_hip
        back_knee = left_knee
        back_ankle = left_ankle
        back_hip = left_hip
        lower_arm_wrist = right_wrist
        upper_arm_wrist = left_wrist
    
    front_knee_angle = calculate_angle(front_hip, front_knee, front_ankle)
    front_leg_bent = 75 < front_knee_angle < 105
    
    knee_ankle_alignment = abs(front_knee.x - front_ankle.x)
    knee_aligned = knee_ankle_alignment < 0.05
    
    back_knee_angle = calculate_angle(back_hip, back_knee, back_ankle)
    back_leg_straight = back_knee_angle > 170
    
    hip_center = ((left_hip.x + right_hip.x) / 2, (left_hip.y + right_hip.y) / 2)
    shoulder_center = ((left_shoulder.x + right_shoulder.x) / 2,
                      (left_shoulder.y + right_shoulder.y) / 2)
    
    dx = shoulder_center[0] - hip_center[0]
    dy = shoulder_center[1] - hip_center[1]
    body_angle = math.degrees(math.atan2(dx, dy)) - 90
    body_bent = abs(body_angle) > 45
    
    lower_arm_down = lower_arm_wrist.y > front_knee.y
    
    alignment_angle = calculate_angle(
        lower_arm_wrist,
        front_hip,
        upper_arm_wrist
    )
    body_alignment = 160 < alignment_angle < 200
    
    is_side_angle = (
        front_leg_bent and
        knee_aligned and
        back_leg_straight and
        body_bent and
        lower_arm_down and
        body_alignment
    )
    
    return is_side_angle

