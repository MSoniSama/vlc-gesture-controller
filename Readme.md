# VLC Gesture Controller

Control VLC on Windows with two-handed webcam gestures: adjust volume, seek, play/pause, and navigate chapters or playlist videos. Your left hand enables control; your right hand operates playback.

The controller runs in the background and only controls VLC while VLC is the foreground app. Hand tracking runs locally using MediaPipe and OpenCV.

## Requirements

- Windows 11.
- Standard 64-bit Python **3.14**, with the `py` launcher installed.
- VLC installed separately and a working webcam.
- Internet access for first-time setup.

## Quick start

1. Download or clone the project and open the **VLC Gesture Control** folder. Extract downloaded ZIP files before running anything.
2. Double-click **Set Up.bat** and press **Y**. It creates a local `.venv`, installs dependencies and downloads the hand model. You can retry setup after a failure; it reuses the existing environment and completed model download.
3. Open VLC and load a video or playlist.
4. Double-click **Run.bat**, then bring VLC to the foreground.
5. Raise your left index finger to enable right-hand controls, or use the persistent toggle below.
6. Run **Stop.bat** when finished to release the webcam and stop the controller.

Setup errors remain visible in the terminal. Launchers do not install dependencies automatically.

## Activation

Use your **anatomical left hand**, regardless of where it appears on screen.

| Gesture                                                                          | Behavior                                                                                                                               |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Left index extended; other fingers folded                                        | Temporary **HOLD** activation after a brief hold. Keep this pose while using right-hand controls. Thumb position does not matter.      |
| Both hands making Shaka (thumb and little finger extended, other fingers curled) | Hold for about half a second to toggle persistent control ON/OFF. Visibly release Shaka on **both hands** before controlling playback. |

Two ascending beeps mean toggle ON; one lower beep means OFF. Persistent activation lets you remove your left hand afterward. Leaving VLC resets activation to OFF and releases the webcam; returning requires activation again.

## Right-hand controls

Start from a comfortable neutral position with your hand visible to the camera. Movement is mirrored by default.

| Pose                                                      | Movement                                                      | VLC action                                                           |
| --------------------------------------------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------- |
| Index extended; middle, ring and little fingers folded    | Move the index fingertip up/down relative to its knuckle      | Volume up/down                                                       |
| Index and middle extended; ring and little fingers folded | Move the two fingertips right/left relative to their knuckles | Continuous small forward/backward seeks using **Shift + Right/Left** |
| Index, middle and ring extended; little finger folded     | Tilt the three fingertips right/left relative to the wrist    | Next/previous chapter using **Shift + N/P**                          |
| Closed fist                                               | Sweep the hand/arm right/left                                 | Next/previous playlist video using **N/P**                           |
| Open palm, including thumb                                | Hold briefly (about 0.25 seconds)                             | Play/pause using **Space**                                           |

Volume and seeking require new movement; holding still does not repeat commands. Thumb position is ignored for volume and fist recognition.

Chapter/video navigation sends one command per outward movement. Return to the original neutral position and briefly settle to rearm without releasing the pose. The return movement does not trigger the opposite command. You can also release/change pose to establish a new neutral position. Play/pause requires a neutral pose between activations.

The intended seek increment is **3 seconds**. VLC determines the actual jump length: check that its **Very short backward/forward jump** hotkeys are Shift + Left/Right and its **Very short jump length** is 3 seconds. The controller does not change VLC preferences.

## Launchers and preview

| File             | Purpose                                                               |
| ---------------- | --------------------------------------------------------------------- |
| `Set Up.bat`     | First-time setup; asks Y/N before beginning                           |
| `Run.bat`        | Background launch; a terminal may flash briefly                       |
| `Run-Hidden.vbs` | Launch without a visible terminal                                     |
| `Run-Test.bat`   | Visible console; choose **Y** for preview or **N** for normal control |
| `Stop.bat`       | Graceful shutdown for any launcher                                    |

Only one instance per project folder and Windows login session can run, including preview. Stop a background instance before starting `Run-Test.bat`.

Preview works independently of VLC focus and **disables all VLC commands**. It shows hand labels, landmarks, activation, gesture state, movement thresholds and diagnostic FPS. Press **Q/Esc**, close the preview, or use **Ctrl+C** to exit. In visible normal mode, Ctrl+C also stops the controller.

## Settings and logs

Edit [config.py](config.py), then restart the controller. Common settings:

- `CAMERA_INDEX`: choose a different webcam.
- `MIRROR` / `SWAP_HANDEDNESS`: adjust the preview/direction or anatomical hand labels for your camera. Check labels in preview before changing them.
- `MOVEMENT_TRACKING`: defaults to `"fingertip"`; `"palm"` uses full-hand movement for volume/seek.
- `FINGERTIP_*`, `CHAPTER_*`, `VIDEO_*`, `NAVIGATION_*`: movement sensitivity and rearming.
- `PROCESSING_MODE`: `"auto"` chooses threaded LIVE_STREAM on systems with at least eight logical CPUs, otherwise single VIDEO mode. You can select `"threaded"` or `"single"` explicitly.

Capture defaults to **640×480 at 30 FPS**. Actual throughput depends on the camera and hardware. Timestamped logs in `logs/` include startup/shutdown, commands and periodic FPS/state diagnostics. Startup removes controller logs older than **30 days**, based on their filename timestamps.

## Gotchas and troubleshooting

- **Nothing happens:** confirm VLC has focus, activation is enabled, and you are not in preview. Use `Run-Test.bat` and inspect the latest log. Chapter navigation needs chaptered media; video navigation needs other playlist entries.
- **Wrong hand controls activation:** check Left/Right labels in preview with each hand separately. Camera mirroring varies; adjust `SWAP_HANDEDNESS` if needed.
- **Tracking pauses:** use good lighting, keep hands visible and separated, and avoid large movements toward/away from the camera. Uncertain hand identities pause affected controls.
- **Webcam will not open:** check Windows camera permissions, `CAMERA_INDEX`, and whether another app is using it.
- **Shortcuts do not work:** run VLC and the controller at the same normal privilege level. Held physical keys/modifiers suppress keyboard commands. Custom VLC hotkeys must match the mappings above.
- **Volume wheel messages are ignored:** assign **U/D** to VLC's ordinary Volume up/down hotkeys, then set `VOLUME_MODE = "keyboard"`. The optional seek fallback uses **J/L** with `SEEK_MODE = "keyboard"`; bind them to VLC's very-short jump actions first.
- **Focus changes:** keyboard delivery checks VLC foreground immediately before sending, but a focus change during Windows input delivery cannot be completely excluded. Avoid switching apps mid-gesture.
- **Stop reports shutdown pending:** a blocked camera/model call can delay cleanup. Inspect the log; Stop does not forcibly kill Python processes.
- **MediaPipe warnings appear:** model feedback/NORM_RECT warnings can be harmless when tracking works. Use preview and diagnostics to distinguish warnings from actual failures.

Normal use requires no online service or model downloads. The controller itself makes no network requests during operation; third-party package behavior is separate.

## Project files

`main.py` coordinates startup and processing; `gestures.py` handles playback gestures; `activation.py` handles activation and hand identity; `pipeline.py` handles capture/inference; `vlc_control.py` delivers VLC commands; `lifecycle.py` and `stop_controller.py` manage the instance and shutdown.

The virtual environment, logs and downloaded models are excluded from Git. For historical implementation detail, see [Development Notes](DEVELOPMENT_NOTES.md).
