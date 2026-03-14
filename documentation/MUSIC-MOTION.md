# Music Motion — Overview

This page is the overview and launching pad for the Music Motion system and its prototypes. The system is organized into four design-pattern branches:

---

## 1. IMU-only design pattern

Motion is driven entirely by **inertial measurement units** (IMUs): orientation (roll, pitch, yaw) and acceleration. No camera.

**Documentation:** [IMU Pipeline](IMU-PIPELINE.md) — prototypes A–G (large movement, precise movement, pitch+pan, volume, dual IMUs, timbre, equalizer).

---

## 2. Vision-only design pattern

Motion is driven entirely by **camera + computer vision** (MediaPipe Pose and Hands). No IMUs.

**Documentation:** [Media Pose Pipeline](MP-PIPELINE.md) — prototypes A (Hands), B (Yoga Pose), C (Equalizer).

---

## 3. Multimodal Fusion design pattern

Combines **IMU** and **Vision** into a single motion representation (e.g. pose from camera + dynamics from IMUs).

**Documentation:** [Multi-modal Pipeline](SF-PIPELINE.md) - prototypes A (Full Timbre), B (Timbre Core), C (Motion->Audio Mapping)

---

## 4. Optimized Real-Time System

Real-time, low-latency pipeline and deployment optimizations across sensors and fusion.

**Documentation:** [Final Optimized Design](MM-PIPELINE.md) - prototypes A-C (Air DJ, Calm/Intense, Two Handed Instrument)

---

For setup and installation, see [INSTALL.md](INSTALL.md).

For controlling and setting up the IMUs, see [IMU.md](IMU.md)
