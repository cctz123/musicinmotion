# Prototype B — Calm vs Intense

← [Music in Motion Final Pipeline](MM-PIPELINE.md)

## Purpose and concept

Concept: **Whole-body posture controls emotional state** (calm vs intense) and **hands control expression** (brightness, attack, resonance accents).

**Design principle:** **Full body posture → mode; hands → expression.**

- **Posture (hand spread)** drives a **state-like** mode (calm vs intense) via hysteresis, so the character shift is clear and stable.
- **Right hand height** drives cutoff and brightness (higher hand → brighter, more harmonic).
- **Left arm extension** drives attack (extended arm → sharp, punchy transients).
- **Sudden movement (jerk)** creates **resonance bursts** that decay over time for clear accents.
- **Global activity** drives volume with **stronger compression** so it supports the performance without dominating.

## Example Demo Flow

- **Stand narrow** → calm, ambient tone; mode slider low (Calm).
- **Spread arms** → intense, aggressive synth; mode slider high (Intense).
- **Raise right hand** → cutoff and brightness sliders rise; tone gets brighter and more harmonic.
- **Extend left arm** → attack slider rises; transients become sharp and punchy (“pushing” the sound).
- **Sudden movement (snap / jerk)** → resonance slider spikes then decays; clear “accents.”
- **Move more** → volume increases but stays compressed; stillness → quieter.

The performer can create a clear **emotional arc**: narrow and calm → spread and intense, with hand and jerk details adding expression and accents.

---

## Controls driven by Prototype B

| Control          | Source (MotionState)     | Role in Calm vs Intense                    |
|------------------|--------------------------|-------------------------------------------|
| **V_mode**       | `hand_spread` (hysteresis)| Narrow → Calm (0); spread → Intense (1)   |
| **V_cutoff**     | `hand_height_R`          | Right hand up → brighter; down → darker   |
| **V_brightness** | `hand_height_R` (curve)  | Same source, exponent 1.6 for “open up”   |
| **V_attack**     | `arm_extension_L`        | Arm extended → sharp transients           |
| **V_resonance**   | `jerk_L`, `jerk_R` (burst)| Sudden movement → spike then decay        |
| **V_volume**      | `activity_global`        | More movement → louder (compressed range) |

**Not driven by B:** V_tremolo and V_pan remain from the sliders.

---

## Detailed mapping and code

All MotionState values are in [0, 1]. TimbreControls are [0, 1]. Sliders use 0–100 with `value_normalized = slider_value / 100.0`.

### 1. Hand spread → V_mode (hysteresis)

- **Source:** `hand_spread`. Mode is **state-like** (calm vs intense), not continuous, so the character shift is obvious and stable.
- **Mapping:** Internal `mode_raw = smoothed_hand_spread`. Discrete `_mode_state`: switch to **intense** when `mode_raw > MODE_HYSTERESIS_HIGH` (0.62); switch to **calm** when `mode_raw < MODE_HYSTERESIS_LOW` (0.38). Output: `V_mode = 1.0` when intense, `0.0` when calm.
- **Smoothing:** One-pole on hand_spread (tau ~80 ms).

```python
# In _update_prototype_b_smoothing():
self._smoothed_hand_spread = self._one_pole_smooth(
    s.hand_spread, self._smoothed_hand_spread, dt, 0.08
)
mode_raw = max(0.0, min(1.0, self._smoothed_hand_spread))
if self._mode_state == 'calm' and mode_raw > MODE_HYSTERESIS_HIGH:
    self._mode_state = 'intense'
elif self._mode_state == 'intense' and mode_raw < MODE_HYSTERESIS_LOW:
    self._mode_state = 'calm'

# In snapshot:
mode_value = 1.0 if self._mode_state == 'intense' else 0.0
```

---

### 2. Right hand height → V_cutoff and V_brightness

- **Source:** `hand_height_R`. Same source for both; different curves for “demo pop.”
- **V_cutoff:** Linear in height: `cutoff_value = height` (clamped).
- **V_brightness:** Top-half acceleration: `brightness_value = pow(height, BRIGHTNESS_HEIGHT_EXPONENT)` with `BRIGHTNESS_HEIGHT_EXPONENT = 1.6`, clamped. Raising hand above shoulder “really opens up.”
- **Smoothing:** Reuses `_smoothed_hand_height_R` from `_update_sensor_smoothing()` (two-stage median + two-speed one-pole).

