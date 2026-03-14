# WT901WIFI Coordinate System Analysis: Observed vs Documentation

## Executive Summary

Our implementation reveals a discrepancy between the **standard IMU coordinate system conventions** and the **actual behavior** of the WT901WIFI device. 

**Standard IMU Convention:**
- Roll (X-axis rotation) → Should control horizontal (X) movement
- Pitch (Y-axis rotation) → Should control vertical (Y) movement

**Observed Device Behavior:**
- Roll (X-axis rotation) → Actually controls vertical (Y) movement  
- Pitch (Y-axis rotation) → Actually controls horizontal (X) movement

This analysis documents the findings to help determine if this is:
1. A device-specific anomaly
2. A documentation error
3. A coordinate system convention difference
4. Roll and Pitch are swapped in the protocol

## Standard IMU Coordinate System (Expected)

IMUs typically use a different convention than aerospace devices:

### Axis Definitions
- **X-axis**: Points right (lateral)
- **Y-axis**: Points forward (longitudinal)  
- **Z-axis**: Points up (vertical, right-hand rule)

### Angle Definitions
- **Roll (φ)**: Rotation around the **X-axis**
  - Tilt left/right (like rolling your head toward your shoulder)
  - Positive roll = tilt right
  - Negative roll = tilt left
  - **Should Control**: Horizontal (X) movement (left/right)

- **Pitch (θ)**: Rotation around the **Y-axis**
  - Tilt forward/back
  - Positive pitch = tilt forward
  - Negative pitch = tilt back
  - **Should Control**: Vertical (Y) movement (up/down)

- **Yaw (ψ)**: Rotation around the **Z-axis**
  - Turn left/right (compass heading)
  - Positive yaw = turn right
  - Negative yaw = turn left
  - **Controls**: Heading/compass direction

**Expected Mapping:**
- Roll (X-axis rotation) → Horizontal (X) position
- Pitch (Y-axis rotation) → Vertical (Y) position

## Our Observed Behavior

Based on physical testing with Method A in `motion-app.py`:

### Actual Device Behavior
- **Roll +90°** → Box moves **UP** (vertical, Y-axis)
- **Roll -90°** → Box moves **DOWN** (vertical, Y-axis)
- **Pitch +90°** → Box moves **RIGHT** (horizontal, X-axis)
- **Pitch -90°** → Box moves **LEFT** (horizontal, X-axis)

### Mapping Required
- **Roll** controls **Y (vertical)** position
- **Pitch** controls **X (horizontal)** position

## The Discrepancy

### What IMU Conventions Say:
```
Roll (X-axis rotation)  → Should control horizontal (X) movement (left/right)
Pitch (Y-axis rotation) → Should control vertical (Y) movement (up/down)
```

### What We Observe:
```
Roll (X-axis rotation)  → Actually controls vertical (Y) movement (up/down)
Pitch (Y-axis rotation) → Actually controls horizontal (X) movement (left/right)
```

**The device behavior is swapped from standard IMU conventions.**

This suggests one of the following:
1. The device is reporting Roll and Pitch in swapped positions in the protocol
2. The device's coordinate system is rotated 90° from standard
3. The device firmware uses a different convention

## Possible Explanations

### 1. Device-Specific Coordinate System

The WT901WIFI may use a **different coordinate system convention** than standard aerospace:

**Hypothesis A: Rotated Coordinate System**
- The device's X, Y, Z axes may be rotated 90° from standard
- Device X = Standard Y
- Device Y = Standard Z  
- Device Z = Standard X

**Hypothesis B: Roll and Pitch Are Swapped in Protocol**
- The device may be reporting Roll and Pitch in swapped positions
- Byte 38-40 labeled "Roll" might actually contain Pitch values
- Byte 40-42 labeled "Pitch" might actually contain Roll values
- This would explain why Roll controls Y and Pitch controls X

**Hypothesis C: Screen/Display Coordinate System**
- The device may be optimized for screen/display applications
- Screen coordinates: X = horizontal, Y = vertical (top-to-bottom)
- The device may map angles to screen coordinates directly

### 2. Documentation Error

