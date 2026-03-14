# Music in Motion - First Time Installation

This document details the first-time installation for Music in Motion, a project for creating music through body motion, combining MediaPipe pose detection and IMU sensors with real-time audio processing.

## Prerequisites

This installation assumes macOS. The following steps should be done once during initial setup.

### Install Homebrew (macOS)

If you don't already have [Homebrew](https://brew.sh/) (the package manager used for Python and other tools), install it first:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the on-screen instructions. After installation, you may need to add Homebrew to your PATH (the installer will show the exact commands for your shell).

### Install Python 3.11

```bash
brew install python@3.11
python3.11 --version   # should be 3.11.x
```

### Activate Virtual Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# or:  .venv\Scripts\activate   # Windows
```

In the future, before using Music in Motion, first execute `source .venv/bin/activate` 

### Install Dependencies

Using requirements-lock.txt is safer as it ensures the version number that works will be installed.

```bash
pip install -r requirements-lock.txt
```

### Start the App

Refer to [Quick Start](QUICK-START.md)


