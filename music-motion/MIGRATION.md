# Migration Guide: motion-app.py → music-motion package

This guide outlines the steps to complete the migration from the monolithic `motion-app.py` to the modular `music-motion` package.

## Overview

The migration follows a 7-phase approach as outlined in `TICKET-MM-PACKAGE`. The foundation has been laid with utilities, audio layer, and base structures. This guide helps complete the remaining work.

## Phase 1: ✅ Complete
- Utils extracted (constants, math_utils, ui_utils)

## Phase 2: ✅ Complete
- Audio layer extracted (synthesis, effects, player, utils)

## Phase 3: Extract IMU Methods (In Progress)

### Step 3.1: Extract Base Method Class
Create `imu/methods/base.py` with common audio/IMU logic:
- Audio stream management
- Common angle handling
- Base visualization integration

### Step 3.2: Extract Individual Methods
For each method (A, B, D, E, F, G):
1. Copy the widget class from `motion-app.py`
2. Update imports to use new package structure
3. Inherit from appropriate base classes
4. Move to `imu/methods/method_X.py`

**Key mappings:**
- Method A: `ImuBoxWidget` → `imu/methods/method_a.py`
- Method B: `ImuSquareWidget` (base) → already in `imu/visualization/base.py`
- Method D: `ImuSquareSoundLoudnessWidget` → `imu/methods/method_d.py`
- Method E: `ImuDualSquareWidget` → `imu/methods/method_e.py`
- Method F: `ImuSquareSoundTimbreWidget` → `imu/methods/method_f.py`
- Method G: `ImuSquareSoundFileWidget` → `imu/methods/method_g.py`

### Step 3.3: Extract Dual Square Widget
Create `imu/visualization/dual_square.py`:
- Copy `ImuDualSquareWidget` class
- Update imports

## Phase 4: Extract UI Components

### Step 4.1: Extract Reusable Widgets
1. **`ui/widgets/pose_card.py`**: Copy `PoseCard` class (lines ~37-110)
2. **`ui/widgets/imu_stats.py`**: Copy `ImuStatsWidget` class (lines ~950-1028)

### Step 4.2: Extract Tab Widgets
1. **`ui/tabs/base_tab.py`**: Create base class with:
   - `cleanup()` method
   - `resume()` method
   - `set_camera_blackout()` method
   - Common initialization patterns

2. **`ui/tabs/imu_prototypes.py`**: Copy `MusicInMotionWidget` class (lines ~2679-3623)
   - Update imports
   - Update method widget references to use new package structure

3. **`ui/tabs/ml_stream.py`**: Copy `HandsDemoWidget` class (lines ~114-263)
   - Update imports
   - Move MediaPipe logic to `ml/hands.py` if needed

4. **`ui/tabs/yoga_pose.py`**: Copy `YogaPoseDetectorWidget` class (lines ~264-949)
   - Update imports
   - Move pose detection logic to `ml/yoga.py`

5. **`ui/tabs/coming_soon.py`**: Copy `ComingSoonWidget` class (lines ~2651-2678)

### Step 4.3: Extract Main Window
1. **`ui/main_window.py`**: Copy `MainWindow` class (lines ~3624-3801)
   - Update imports for all tab widgets
   - Update widget instantiation

## Phase 5: Extract ML Components

### Step 5.1: Extract Hands Detection
Create `ml/hands.py`:
- MediaPipe hands initialization
- Hand landmark processing
- Can be imported by `ui/tabs/ml_stream.py`

### Step 5.2: Extract Yoga Pose Detection
Create `ml/yoga.py`:
- Pose detection algorithms
- Angle calculations (use `utils.math_utils.calculate_angle`)
- Pose classification logic
- Can be imported by `ui/tabs/yoga_pose.py`

## Phase 6: Update Entry Points

### Step 6.1: Update main.py
Ensure `main.py` correctly imports:
```python
from .ui.main_window import MainWindow
```

### Step 6.2: Test Entry Points
```bash
python -m music-motion
python -m music-motion.main
```

## Phase 7: Testing and Cleanup

### Step 7.1: Update All Imports
Search for all imports in extracted files and update:
- `from motion_app import ...` → `from music_motion.ui... import ...`
- Update relative imports as needed

### Step 7.2: Test Each Component
1. Test each IMU method (A, B, D, E, F, G)
2. Test each tab
3. Test tab switching
4. Test camera blackout
5. Test audio playback
6. Test IMU data flow

### Step 7.3: Cleanup
1. Keep `motion-app.py` as backup initially
2. Update any scripts that import from `motion-app.py`
3. Update documentation
4. Remove backup once confirmed working

## Import Patterns

### Before (motion-app.py):
```python
# Everything in one file
class ImuSquareWidget(QWidget):
    MAX_TILT_DEG = 5.0
    def map_tilt_to_position(self, roll_deg, pitch_deg):
        # implementation
```

### After (music-motion package):
```python
from music_motion.utils.constants import MAX_TILT_DEG
from music_motion.utils.math_utils import map_tilt_to_position
from music_motion.imu.visualization.base import ImuSquareWidget

class MyMethod(ImuSquareWidget):
    def some_method(self):
        x, y = map_tilt_to_position(roll_deg, pitch_deg)
```

## Common Issues and Solutions

### Issue: Circular Imports
**Solution**: Use relative imports within package, absolute imports from outside

### Issue: Missing Constants
**Solution**: Ensure all constants are in `utils/constants.py` and imported where needed

### Issue: Audio Not Working
**Solution**: Check that `audio/player.py` AudioStream is properly initialized and callbacks are set up

### Issue: IMU Data Not Flowing
**Solution**: Verify `imu/reader.py` wrapper correctly interfaces with `imu_viewer` package

## Next Steps

1. Complete Phase 3 (IMU methods extraction)
2. Complete Phase 4 (UI components extraction)
3. Complete Phase 5 (ML components extraction)
4. Test thoroughly
5. Update documentation