The manufacturer's documentation may:
- Use standard aerospace conventions in text
- But the actual device firmware uses a different convention
- Documentation may not have been updated to match firmware

### 3. Device Orientation/Mounting

The device's physical orientation when mounted may affect angle interpretation:
- If the device is mounted rotated 90° from expected orientation
- The angles would appear swapped
- But this would be a mounting issue, not a device issue

### 4. Firmware Version Differences

Different firmware versions may:
- Use different coordinate systems
- Have bugs or inconsistencies
- Have been updated without documentation updates

## Protocol Documentation Review

### What We Know from Protocol

From `imu_viewer/data_sources/serial_reader.py`:
- Bytes 38-40: Roll (signed int16, ±180°)
- Bytes 40-42: Pitch (signed int16, ±180°)
- Bytes 42-44: Yaw (signed int16, ±180°)

The protocol clearly defines three separate angle values labeled as Roll, Pitch, Yaw.

### What We Don't Know

The protocol documentation (`WT901WIFI protocol.pdf`) likely:
- Defines the byte positions (which we have correct)
- May or may not define the coordinate system
- May or may not define what "Roll" and "Pitch" mean in physical terms
- May or may not clarify if the device uses IMU conventions vs aerospace conventions

**Key Question**: Does the device protocol actually swap Roll and Pitch, or does it use a rotated coordinate system?

## Testing Recommendations

To determine if this is device-specific or universal:

### Test 1: Multiple Devices
- Test with a second WT901WIFI device
- If behavior matches → Likely a documentation/firmware convention issue
- If behavior differs → Likely a device-specific anomaly

### Test 2: Physical Orientation Tests
- Place device flat on table (0° roll, 0° pitch)
- Tilt device forward/back → Should see **Pitch** change (Y-axis rotation)
- Tilt device left/right → Should see **Roll** change (X-axis rotation)
- **Key Test**: When tilting left/right, check if the value in the "Roll" byte changes or if the "Pitch" byte changes
- **Key Test**: When tilting forward/back, check if the value in the "Pitch" byte changes or if the "Roll" byte changes
- This will determine if Roll and Pitch are swapped in the protocol

### Test 3: Documentation Cross-Reference
- Check if manufacturer's Windows software matches our observations
- Check if other users report similar behavior
- Review firmware version and changelog

### Test 4: Coordinate System Verification
- Use accelerometer data to verify coordinate system
- When device is flat: Z should be ~1g, X and Y should be ~0g
- When device is tilted forward: X should change
- When device is tilted right: Y should change
- Compare accelerometer axes to angle axes

## Current Implementation Status

### Code Implementation
Our code now correctly maps:
```python
# Pitch controls horizontal position (X)
x_pos = 0.5 + (pitch_rel / self.max_pitch_deg)

# Roll controls vertical position (Y)
y_pos = 0.5 - (roll_rel / self.max_roll_deg)
```

This matches the **observed behavior**, regardless of what the documentation says.

### Documentation Status
- ✅ Code comments updated to reflect actual behavior
- ✅ Analysis document created
- ⚠️ Manufacturer documentation not yet verified
- ⚠️ Coordinate system convention not yet confirmed

## Recommendations

1. **Keep Current Implementation**: The code works correctly for the observed behavior
2. **Document the Discrepancy**: Note in code/comments that behavior differs from standard conventions
3. **Test with Additional Devices**: Verify if this is universal or device-specific
4. **Contact Manufacturer** (if needed): If multiple devices show same behavior, may indicate documentation issue
5. **Add Configuration Option**: Consider allowing users to swap axes if needed for different devices

## Conclusion

We have a working implementation that matches observed device behavior. The discrepancy with standard conventions could be:
- A device-specific coordinate system choice
- A documentation error
- A firmware convention difference

**Next Step**: Test with additional devices to determine if this is universal or device-specific.

## References

- Protocol Parser: `imu_viewer/data_sources/serial_reader.py` lines 194-230
- Implementation: `motion-app.py` lines 2013-2022
- Analysis: `documentation/METHOD_A_ANGLE_MAPPING_ANALYSIS.md`
- Protocol Documentation: `documentation/WT901 IMU docs/WT901WIFI protocol.pdf`

