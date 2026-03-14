# Music Motion

A project for creating music through body motion, combining MediaPipe pose detection and IMU sensors with real-time audio processing.

For first time installation, refer to [INSTALL.md](documentation/INSTALL.md) in the documentation folder.

## Prerequisites

- **Python 3.11** 
- **Virtual environment** (recommended):
- Dependencies listed in `requirements-lock.txt`

## Getting started — Posterboard docs

Once Python and dependencies are installed, information and documentation on this project can be accessed as follows:

1. **Start a local HTTP server** (from the project root):

```bash
source .venv/bin/activate   # if not already active
python -m http.server 8000
```

1. **Open the posterboard in your browser:**
  - **[http://localhost:8000/posterboard/](http://localhost:8000/posterboard/)**
   From there you can use the nav to open the main poster pages (Design Constraints, Design Patterns, Sensor Fusion Pipeline, etc.) and the **Docs** link for project documentation.
2. **Stop the server** when done: press `Ctrl+C` in the terminal.

## More documentation

- **Project layout and apps** — [documentation/PROJECT_ORGANIZATION.md](documentation/PROJECT_ORGANIZATION.md) (how to run each application, key applications, dependencies).
- **Install and setup** — [documentation/INSTALL.md](documentation/INSTALL.md).
- **Quick Start** — [documentation/QUICK-START.md](documentation/QUICK-START.md) to start the app subsequent to first time installation.
- **IMU setup and usage** — [documentation/IMU.md](documentation/IMU.md).

