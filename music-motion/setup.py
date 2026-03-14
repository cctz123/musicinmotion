"""Setup configuration for music-motion package."""

from setuptools import setup, find_packages

setup(
    name="music-motion",
    version="0.1.0",
    description="Motion-controlled music application",
    packages=find_packages(),
    install_requires=[
        "mediapipe",
        "opencv-python",
        "numpy",
        "PyQt5",
        "librosa",
        "sounddevice",
        "scipy",
        "pyserial>=3.5",
        "matplotlib",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "music-motion=music_motion.main:main",
        ],
    },
)

