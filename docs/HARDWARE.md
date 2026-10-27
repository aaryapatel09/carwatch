# First hardware target

Use a **single Logitech C920s connected by USB to the development computer** for the first supervised, stationary car-side test. It provides 1080p at 30 fps, a 78° diagonal field of view and a physical privacy shutter according to [Logitech's specifications](https://www.logitech.com/en-us/shop/p/c920s-pro-hd-webcam.960-001257). This is a bench-test choice; this repository has not established device compatibility or automotive suitability.

Position the camera on a stable stand so the complete person and the target door remain visible. Select its local camera index in the app, calibrate the ground and handle regions on that view, and explicitly start a short session. Record acquisition, frame delivery, Stop, the automatic timeout, disconnect handling, and detection latency. Change distance, lighting and partial occlusion before treating any working demonstration as representative. The app does not capture microphone audio.

The current live input is an OpenCV local-camera index. Raspberry Pi CSI cameras require a capture adapter through the supported Raspberry Pi camera stack before they can replace that input. A possible later edge prototype is a Raspberry Pi with Camera Module 3 Wide modules: the manufacturer specifies 102° horizontal / 120° diagonal field of view, and NoIR versions need infrared illumination for night viewing. These specifications do not establish coverage, processing rate, power consumption or thermal behavior for Carwatch. [Camera specifications](https://www.raspberrypi.com/documentation/accessories/camera.html), [product details](https://www.raspberrypi.com/products/camera-module-3/).

## What the car-mounted version still needs

Per-camera calibration makes the software independent of a particular car's image geometry. Universal physical mounting is a separate mechanical requirement. A single view cannot establish complete coverage of both sides or the underbody; the placement and number of cameras must follow measured blind spots on actual vehicles. The current batch workflow processes views independently and does not prove a working simultaneous multi-camera system.

Measure the complete assembly's energy use and heat, design and test its enclosure and mounts, and establish reliable offline/phone-delivery behavior before an unattended parked-car trial. No mount, automotive power connection, cellular modem or phone-delivery path has been qualified by this project. No hardware has been purchased or activated during development.
