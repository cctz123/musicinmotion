# Method A Angle Mapping Analysis

## Problem Statement

The observed behavior of Method A in `motion-app.py` did not match the documented/expected behavior:

**Observed Behavior (CORRECTED):**
- Roll +90° → box moves UP (vertical)
- Roll -90° → box moves DOWN (vertical)  
- Pitch +90° → box moves RIGHT (horizontal)
- Pitch -90° → box moves LEFT (horizontal)

**Original Code Behavior (INCORRECT):**
- Roll was mapped to control horizontal (X) position
- Pitch was mapped to control vertical (Y) position

**Correct Mapping:**
- Roll should control vertical (Y) position
- Pitch should control horizontal (X) position

## Current Code Implementation

From `motion-app.py` lines 2013-2022:

```python
# Map relative angles to box position
# Roll (left/right tilt) controls horizontal position
# Positive roll (tilt right) → box moves right
# Negative roll (tilt left) → box moves left
x_pos = 0.5 + (roll_rel / self.max_roll_deg)

# Pitch (forward/back tilt) controls vertical position
# Positive pitch (tilt forward) → box moves down (invert Y for screen)
# Negative pitch (tilt back) → box moves up
y_pos = 0.5 - (pitch_rel / self.max_pitch_deg)  # Minus to invert screen Y
```

## Protocol Data Extraction

From `imu_viewer/data_sources/serial_reader.py` lines 194-230:

```python
# Angles: Roll, Pitch, Yaw (signed int16)
roll_raw = struct.unpack('<h', line[38:40])[0]
pitch_raw = struct.unpack('<h', line[40:42])[0]
yaw_raw = struct.unpack('<h', line[42:44])[0]

# Angles: ±180 degrees
roll_deg = roll_raw / 32768.0 * 180.0
pitch_deg = pitch_raw / 32768.0 * 180.0
yaw_deg = yaw_raw / 32768.0 * 180.0
```

The code extracts Roll, Pitch, Yaw from bytes 38-44 of the WT55 protocol frame in that order.

## Coordinate System Definitions

According to standard aerospace/IMU conventions:
- **Roll**: Rotation around the longitudinal (X) axis (bank angle)
- **Pitch**: Rotation around the lateral (Y) axis (nose up/down)
- **Yaw**: Rotation around the vertical (Z) axis (heading)

However, the **WT901WIFI device's actual coordinate system** may differ from these standard definitions. The device manufacturer's documentation should be consulted for the exact definitions.

## Analysis

### Issue 1: Axes Are Swapped

The observed behavior confirms that:
- **Roll controls Y (vertical) position**, not X
- **Pitch controls X (horizontal) position**, not Y

The original code had the axes swapped. The fix is to swap the mapping.

### Issue 2: Sign Behavior (RESOLVED)

Initial observation suggested both +90° and -90° Roll moved the box UP, but further testing revealed:
- Roll +90° → box moves UP (correct)
- Roll -90° → box moves DOWN (correct)
- The sign is working correctly; the initial observation was incomplete

## Solution (IMPLEMENTED)

The axes have been swapped in the code to match observed behavior:

```python
# Pitch controls horizontal position (X)
# Positive pitch (+90°) → box moves right
# Negative pitch (-90°) → box moves left
x_pos = 0.5 + (pitch_rel / self.max_pitch_deg)

# Roll controls vertical position (Y)
# Positive roll (+90°) → box moves up (invert Y for screen coordinates)
# Negative roll (-90°) → box moves down
y_pos = 0.5 - (roll_rel / self.max_roll_deg)  # Minus to invert screen Y
```

**Verification:**
- Roll +90°: y_pos = 0.5 - (90/45) = 0.5 - 2.0 = -1.5 → clamped to 0.0 (top = UP) ✓
- Roll -90°: y_pos = 0.5 - (-90/45) = 0.5 - (-2.0) = 2.5 → clamped to 1.0 (bottom = DOWN) ✓
- Pitch +90°: x_pos = 0.5 + (90/45) = 0.5 + 2.0 = 2.5 → clamped to 1.0 (right = RIGHT) ✓
- Pitch -90°: x_pos = 0.5 + (-90/45) = 0.5 + (-2.0) = -1.5 → clamped to 0.0 (left = LEFT) ✓

## Recommended Next Steps

1. **Test with Known Orientations**: 
   - Place device flat (0° roll, 0° pitch) and note box position
   - Tilt device forward (positive pitch) and observe box movement
   - Tilt device backward (negative pitch) and observe box movement
   - Tilt device left (negative roll) and observe box movement
   - Tilt device right (positive roll) and observe box movement

2. **Check Device Documentation**: 
   - Review `documentation/WT901 IMU docs/WT901WIFI protocol.pdf` section 2.2.2.19 (Roll Yaw angle register)
   - Verify the device's coordinate system and angle definitions

3. **Fix the Mapping**: 
   - Based on test results, update the mapping in `motion-app.py`
   - Update comments to reflect actual behavior
   - Consider adding a configuration option if the device orientation varies

## Current Status

- [x] Physical orientation tests performed
- [x] Mapping code updated to match observed behavior (axes swapped)
- [x] Comments updated to reflect actual behavior
- [ ] Device documentation reviewed for angle definitions (optional - behavior is now correct)
- [x] Method A behavior verified and documented

## References

- WT901WIFI Protocol Documentation: `documentation/WT901 IMU docs/WT901WIFI protocol.pdf`
- Code Location: `motion-app.py` lines 2006-2037
- Protocol Parser: `imu_viewer/data_sources/serial_reader.py` lines 194-230

