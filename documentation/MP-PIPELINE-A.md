# Prototype A: Hands Detector

← [MP Pipeline](MP-PIPELINE.md)

---

MediaPipe **Hands** — hand detection and 21 landmarks per hand. Part of the [Vision-only design](MP-PIPELINE.md).

## MediaPipe Hands

**What we use:** `mp.solutions.hands.Hands` — up to 2 hands per frame, 21 landmarks per hand.

**Raw output:**
- **Landmarks:** 21 keypoints per hand (wrist, thumb CMC/IP/MCP/tip, index to pinky MCP/PIP/DIP/tip, etc.). Each has `x`, `y`, `z` in normalized image coordinates.
- **Handedness:** Left/right label per detected hand.
- **Options we use:** `model_complexity=0`, `max_num_hands=2`, `min_detection_confidence=0.5`, `min_tracking_confidence=0.5`.

**Where it appears:** The Hands Demo (MP Hands Demo) tab draws the hand skeleton and landmarks on the camera feed; we do not currently expose derived “sensor” values (e.g. finger curl or pinch) beyond the raw landmarks used for visualization.

All coordinates are normalized image coordinates (typically 0–1; y increases downward).
