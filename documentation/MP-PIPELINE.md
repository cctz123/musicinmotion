# Media Pose Pipeline

← [Music in Motion](MUSIC-MOTION.md)

These pages document the Media Pose Pipeline prototypes created as part of the 2nd Vision-only design patterns.

To start the app:

```bash
python motion-app.py
```

Based on the limitations of using IMU sensor data to measure full body motion, a 2nd design pattern was explored that used video to interpret full body poses and motion. Multiple technologies were explored but MediaPipe's perception pipeline proved to be the most effective. These prototypes started with demonstrating the effectiveness of MediaPipe in interpreting full body positions such as Yoga poses. Then, the media pose sensors were used to drive the Equalizer built in Prototype G in Design Pattern 1.

## The prototypes

- **Prototype A** — [Hands Detector](MP-PIPELINE-A.md)
- **Prototype B** — [Yoga Pose Detector](MP-PIPELINE-B.md)
- **Prototype C** — [Full Body Equalizer](MP-PIPELINE-C.md)

## MediaPipe Sensors

**MediaPipe** is Google’s open-source AI framework for building perception pipelines (vision, audio, etc.). MediaPipe Vision exposes **three** main landmark solutions: **Hands**, **Pose**, and **Face Mesh**. 

1. **Hands** — up to two hands per frame (21 landmarks per hand).
2. **Full-body pose** — one skeleton per frame (33 landmarks).
3. **Face Mesh** — one face per frame (468 landmarks).

All landmarks are reported in **normalized image coordinates**: x and y typically in `[0, 1]`, with y increasing downward. Each landmark also has a **z** value (depth); the origin for z differs by solution (see below).

**MediaPipe** uses pre-trained neural networks that run **on-device**; because everything is local, it is fast, lightweight, reliable, and well-suited for real-time systems. On a modern Mac, typical performance:

| Model | Typical FPS | Latency |
|-------|-------------|---------|
| Pose (BlazePose) | 30–60+ FPS | ~5–15 ms |
| Hands | 60+ FPS | ~3–8 ms |
| Face Mesh | 30–60 FPS | ~8–20 ms |

### MediaPipe Hands

`mp.solutions.hands.Hands` — up to 2 hands per frame, **21 landmarks** per hand.

- **Per landmark:** `x`, `y`, `z` in normalized image coordinates (z: depth with wrist as origin; smaller = closer to camera).
- **Handedness:** Left/right label per detected hand.

All 21 landmarks (index matches `HandLandmark` in code):

| Index | Landmark         | Index | Landmark          | Index | Landmark        |
| ----: | ---------------- | ----: | ----------------- | ----: | --------------- |
|     0 | WRIST            |     7 | INDEX_FINGER_TIP  |    14 | RING_FINGER_DIP |
|     1 | THUMB_CMC        |     8 | MIDDLE_FINGER_MCP |    15 | RING_FINGER_TIP |
|     2 | THUMB_MCP        |     9 | MIDDLE_FINGER_PIP |    16 | PINKY_MCP       |
|     3 | THUMB_IP         |    10 | MIDDLE_FINGER_DIP |    17 | PINKY_PIP       |
|     4 | THUMB_TIP        |    11 | MIDDLE_FINGER_TIP |    18 | PINKY_DIP       |
|     5 | INDEX_FINGER_MCP |    12 | RING_FINGER_MCP   |    19 | PINKY_DIP       |
|     6 | INDEX_FINGER_PIP |    13 | RING_FINGER_PIP   |    20 | PINKY_TIP       |

### MediaPipe Pose (full-body)

`mp.solutions.pose.Pose` — full-body **33 landmarks** per frame.

- **Per landmark:** `x`, `y`, `z` (z relative to hip center), and `visibility` in `[0, 1]`.

All 33 landmarks (index matches `PoseLandmark` in code):

| Index | Landmark        | Index | Landmark         | Index | Landmark          |
|------:|-----------------|------:|------------------|------:|-------------------|
| 0     | NOSE            | 11    | LEFT_SHOULDER    | 23    | LEFT_HIP          |
| 1     | LEFT_EYE_INNER  | 12    | RIGHT_SHOULDER   | 24    | RIGHT_HIP         |
| 2     | LEFT_EYE        | 13    | LEFT_ELBOW       | 25    | LEFT_KNEE         |
| 3     | LEFT_EYE_OUTER  | 14    | RIGHT_ELBOW      | 26    | RIGHT_KNEE        |
| 4     | RIGHT_EYE_INNER | 15    | LEFT_WRIST       | 27    | LEFT_ANKLE        |
| 5     | RIGHT_EYE       | 16    | RIGHT_WRIST      | 28    | RIGHT_ANKLE       |
| 6     | RIGHT_EYE_OUTER | 17    | LEFT_PINKY       | 29    | LEFT_HEEL         |
| 7     | LEFT_EAR        | 18    | RIGHT_PINKY      | 30    | RIGHT_HEEL        |
| 8     | RIGHT_EAR       | 19    | LEFT_INDEX       | 31    | LEFT_FOOT_INDEX   |
| 9     | MOUTH_LEFT      | 20    | RIGHT_INDEX      | 32    | RIGHT_FOOT_INDEX  |
| 10    | MOUTH_RIGHT     | 21    | LEFT_THUMB       |       |                   |
|       |                 | 22    | RIGHT_THUMB      |       |                   |

### MediaPipe Face Mesh

`mp.solutions.face_mesh.FaceMesh` — **468 landmarks** per face (one face per frame by default; optional multi-face mode available).

- **Per landmark:** `x`, `y`, `z` in normalized image coordinates (z: depth relative to the face; smaller = closer to camera). No separate visibility score; landmarks are always reported for the detected face region.
- **Output:** A triangulated 3D mesh over the facial surface (lips, eyes, eyebrows, face oval, etc.).

Available sensor data (summary; full topology has 468 indices):

| Data | Description |
|------|--------------|
| **Landmark count** | 468 (indices 0–467) |
| **Coordinates** | Normalized x, y, z per landmark; same image coordinate convention as Hands and Pose |
| **Topology** | 3D facial surface mesh. See [MediaPipe Face Mesh](https://developers.google.com/mediapipe/solutions/vision/face_landmarker) for the full landmark index map and connections. |

For official API and landmark details, see [MediaPipe Solutions (Vision)](https://ai.google.dev/edge/mediapipe/solutions/about).

---