```python
# In snapshot (B):
height = max(0.0, min(1.0, self._smoothed_hand_height_R))
cutoff_value = height
brightness_value = max(0.0, min(1.0, math.pow(height, BRIGHTNESS_HEIGHT_EXPONENT)))
```

---

### 3. Left arm extension → V_attack

- **Source:** `arm_extension_L`. Arm bent → low extension; arm fully extended → high.
- **Mapping:** Direct: `V_attack = smoothed_arm_extension_L` (clamped). Extended arm → sharp, punchy transients (“pushing” the sound).
- **Smoothing:** One-pole (tau ~70 ms), updated in `_update_prototype_b_smoothing()`.

```python
# In _update_prototype_b_smoothing():
self._smoothed_arm_extension_L = self._one_pole_smooth(
    s.arm_extension_L, self._smoothed_arm_extension_L, dt, 0.07
)

# In snapshot:
attack_value = max(0.0, min(1.0, self._smoothed_arm_extension_L))
```

---

### 4. Jerk_L / Jerk_R → resonance bursts

- **Source:** `jerk_L`, `jerk_R`. Fast sudden movement → high jerk; stillness → low.
- **Mapping:** When `jerk_max = max(jerk_L, jerk_R)` exceeds `JERK_BURST_THRESHOLD` (0.15), add to `_resonance_burst` with `JERK_BURST_GAIN` (0.5). Burst **decays over time**: `_resonance_burst *= exp(-dt / TAU_RESONANCE_BURST_DECAY)` with `TAU_RESONANCE_BURST_DECAY = 0.35` s, so the accent envelope is stable across frame rates. `V_resonance = min(cap, base + _resonance_burst)`. In intense mode, resonance is capped at `RESONANCE_CAP_INTENSE` (0.92) to avoid harsh filter squeal.
- **Smoothing:** Time-based decay and burst add in `_update_prototype_b_smoothing()`; `_last_burst_time` updated each frame.

```python
# In _update_prototype_b_smoothing():
elapsed = current_time - self._last_burst_time
self._last_burst_time = current_time
self._resonance_burst *= math.exp(-elapsed / TAU_RESONANCE_BURST_DECAY)
jerk_max = max(getattr(s, 'jerk_L', 0.0), getattr(s, 'jerk_R', 0.0))
if jerk_max > JERK_BURST_THRESHOLD:
    burst_add = JERK_BURST_GAIN * min(1.0, jerk_max - JERK_BURST_THRESHOLD)
    self._resonance_burst = min(1.0, self._resonance_burst + burst_add)

# In snapshot:
base_resonance = 0.0
resonance_cap = RESONANCE_CAP_INTENSE if self._mode_state == 'intense' else 1.0
resonance_value = min(resonance_cap, base_resonance + self._resonance_burst)
```

---

### 5. Global activity → V_volume (compressed)

- **Source:** `activity_global`. More movement → louder; stillness → softer.
- **Mapping:** **Compressed** so volume supports but doesn’t dominate: `curved = activity_global ** 2.0`; `V_volume = 0.25 + 0.55 * curved` (clamped). Stillness ≈ 0.25, full activity ≈ 0.8.
- **Smoothing:** Two-speed one-pole (tau_up 60 ms, tau_down 200 ms), same as Prototype A’s activity smoothing.

```python
# In _update_prototype_b_smoothing():
self._smoothed_activity_global = self._two_speed_smooth(
    s.activity_global, self._smoothed_activity_global, dt, 0.06, 0.2
)

# In snapshot:
curved = self._smoothed_activity_global ** 2.0
volume_value = max(0.0, min(1.0, 0.25 + 0.55 * curved))
```

---

## Flow: smoothing, snapshot, and UI push

1. **Each video frame** (`_update_video_frame()`):  
   `_update_sensor_smoothing()` (updates `_smoothed_hand_height_R`) → if Prototype B, `_update_prototype_b_smoothing()` (hand_spread, arm_extension_L, activity_global, mode hysteresis, resonance burst decay + add) → `_update_atomic_snapshot()` → if Prototype B, `_push_prototype_b_values_to_ui()`.

2. **Push to UI:** The six values from the snapshot are written to `timbre_controls`, then the six sliders (mode, cutoff, brightness, attack, resonance, volume) are updated with signals blocked:

```python
self.mode_slider.blockSignals(True)
self.mode_slider.setValue(round(ctrl.V_mode * 100))
self.mode_slider.blockSignals(False)
# ... same for cutoff, brightness, attack, resonance, volume
```

