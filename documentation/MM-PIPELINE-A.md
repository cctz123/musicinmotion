# Prototype A — Air DJ

← [Music in Motion Final Pipeline](MM-PIPELINE.md)


## Purpose and concept

Concept:
Turn the user into a DJ in the air. Big, visible gestures cause big, audible changes.

**Design principle:** **Left hand = tone & space; right hand = energy & aggression.**

- **Pan** comes from **where the hands are** (lateral position).
- **Hand spread** drives things that read as “space”: wider arms → brighter/open, more movement; optionally volume (wider stance = bigger sound). This is kept physically intuitive.

## Example Demo Flow

- **Raise right hand** → cutoff rises; cutoff slider moves up.
- **Raise left hand** → resonance increases; resonance slider moves up.
- **Move both hands left or right** → pan follows; pan slider moves.
- **Spread arms** → brightness opens; brightness slider moves up; tremolo can increase with spread.
- **Shake right hand** → tremolo; tremolo slider moves.
- **Move more** → volume increases; stillness → softer.

Sliders visibly follow the user’s motion. Pan reflects where the hands are; spread reflects space (brighter, more movement). The result feels like **conducting electronic music** in the air.


---

## Controls driven by Prototype A

| Control        | Source (MotionState)        | Role in Air DJ                         |
|----------------|-----------------------------|----------------------------------------|
| **V_cutoff**   | `hand_height_R`             | Right hand up → brighter; down → darker |
| **V_resonance**| `hand_height_L`             | Left hand up → sharper peak; down → smooth |
| **V_pan**      | `lateral_offset_L`, `_R`     | Hands left → pan left; hands right → pan right |
| **V_volume**   | `activity_global`           | More movement → louder; stillness → softer |
| **V_tremolo**  | `shake_energy_R` + `hand_spread` | Shake right hand and/or wide arms → tremolo |
| **V_brightness** | `hand_spread`             | Wider arms → brighter/open; hands close → darker |

**Not driven by A:** V_attack and V_mode remain from the sliders.

---

## Detailed mapping and code

All MotionState values are in [0, 1]. TimbreControls are [0, 1]. Sliders use 0–100 with `value_normalized = slider_value / 100.0`.

### 1. Right hand height → V_cutoff

- **Source:** `hand_height_R`.
- **Mapping:** Direct: `V_cutoff = _smoothed_hand_height_R`. Raise right hand → brighter; lower → darker.
- **Smoothing:** Reuses the existing two-stage pipeline: median-of-3 over recent frames, then two-speed one-pole (~50 ms up / 200 ms down), updated in `_update_sensor_smoothing()` every frame.

In `_update_atomic_snapshot()` when Prototype A:

```python
cutoff_value = self._smoothed_hand_height_R
```

---

### 2. Left hand height → V_resonance

- **Source:** `hand_height_L`.
- **Mapping:** Direct: `V_resonance = smoothed_hand_height_L`. Raise left hand → sharper filter peak; lower → smooth/flat.
- **Smoothing:** Two-stage like right hand: median-of-3, then two-speed one-pole (tau_up 50 ms, tau_down 200 ms), updated in `_update_prototype_a_smoothing()`.

```python
# In _update_prototype_a_smoothing():
self._hand_height_L_history.append(s.hand_height_L)
self._hand_height_L_history.pop(0)
median_L = sorted(self._hand_height_L_history)[1]
self._smoothed_hand_height_L = self._two_speed_smooth(
    median_L, self._smoothed_hand_height_L, dt, 0.05, 0.2
)

# In snapshot:
resonance_value = self._smoothed_hand_height_L
```

---

### 3. Lateral position → V_pan

- **Source:** `lateral_offset_L`, `lateral_offset_R`. Pan reflects **where the hands are**: both hands left → sound left; both hands right → sound right.
- **Mapping:** `pan = 0.5 + k * (lateral_offset_R - lateral_offset_L)` with `k = 0.5` (constant `PAN_LATERAL_K`), clamped to [0, 1].
- **Smoothing:** One-pole on each offset (tau ~80 ms).

