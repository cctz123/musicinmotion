# Prototype C — Two-Hand Instrument

← [Music in Motion Final Pipeline](MM-PIPELINE.md)

## Purpose and concept

Concept: Each hand has a distinct musical role — left hand = tone sculptor, right hand = rhythmic modulator. Very intuitive in demo.

**Design principle:** **Left hand = tone control; right hand = rhythm & motion.**

- **Left hand** shapes the tone: height → cutoff, elbow bend → resonance (bent = mellow, extended = sharp), lateral position → pan.
- **Right hand** adds percussive expression: shake → tremolo, jerk → attack spikes, activity → volume boost.
- **V_mode** is fixed (e.g. 0.6) so tremolo rate and Q range stay consistent; **V_brightness** is slaved to cutoff (0.2 + 0.8×cutoff) so tone sculpting feels cohesive.

## Example Demo Flow

- **Left hand held steady high** → bright, resonant tone; cutoff and resonance sliders reflect left hand.
- **Right hand shaking** → tremolo + punch; tremolo slider moves.
- **Right hand snapping** → attack spikes; attack slider spikes then decays.
- **Left hand left/right** → pan follows; pan slider moves.
- **More right-hand movement** → volume increases (boost); stillness → quieter.

Overall, it feels like **playing an invisible synth**: left hand sculpts tone (cutoff, resonance, pan), right hand adds rhythm and motion (tremolo, attack, volume boost).

---

## Controls driven by Prototype C

| Control          | Source (MotionState)     | Role in Two-Hand Instrument              |
|------------------|--------------------------|------------------------------------------|
| **V_cutoff**     | `hand_height_L`          | Left hand up → brighter; down → darker   |
| **V_resonance**  | `elbow_bend_L` (inverted)| Bent arm → mellow; extended → sharp peak |
| **V_pan**        | `lateral_offset_L`       | Left hand left → pan left; right → right  |
| **V_tremolo**    | `shake_energy_R`         | Shake right hand → tremolo               |
| **V_attack**     | `jerk_R` (burst envelope)| Right hand snap → attack spike then decay|
| **V_volume**     | `activity_R`             | Right-hand movement → volume boost        |
| **V_mode**       | fixed                    | Constant (e.g. 0.6) for consistent feel  |
| **V_brightness** | derived from cutoff      | 0.2 + 0.8×cutoff for cohesive tone       |

---

## Detailed mapping and code

All MotionState values are in [0, 1]. TimbreControls are [0, 1]. Sliders use 0–100 with `value_normalized = slider_value / 100.0`.

### 1. Left hand height → V_cutoff

- **Source:** `hand_height_L`. Left hand is the “tone sculptor” for brightness.
- **Mapping:** Direct: `V_cutoff = smoothed_hand_height_L` (clamped). Left hand high → brighter; left hand low → darker.
- **Smoothing:** Two-stage (median-of-3 + two-speed one-pole, tau_up 50 ms, tau_down 200 ms), same as Prototype A’s left hand, updated in `_update_prototype_c_smoothing()`.

```python
# In _update_prototype_c_smoothing():
self._hand_height_L_history.append(s.hand_height_L)
self._hand_height_L_history.pop(0)
median_L = sorted(self._hand_height_L_history)[1]
self._smoothed_hand_height_L = self._two_speed_smooth(
    median_L, self._smoothed_hand_height_L, dt, 0.05, 0.2
)

# In snapshot (C):
cutoff_value = max(0.0, min(1.0, self._smoothed_hand_height_L))
```

---

### 2. Left elbow bend → V_resonance

- **Source:** `elbow_bend_L`. Bent arm → high value; extended (straight) arm → low value.
- **Mapping:** Inverted: `V_resonance = 1.0 - smoothed_elbow_bend_L` (clamped). Bent arm → mellow (low resonance); extended arm → sharp peak (high resonance).
- **Smoothing:** One-pole (tau ~70 ms).

```python
# In _update_prototype_c_smoothing():
self._smoothed_elbow_bend_L = self._one_pole_smooth(
    s.elbow_bend_L, self._smoothed_elbow_bend_L, dt, 0.07
)

# In snapshot:
resonance_value = max(0.0, min(1.0, 1.0 - self._smoothed_elbow_bend_L))
```

---

### 3. Left hand lateral offset → V_pan

- **Source:** `lateral_offset_L`. Move left hand left → pan left; move left hand right → pan right. Convention: 0 = left, 0.5 = center, 1 = right (see MM-PIPELINE.md).
- **Mapping:** Direct: `V_pan = smoothed_lateral_offset_L` (clamped).
- **Smoothing:** One-pole (tau ~80 ms).

```python
# In _update_prototype_c_smoothing():
tau_lat = 0.08
self._smoothed_lateral_offset_L = self._one_pole_smooth(
    s.lateral_offset_L, self._smoothed_lateral_offset_L, dt, tau_lat
)

# In snapshot:
pan_value = max(0.0, min(1.0, self._smoothed_lateral_offset_L))
```

---

### 4. Right hand shake energy → V_tremolo

