# Extraction Notes

## Line Ranges from motion-app.py

- PoseCard: lines 37-113 ✅ (extracted to ui/widgets/pose_card.py)
- HandsDemoWidget: lines 114-263 ⏳ (needs extraction to ui/tabs/ml_stream.py)
- YogaPoseDetectorWidget: lines 264-949 ⏳ (needs extraction to ui/tabs/yoga_pose.py)
- ImuStatsWidget: lines 950-1028 ✅ (extracted to ui/widgets/imu_stats.py)
- ImuBoxWidget: lines 1029-1070 ✅ (extracted to imu/visualization/box.py)
- ImuSquareWidget: lines 1071-1213 ✅ (extracted to imu/visualization/base.py)
- ImuDualSquareWidget: lines 1214-1358 ✅ (extracted to imu/visualization/dual_square.py)
- ImuSquareSoundWidget: lines 1359-1466 ⏳ (needs extraction to imu/methods/base.py or separate)
- ImuSquareSoundLoudnessWidget: lines 1467-1769 ⏳ (needs extraction to imu/methods/method_d.py)
- ImuSquareSoundTimbreWidget: lines 1770-2124 ⏳ (needs extraction to imu/methods/method_f.py)
- ImuSquareSoundFileWidget: lines 2125-2650 ⏳ (needs extraction to imu/methods/method_g.py)
- ComingSoonWidget: lines 2651-2678 ✅ (extracted to ui/tabs/coming_soon.py)
- MusicInMotionWidget: lines 2679-3623 ⏳ (needs extraction to ui/tabs/imu_prototypes.py)
- MainWindow: lines 3624-3811 ⏳ (needs extraction to ui/main_window.py)

## Import Updates Needed

When extracting, update imports:
- `from PyQt5.QtWidgets import ...` → Keep as is
- `import numpy as np` → Keep as is
- `import sounddevice as sd` → Can use `from ...audio.player import AudioStream`
- Constants → `from ...utils.constants import ...`
- Math utils → `from ...utils.math_utils import ...`
- Audio utils → `from ...audio.utils import ...`
- Audio synthesis → `from ...audio.synthesis import ...`
- Audio effects → `from ...audio.effects import ...`

## Method-Specific Notes

### Method D (Loudness)
- Uses acceleration-based volume control
- Has volume indicator UI
- Extends ImuSquareSoundWidget

### Method F (Timbre)
- Uses waveform morphing (sine/sawtooth)
- Has three control bars (Volume, Pitch, Timbre)
- User-controlled volume, IMU-controlled pitch and timbre

### Method G (Audio File + EQ)
- Uses librosa for audio file loading
- Implements 7-band EQ with FFT
- Has EQ visualization bars
- Volume controlled by pitch, timbre by roll

