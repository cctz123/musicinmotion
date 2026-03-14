# Music in Motion — UI layout (mmotion.py)

This document describes the visual and structural hierarchy of the main Music in Motion application.

---

## 1. Overview

The Music in Motion app is divided into top and bottom sections, divided by a **vertical splitter**:

- **Top band**: Fixed max height; contains a **horizontal splitter** with two panels — **video (left)** and **play + timeline (right)**.
- **Bottom band**: Remaining height; contains a **horizontal splitter** with two panels — **motion sensor (left)** and **audio control (right)**, split 50/50.

Both bottom panels share the same structure: a **title label**, then a **QScrollArea** (transparent background, sunken border) whose content is built by `_init_stats_ui` (motion) or `_init_controls_ui` (audio).

---

## 2. Window level

- **Class**: `TimbreControl3Window(QMainWindow)`
- **Title**: "Music in Motion"
- **Central widget**: A single `QWidget` with a `QVBoxLayout` (**main_layout**):
  - Margins: 0
  - Spacing: 0
  - Single child: **main_splitter** (vertical)

---

## 3. Main splitter (TOP | BOTTOM)

- **Widget**: `QSplitter(Qt.Vertical)` — **main_splitter**
- **Children** (in order):
  1. **top_widget** (top band)
  2. **bottom_splitter** (bottom band)
- **Initial sizes**: Top = 40% of default window height; bottom = remainder. Ratio controlled by `TOP_DEFAULT_HEIGHT_RATIO`.

---

## 4. Top band

- **Widget**: **top_widget** (`QWidget`)
  - `setMaximumHeight(TOP_MAX_HEIGHT)`
- **Layout**: **top_layout** (`QVBoxLayout`)
  - Margins: 0, 0, 0, 0
  - Spacing: 0
  - Single child: **top_h_splitter** (`QSplitter(Qt.Horizontal)`)

### 4.1 Top horizontal splitter

- **Widget**: **top_h_splitter**
- **Children** (left → right):
  1. **top_left_widget** — Video panel
  2. **top_right_widget** — Play + timeline panel
- **Initial sizes**: Left = remaining width; right = `TOP_LEFT_MAX_WIDTH` (650 px).

---

### 4.2 Top-left panel: Video

- **Widget**: **top_left_widget** (`QWidget`)
  - `setMinimumWidth(TOP_RIGHT_MIN_WIDTH)` — ensures video column has at least 720 px.
- **Layout**: **top_left_layout** (`QVBoxLayout`)
  - Margins: 0, 0, 0, 0
  - Spacing: 10
- **Content** (from `_init_video_ui(top_left_layout)`):
  - **video_label** (`QLabel`) — camera/video display, styled (dark background, border). Stretch factor 1.

---

### 4.3 Top-right panel: Play + timeline

- **Widget**: **top_right_widget** (`QWidget`)
  - `setMaximumWidth(TOP_LEFT_MAX_WIDTH)` — play + timeline column capped at 650 px.
- **Layout**: **top_right_layout** (`QVBoxLayout`)
  - Margins: 20, 20, 20, 20
  - Spacing: 10
- **Content** (from `_init_play_timeline_ui(top_right_layout)`):
  - **Title**: `QLabel` "Music in Motion" (Arial 18 Bold)
  - **button_layout** (`QHBoxLayout`): stretch, **play_button** (`QPushButton` "Play"), stretch
  - **progress_layout** (`QVBoxLayout`, spacing 5):
    - **time_layout** (`QHBoxLayout`): current_time_label, progress_bar (stretch 1), total_time_label
  - **load_button** (`QPushButton` "Load music file")

---

## 5. Bottom band

- **Widget**: **bottom_splitter** (`QSplitter(Qt.Horizontal)`)
- **Children** (left → right):
  1. **motion_sensor_widget** — Motion sensor / stats panel
  2. **audio_control_widget** — Audio control panel
- **Initial sizes**: 50% / 50% of window width.

---

### 5.1 Bottom-left panel: Motion sensor

- **Widget**: **motion_sensor_widget** (`QWidget`)
- **Layout**: **motion_sensor_layout** (`QVBoxLayout`)
  - Margins: `BOTTOM_PANEL_MARGINS` (10) on all sides
  - Spacing: `BOTTOM_PANEL_VERTICAL_SPACING` (10)
  - Alignment: `Qt.AlignTop`
- **Content** (from `_init_stats_ui(motion_sensor_layout)`):
  1. **motion_sensor_title** — `QLabel` "Sensor Readings" (Arial 18 Bold)
  2. **motion_sensor_scroll** — `QScrollArea`
    - `setWidgetResizable(True)`
    - `setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)`
    - `setStyleSheet(SCROLL_AREA_STYLESHEET)` — transparent background, sunken border
    - **Child widget**: **motion_sensor_scroll_widget** (`QWidget`) with **scroll_layout** (`QVBoxLayout`):
      - Section label: "Pose Features (MediaPipe)" (blue)
      - Two-column layout: left/right hand stats (hand_height, arm_extension, elbow_bend, lateral_offset, hand_spread)
      - Section label: "Dynamics Features (IMU)" (red)
      - Two-column layout: activity, jerk, shake_energy (L/R and activity_global)
      - Section label: "Confidence" (green)
      - Two-column layout: mediapipe_confidence, imu_confidence_L/R
      - Stretch at end

---

### 5.2 Bottom-right panel: Audio control