- **Source:** `shake_energy_R`. Shake right hand → tremolo; stop → clean.
- **Mapping:** Same as Prototype A: on/off threshold (`TREMOLO_ACTIVATION_THRESHOLD = 0.10`). Below threshold: `V_tremolo = 0`; above: map [threshold, 1] → [0, 1].
- **Smoothing:** Two-speed one-pole (tau_up 30 ms, tau_down 150 ms).

```python
# In _update_prototype_c_smoothing():
self._smoothed_shake_energy_R = self._two_speed_smooth(
    s.shake_energy_R, self._smoothed_shake_energy_R, dt, 0.03, 0.15
)

# In snapshot:
raw_tremolo = self._smoothed_shake_energy_R
if raw_tremolo <= TREMOLO_ACTIVATION_THRESHOLD:
    tremolo_value = 0.0
else:
    tremolo_value = max(0.0, min(1.0, (raw_tremolo - TREMOLO_ACTIVATION_THRESHOLD) / (1.0 - TREMOLO_ACTIVATION_THRESHOLD)))
```

---

### 5. Right hand jerk → V_attack (attack-burst envelope)

- **Source:** `jerk_R`. Right hand snapping → attack spikes; stillness → low attack.
- **Mapping:** Sudden movement triggers a **momentary attack boost** that decays over time. `V_attack = ATTACK_BASE_C + _attack_burst` (clamped). When jerk_R exceeds `ATTACK_BURST_THRESHOLD` (0.15), add to burst; burst decays with `exp(-dt / TAU_ATTACK_BURST_DECAY)` (e.g. 0.30 s).
- **Constants:** `ATTACK_BURST_THRESHOLD = 0.15`, `ATTACK_BURST_GAIN = 0.5`, `TAU_ATTACK_BURST_DECAY = 0.30`, `ATTACK_BASE_C = 0.0`.

```python
# In _update_prototype_c_smoothing():
elapsed = current_time - self._last_attack_burst_time
self._last_attack_burst_time = current_time
self._attack_burst *= math.exp(-elapsed / TAU_ATTACK_BURST_DECAY)
jerk_R = getattr(s, 'jerk_R', 0.0)
if jerk_R > ATTACK_BURST_THRESHOLD:
    burst_add = ATTACK_BURST_GAIN * min(1.0, jerk_R - ATTACK_BURST_THRESHOLD)
    self._attack_burst = min(1.0, self._attack_burst + burst_add)

# In snapshot:
attack_value = max(0.0, min(1.0, ATTACK_BASE_C + self._attack_burst))
```

---

### 6. Right hand activity → V_volume (volume boost)

- **Source:** `activity_R`. More right-hand movement → louder; stillness → lower.
- **Mapping:** `V_volume = 0.35 + 0.55 * smoothed_activity_R` (clamped). Stillness → ~0.35, full activity → ~0.9.
- **Smoothing:** Two-speed one-pole (tau_up 60 ms, tau_down 200 ms).

```python
# In _update_prototype_c_smoothing():
self._smoothed_activity_R = self._two_speed_smooth(
    s.activity_R, self._smoothed_activity_R, dt, 0.06, 0.2
)

# In snapshot:
volume_value = max(0.0, min(1.0, 0.35 + 0.55 * self._smoothed_activity_R))
```

---

### 7. V_mode and V_brightness (instrument feel)

- **V_mode:** Fixed at `MODE_FIXED_C` (e.g. **0.6**) so tremolo rate and Q range stay consistent.
- **V_brightness:** Slaved to cutoff: `V_brightness = BRIGHTNESS_C_OFFSET + BRIGHTNESS_C_SCALE * cutoff_value` (clamped). Constants: `BRIGHTNESS_C_OFFSET = 0.2`, `BRIGHTNESS_C_SCALE = 0.8` (cutoff 0 → brightness 0.2, cutoff 1 → brightness 1.0).

```python
# In snapshot (C), after computing cutoff_value:
mode_value = MODE_FIXED_C
brightness_value = max(0.0, min(1.0, BRIGHTNESS_C_OFFSET + BRIGHTNESS_C_SCALE * cutoff_value))
```

---

## Flow: smoothing, snapshot, and UI push

1. **Each video frame** (`_update_video_frame()`):  
   `_update_sensor_smoothing()` → if Prototype C, `_update_prototype_c_smoothing()` (hand_height_L, elbow_bend_L, lateral_offset_L, shake_energy_R, attack burst, activity_R) → `_update_atomic_snapshot()` → if Prototype C, `_push_prototype_c_values_to_ui()`.

2. **Push to UI:** All eight values from the snapshot are written to `timbre_controls`, then the eight sliders (cutoff, resonance, pan, tremolo, attack, volume, mode, brightness) are updated with signals blocked:

```python
self.cutoff_slider.blockSignals(True)
self.cutoff_slider.setValue(round(ctrl.V_cutoff * 100))
self.cutoff_slider.blockSignals(False)
# ... same for resonance, pan, tremolo, attack, volume, mode, brightness
```
