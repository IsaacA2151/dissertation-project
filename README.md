# Spatial Audio Navigation Device

A wearable device that uses spatial audio to convey direction to visually impaired users for indoor navigation. Built on a Raspberry Pi Zero 2 W, kept under a £50 budget so it stays accessible rather than joining the expensive assistive tech products already out there.

## The problem

Existing aids like the white cane or GPS based apps each have well documented limitations, particularly indoors where satellite signal is unavailable and spatial awareness is necessary. When vision becomes impaired, hearing becomes the primary sense for spatial awareness, which makes audio a natural option for navigation aids.

This device renders a virtual sound source at a user defined position and updates it in real time as the user rotates their head, so the sound appears fixed at one point in the room. The user can then orient themselves towards the sound, which could be placed on a doorway or object, simply by turning their head.

## How it works

An MPU-6050 IMU tracks head orientation using a Madgwick filter, combining accelerometer and gyroscope data to produce a stable, drift corrected orientation estimate. This orientation is used to select the nearest matching Head-Related Transfer Function (HRTF) pair from the CIPIC dataset, a set of real acoustic measurements of how sound is filtered by the head and ears before reaching each eardrum. The selected HRTF pair is convolved with an audio signal in real time using FFT based convolution, and streamed out over a USB DAC to headphones so the sound is perceived as coming from a fixed point in the room regardless of head rotation.

A Flask web interface, reachable from any device on the same local network, lets the user set the target direction, control volume, and switch between HRTF subject measurements to find the one that best suits their own anatomy.

```
IMU (MPU-6050) --I2C--> Madgwick filter --> yaw / pitch
                                               |
                                               v
CIPIC HRTF dataset --> nearest HRIR lookup --> FFT convolution --> stereo output --> headphones
                                               ^
                                               |
                          Flask web interface (target direction, volume, HRTF selection)
```

## Hardware

| Component | Purpose | Cost |
|---|---|---|
| Raspberry Pi Zero 2 W | Runs software, Wi-Fi for SSH access | £25 |
| MPU-6050 | Head orientation via accelerometer and gyroscope | £4 |
| USB DAC dongle | Converts digital audio to analogue stereo output at 48kHz | £3 |
| Headphones | Stereo playback for binaural audio | £10 |
| USB power bank | Enables the device to be portable | £10 |
| Elastic sports headband | Mounting platform for IMU and wiring | £1 |
| Micro USB OTG adapter | Connects USB audio adapter to Pi Zero 2 W | £2 |
| **Total** | | **£55** |

The enclosures for the Pi and IMU were designed in Onshape and 3D printed in PLA, mounted directly onto the elastic headband via slots on either side through which the headband passes.

## Software stack

Implemented entirely in Python 3, split across four modules so each could be developed and tested in isolation.

- **`imu_driver.py`** handles communication with the MPU-6050 and creates a stable orientation estimate for the rest of the pipeline.
- **`sofa_reader.py`** loads the CIPIC dataset at startup and provides HRIR pairs on request.
- **`spatial_engine.py`** is the core processing module, bringing the orientation data and HRIR lookup together into a continuous stereo audio stream.
- **`app.py`** provides the Flask web interface, giving control to the user without requiring a display or keyboard connected to the Pi.

## Results

| Specification | Target | Result |
|---|---|---|
| Latency | < 80 ms | ~25 ms |
| Orientation accuracy | < 5° yaw error | < 2.5° across all tested positions |
| Spatialisation accuracy | > 75% correct response rate | 76.7% overall (120 trials across 8 azimuths) |
| Total component cost | < £50 | £55 |
| Total component weight | < 100g | Met |

During normal use, rotating left and right produced a clear, smooth and responsive shift in the perceived source direction, and the sound felt anchored in space rather than attached to the head. Performance was strongest at 90° and 270° (93.3% and 86.7% correct) and weakest at 180° and 225° (60% and 66.7%), with most incorrect responses being front and back reversals. This is a well documented limitation of non-individualised HRTFs, since without personal pinnae measurements the spectral cues that distinguish front from back sources are often insufficient.

## Limitations and future work

The device currently only handles one virtual sound source at a fixed position set manually through the web interface. In a real scenario a user would be surrounded by multiple objects, none of which the device is currently aware of, so in its current form it is more of a directional orientation tool than a full navigation system. The most impactful direction for future work would be to integrate an object detection system, such as a depth camera or ultrasonic array, to automatically identify objects in the room and feed their positions to the spatial engine.

The absence of a magnetometer also means the system has no absolute heading reference, so yaw drift accumulates over time and requires the user to periodically recalibrate by returning to a known reference orientation. Jumper wire connections were another weak point, introducing occasional contact failures when the headband flexed. Replacing them with soldered stranded wire would be a straightforward improvement.

## Try it yourself

```bash
# On the Raspberry Pi Zero 2 W (Raspberry Pi OS, I2C enabled)
pip install -r requirements.txt
python app.py
# Open http://<pi-ip-address>:5000 from any device on the same network
```

Requires a CIPIC format SOFA HRTF file (see `sofa_reader.py`) and a USB audio DAC connected via the Pi's micro USB OTG port.

## Background

Built as my final year dissertation for BEng Electrical and Electronic Engineering / Electronic and Computer Engineering at Newcastle University, 2026. Full report with literature review, testing methodology and design iteration log available [here](./dissertation.pdf).