```python
# Smoothing (in _update_prototype_a_smoothing()):
tau_lat = 0.08
self._smoothed_lateral_offset_L = self._one_pole_smooth(
    s.lateral_offset_L, self._smoothed_lateral_offset_L, dt, tau_lat
)
self._smoothed_lateral_offset_R = self._one_pole_smooth(
    s.lateral_offset_R, self._smoothed_lateral_offset_R, dt, tau_lat
)

# Snapshot:
pan_value = max(0.0, min(1.0, 0.5 + PAN_LATERAL_K * (
    self._smoothed_lateral_offset_R - self._smoothed_lateral_offset_L
)))
```

---

### 4. Hand spread → V_brightness

- **Source:** `hand_spread`. Spread drives “space”: wider arms → brighter/open.
- **Mapping:** Direct: `V_brightness = smoothed_hand_spread` (clamped to [0, 1]).
- **Smoothing:** One-pole, tau ~80 ms.

```python
# Smoothing:
self._smoothed_hand_spread = self._one_pole_smooth(
    s.hand_spread, self._smoothed_hand_spread, dt, tau_lat
)

# Snapshot:
brightness_value = max(0.0, min(1.0, self._smoothed_hand_spread))
```

---

### 5. Global activity → V_volume

- **Source:** `activity_global`. More movement → louder; stillness → softer.
- **Mapping:** Linear in activity for higher sensitivity (less movement → louder): `curved = activity_global ** 1.0`; `V_volume = 0.15 + 0.85 * curved` (clamped). Stillness → ~0.15, high activity → 1.0.
- **Smoothing:** Two-speed one-pole (tau_up 60 ms, tau_down 200 ms).

```python
# Smoothing:
self._smoothed_activity_global = self._two_speed_smooth(
    s.activity_global, self._smoothed_activity_global, dt, 0.06, 0.2
)

# Snapshot:
curved = self._smoothed_activity_global ** 1.0  # linear for higher sensitivity
volume_value = max(0.0, min(1.0, 0.15 + 0.85 * curved))
```

---

### 6. Shake energy (right) + spread → V_tremolo

- **Source:** `shake_energy_R`; optionally `hand_spread` so wider arms also add tremolo (“wider arms → more movement”).
- **Mapping:** Raw = `min(1.0, smoothed_shake_energy_R + 0.3 * smoothed_hand_spread)`. Then an **on/off threshold** (`TREMOLO_ACTIVATION_THRESHOLD = 0.10`): below it `V_tremolo = 0`; above it map [threshold, 1] → [0, 1].
- **Smoothing:** Two-speed on shake (tau_up 30 ms, tau_down 150 ms).

```python
# Smoothing:
self._smoothed_shake_energy_R = self._two_speed_smooth(
    s.shake_energy_R, self._smoothed_shake_energy_R, dt, 0.03, 0.15
)

# Snapshot:
raw_tremolo = min(1.0, self._smoothed_shake_energy_R + 0.3 * self._smoothed_hand_spread)
if raw_tremolo <= TREMOLO_ACTIVATION_THRESHOLD:
    tremolo_value = 0.0
else:
    tremolo_value = min(1.0, (raw_tremolo - TREMOLO_ACTIVATION_THRESHOLD) / (1.0 - TREMOLO_ACTIVATION_THRESHOLD))
```

---

## Flow: smoothing, snapshot, and UI push

1. **Each video frame** (`_update_video_frame()`):  
   `_update_sensor_smoothing()` (updates `_smoothed_hand_height_R`) → if Prototype A, `_update_prototype_a_smoothing()` (updates the other five smoothed state variables) → `_update_atomic_snapshot()` → if Prototype A, `_push_prototype_a_values_to_ui()`.

2. **Push to UI:** The six values from the snapshot are written to `timbre_controls`, then each of the six sliders is updated with signals blocked so that slider handlers do not overwrite the snapshot:

```python
self.cutoff_slider.blockSignals(True)
self.cutoff_slider.setValue(round(ctrl.V_cutoff * 100))
self.cutoff_slider.blockSignals(False)
# ... same for resonance, pan, volume, tremolo, brightness
```

3. **Display labels:** When Prototype A is active, the six motion-driven controls show “(Prototype A)” so it is clear the value is from motion.

---

