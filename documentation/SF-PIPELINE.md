# Sensor Fusion Pipeline

← [Music in Motion](MUSIC-MOTION.md)

These pages document the Sensor Fusion Pipeline prototypes created
as part of the 3rd Multi-Modal design patterns.

The next series of prototypes were used to design a sophisticated framework that fused sensor data from both the IMU pipeline and Media Pose pipeline into a single sensor pipeline that can be mapped to properties of audio signals

These prototypes were created as separate apps:

```bash
python -m timbre-control1
python -m timbre-control2
python -m fusionpipe
```


## The prototypes

- **Prototype A** — [Timbre Control](SF-PIPELINE-A.md)
- **Prototype B** — [Timbre Control 2](SF-PIPELINE-B.md)
- **Prototype C** — [Timbre Control 3](SF-PIPELINE-C.md)

---

## Architectural Principle

At a high level, the goal was to build the following sensor pipeline:

Two sets of Motion Sensors → Normalized Control Vector → DSP Parameters → Audio Output

This required separating the system into three independent layers:

1. Motion Layer
   - MediaPipe pose detection
   - Dual IMU sensors
   - MotionFeatureExtractor → MotionState

2. Control Layer
   - TimbreControls (all values normalized 0–1)
   - Atomic snapshot pattern for thread safety

3. DSP Layer
   - Low-pass filter (biquad)
   - Resonance (Q)
   - Tremolo
   - Volume mapping
   - Optional modulation (chorus, phaser, stereo in earlier prototype)

