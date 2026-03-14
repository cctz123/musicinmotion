# IMU Pipeline

← [Music in Motion](MUSIC-MOTION.md)

These pages document the IMU Pipeline prototypes created as part of the 1st IMU-only design pattern.  For information on initializing the IMUs, refer to [Quick Start](QUICK-START.md)

To start the app:

```bash
python motion-app.py

# to access the IMU viewer
python -m imu_viewer.app
```

After getting the IMUs working using the [IMU Viewer](IMU-VIEWER.md) app, a series of prototypes were built to test how motion can be tracked with IMU sensors.

The first two prototypes tested translating sensor readings to movement, by allowing the user to control a shape on the screen with the IMU device.

Subsequent prototypes built on the learnings from those prototypes to:
- control pitch, pan, volume and timbre of an auditory tone
- add support for multiple IMUs (so, for example, one could be held in each hand)
- manipulate actual music as it is being played in real time

## The prototypes

- **Prototype A** — [Large IMU Movement](IMU-PIPELINE-A.md)
- **Prototype B** — [Precise IMU Movement](IMU-PIPELINE-B.md)
- **Prototype C** — [Controlling Pitch + Pan](IMU-PIPELINE-C.md)
- **Prototype D** — [Controlling Pitch + Pan + Volume](IMU-PIPELINE-D.md)
- **Prototype E** — [Dualing IMUs](IMU-PIPELINE-E.md)
- **Prototype F** — [Pitch + Pan + Timbre](IMU-PIPELINE-F.md)
- **Prototype G** — [Music Control / Equalizer](IMU-PIPELINE-G.md)

## IMU Motion Sensors

Based on the work on [IMU Viewer](IMU-VIEWER.md), the following sensor data was used to interpret and map motion to sound:

- **Roll** -- tilting the IMU left and right, like the wings of a plane.  
- **Pitch** -- tilting the IMU's front up or down, like tilting the nose of a plane so it dives or rises  
- **Yaw** -- turning the IMU left or right  
- **X-Accel** -- acceleration (measured in terms of g-force) side-and-side
- **Y-Accel** -- acceleration (measured in terms of g-force) forward-and-back
- **Z-Accel** -- acceleration (measured in terms of g-force) up-and-down

---