- **Widget**: **audio_control_widget** (`QWidget`)
- **Layout**: **audio_control_layout** (`QVBoxLayout`)
  - Margins: `BOTTOM_PANEL_MARGINS` (10) on all sides
  - Spacing: `BOTTOM_PANEL_VERTICAL_SPACING` (10)
  - Alignment: `Qt.AlignTop`
- **Content** (from `_init_controls_ui(audio_control_layout)`):
  1. **audio_control_title** — `QLabel` "Audio Control" (Arial 18 Bold)
  2. **audio_control_scroll** — `QScrollArea`
    - Same behavior as motion_sensor_scroll (resizable widget, no horizontal scrollbar, `SCROLL_AREA_STYLESHEET`)
    - **Child widget**: **audio_control_scroll_widget** (`QWidget`) with **scroll_content_layout** (`QVBoxLayout`)
      - Margins 12, spacing `AC_VERTICAL_SPACING`
      - Cutoff (label, Smooth/Sensor checkboxes, slider, value display)
      - Resonance (label, Smooth checkbox, slider, value display)
      - Attack, Brightness, Tremolo, Mode, Volume sliders (each with min/max labels and value display)
      - Stretch at end

---

## 6. Hierarchy summary (tree)

```
QMainWindow (TimbreControl3Window)
└── central_widget (QWidget)
    └── main_layout (QVBoxLayout)
        └── main_splitter (QSplitter vertical)
            ├── top_widget (QWidget, max height TOP_MAX_HEIGHT)
            │   └── top_layout (QVBoxLayout)
            │       └── top_h_splitter (QSplitter horizontal)
            │           ├── top_left_widget [Video] (QWidget, min width TOP_RIGHT_MIN_WIDTH)
            │           │   └── top_left_layout
            │           │       └── video_label
            │           └── top_right_widget [Play + timeline] (QWidget, max width TOP_LEFT_MAX_WIDTH)
            │               └── top_right_layout
            │                   ├── title "Music in Motion"
            │                   ├── play_button, progress_bar, time labels
            │                   └── load_button
            └── bottom_splitter (QSplitter horizontal, 50/50)
                ├── motion_sensor_widget [Motion sensor]
                │   └── motion_sensor_layout
                │       ├── motion_sensor_title "Sensor Readings"
                │       └── motion_sensor_scroll (QScrollArea)
                │           └── motion_sensor_scroll_widget
                │               └── scroll_layout (Pose, Dynamics, Confidence sections)
                └── audio_control_widget [Audio control]
                    └── audio_control_layout
                        ├── audio_control_title "Audio Control"
                        └── audio_control_scroll (QScrollArea)
                            └── audio_control_scroll_widget
                                └── scroll_content_layout (sliders + checkboxes)
```

---

## 7. Consolidated constants


| Constant                        | Value                                                                                                      | Usage                                                                        |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **Window**                      |                                                                                                            |                                                                              |
| `DEFAULT_WINDOW_WIDTH`          | 1500                                                                                                       | Initial window width (px)                                                    |
| `DEFAULT_WINDOW_HEIGHT`         | 900                                                                                                        | Initial window height (px)                                                   |
| `MIN_WINDOW_WIDTH`              | 1200                                                                                                       | Minimum window width (px)                                                    |
| `MIN_WINDOW_HEIGHT`             | 700                                                                                                        | Minimum window height (px)                                                   |
| **Top band**                    |                                                                                                            |                                                                              |
| `TOP_DEFAULT_HEIGHT_RATIO`      | 0.40                                                                                                       | Top band is 40% of window height by default                                  |
| `TOP_MAX_HEIGHT`                | 450                                                                                                        | Maximum height of top band (px)                                              |
| `TOP_LEFT_MAX_WIDTH`            | 650                                                                                                        | Play + timeline column max width (px) — used for **top-right** panel         |
| `TOP_RIGHT_MIN_WIDTH`           | 720                                                                                                        | Video column min width (px) — used for **top-left** panel                    |
| **Bottom panels (both)**        |                                                                                                            |                                                                              |
| `BOTTOM_PANEL_MARGINS`          | 10                                                                                                         | Margins for motion_sensor_layout and audio_control_layout                    |
| `BOTTOM_PANEL_VERTICAL_SPACING` | 10                                                                                                         | Vertical spacing for motion_sensor_layout and audio_control_layout           |
| `SCROLL_AREA_STYLESHEET`        | `"QScrollArea { background-color: transparent; border: 1px solid palette(shadow); border-style: inset; }"` | Shared style for both bottom-panel QScrollAreas (transparent, sunken border) |
| **Audio control (sliders)**     |                                                                                                            |                                                                              |
| `AC_VERTICAL_SPACING`           | 15                                                                                                         | Vertical spacing in scroll_content_layout (audio control scroll content)    |
| `SLIDER_LABEL_FONT`             | 12                                                                                                         | Font size for min/max labels (e.g. "0.0", "1.0")                             |
| `SLIDER_WIDTH`                  | 320                                                                                                        | Min/max width for sliders (px)                                               |
| `SLIDER_VALUE_FONT`             | 14                                                                                                         | Font size for value display next to each slider                              |


Note: Top-left/top-right naming in constants is from a “play column” vs “video column” perspective: **TOP_LEFT_MAX_WIDTH** limits the **play+timeline** (right) column; **TOP_RIGHT_MIN_WIDTH** ensures the **video** (left) column has minimum width.