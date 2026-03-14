# Music Motion Package

This package is the refactored version of `motion-app.py`, organized into a modular structure.

## Package Structure

```
music-motion/
├── __init__.py              # Package initialization
├── __main__.py              # Entry point (python -m music-motion)
├── main.py                  # Alternative entry point
├── config.py                # Configuration management
│
├── utils/                   # Shared utilities
│   ├── constants.py         # All constants
│   ├── math_utils.py        # Math helpers
│   └── ui_utils.py          # UI helpers
│
├── audio/                   # Audio processing
│   ├── synthesis.py         # Waveform generation
│   ├── effects.py           # EQ, filters, limiting
│   ├── player.py            # Audio stream management
│   └── utils.py             # Audio conversions/mappings
│
├── imu/                     # IMU functionality
│   ├── reader.py            # IMU reader wrapper
│   ├── visualization/       # Visualization widgets
│   │   ├── base.py          # ImuSquareWidget (base)
│   │   ├── box.py           # ImuBoxWidget (Method A)
│   │   └── dual_square.py   # ImuDualSquareWidget (Method E)
│   └── methods/              # IMU control methods
│       ├── base.py          # Base method class
│       ├── method_a.py      # Box visualization
│       ├── method_b.py      # Square visualization
│       ├── method_d.py      # Loudness control
│       ├── method_f.py      # Timbre control
│       └── method_g.py      # Audio file + EQ
│
├── ui/                      # UI components
│   ├── main_window.py       # MainWindow class
│   ├── widgets/             # Reusable widgets
│   │   ├── pose_card.py     # PoseCard
│   │   └── imu_stats.py     # ImuStatsWidget
│   └── tabs/                 # Tab widgets
│       ├── base_tab.py      # Base tab class
│       ├── imu_prototypes.py # IMU Prototypes tab
│       ├── ml_stream.py      # MP Hands Demo tab
│       ├── yoga_pose.py      # Yoga Pose Detector tab
│       └── coming_soon.py    # Coming Soon tab
│
└── ml/                      # Machine learning
    ├── hands.py             # MediaPipe hands
    └── yoga.py              # Yoga pose detection
```

## Migration Status

### Completed
- ✅ Package structure created
- ✅ Utils layer (constants, math_utils, ui_utils)
- ✅ Audio layer (synthesis, effects, player, utils)
- ✅ Base IMU visualization (base.py, box.py)
- ✅ Entry points (__main__.py, main.py)

### In Progress
- 🔄 IMU methods extraction
- 🔄 UI components extraction
- 🔄 ML components extraction

### Pending
- ⏳ Complete method extraction (A, B, D, E, F, G)
- ⏳ Complete UI extraction (tabs, widgets, main_window)
- ⏳ Complete ML extraction
- ⏳ Update all imports
- ⏳ Testing

## Usage

Once migration is complete:

```bash
# Run as module
python -m music-motion

# Or run directly
python -m music-motion.main
```

## Migration Guide

See `MIGRATION.md` for detailed steps on completing the migration.

