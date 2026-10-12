# VLC Gesture Controller — Development Notes

## File map

| File                                     | Responsibility                                                                                                                                         |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [main.py](main.py)                       | Startup logging and retention, configuration validation, camera/model lifecycle, main processing loop, command authorization, diagnostics and preview. |
| [config.py](config.py)                   | Centralized camera settings, gesture thresholds, timing, movement modes, sounds and fallback keys.                                                     |
| [activation.py](activation.py)           | Stable left/right hand assignment, left-index HOLD, both-hand Shaka toggle, authorization and audio cues.                                              |
| [gestures.py](gestures.py)               | Right-hand pose classification, confirmation, movement accumulation, play/pause locking and navigation rearming. No camera or Windows dependencies.    |
| [pipeline.py](pipeline.py)               | Capture worker with a latest-frame slot; single-flight MediaPipe LIVE_STREAM submission and callback/result transfer.                                  |
| [vlc_control.py](vlc_control.py)         | Foreground VLC identification, keyboard input, targeted volume-wheel messages and dispatch logging.                                                    |
| [lifecycle.py](lifecycle.py)             | Project/session-scoped Windows mutex and shutdown/completion events.                                                                                   |
| [stop_controller.py](stop_controller.py) | Lightweight shutdown entry point; imports no camera or MediaPipe code.                                                                                 |
| [Set Up.bat](Set%20Up.bat)               | Confirmed first-time setup: local Python 3.14 environment, dependencies and model download.                                                            |
| [Run.bat](Run.bat)                       | Delegates background startup to the VBScript launcher.                                                                                                 |
| [Run-Hidden.vbs](Run-Hidden.vbs)         | Starts local `pythonw.exe` invisibly with the project as its working directory.                                                                        |
| [Run-Test.bat](Run-Test.bat)             | Visible console launch with a Y/N preview prompt and exit-code reporting.                                                                              |
| [Stop.bat](Stop.bat)                     | Runs the lightweight stop helper using the local environment.                                                                                          |
| [requirements.txt](requirements.txt)     | MediaPipe/OpenCV dependency constraints.                                                                                                               |
| [.gitignore](.gitignore)                 | Excludes the environment, Python caches, logs, model files and incomplete model downloads.                                                             |
| [README.md](README.md)                   | User-facing setup, controls and troubleshooting.                                                                                                       |
| `DEVELOPMENT_NOTES.md`                   | Implementation reference and manual-verification checklist.                                                                                            |

These notes describe the current implementation. Configuration defaults are defined in `config.py`; everyday instructions belong in the README.

## Processing flow and ownership

```text
Camera → latest frame → MediaPipe → safe hand identities
       → activation → right-hand gesture → foreground check → VLC command
```

| Owner              | Work                                                                                   |
| ------------------ | -------------------------------------------------------------------------------------- |
| Main thread        | Hand identity, activation, gesture state, dispatch, diagnostics and preview.           |
| Capture worker     | Camera reads and camera release after initial configuration.                           |
| MediaPipe callback | Transfers the completed result under a lock; never updates gestures or sends commands. |
| Audio thread       | Plays a short beep sequence only when persistent activation toggles.                   |

### Modes and buffering

- `PROCESSING_MODE = "auto"` selects threaded LIVE_STREAM at eight or more logical CPUs; otherwise it uses synchronous VIDEO mode. The CPU threshold is a heuristic.
- Explicit `"threaded"` and `"single"` modes support hardware comparison. Thread/model initialization failures fall back to VIDEO where handled.
- Capture keeps one replaceable latest-frame slot. Inference permits only one outstanding submission/result; there is no unbounded frame queue.
- Timestamps increase strictly. Frame references are retained rather than repeatedly copying full capture images.
- Camera disconnection, callback failure or inference timeout stops processing for inspection rather than silently restarting hardware.

### Camera and result freshness

| Setting          | Default / meaning                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------------------------- |
| Capture          | 640×480, requested 30 FPS; driver-reported mode is logged.                                                            |
| Inference bounds | 640×360, preserving aspect ratio without upscaling. At 640×480 capture this produces 480×360 inference images.        |
| Result age limit | 0.12 seconds from camera-read completion; checked during consumption and again before dispatch in threaded mode.      |
| Focus loss       | Invalidates the session, clears activation/gesture identities and releases the webcam. The model remains initialized. |
| Preview          | Displays the frame associated with the inference result, with all VLC commands disabled.                              |

Generation invalidation prevents old callbacks from reactivating a new camera session. An in-flight marker remains until its callback arrives, avoiding overlapping submissions after invalidation.

## Hand identity and activation

### Identity routing

- Initial assignment uses MediaPipe handedness confidence and a short confirmation period, not screen side or detection order.
- Established identities match previous wrist and middle-knuckle positions. Unique spatial continuity can preserve roles through conflicting labels.
- Recent identities survive up to 0.22 seconds of loss. Ambiguous matches pause affected hands; stale landmarks are never returned as current evidence.
- Mirroring correction and `SWAP_HANDEDNESS` are separate. The current swap default reflects manual testing on the original camera.

### Activation rules

| State / gesture           | Behavior                                                                                                                              |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Left-index HOLD           | Confirms after 0.18 seconds. Uncertain evidence immediately pauses commands while logical HOLD can survive 0.28 seconds.              |
| Clear alternate left pose | Ends HOLD after 0.06 seconds of confirmation.                                                                                         |
| Both-hand Shaka           | Confirms after 0.50 seconds and toggles persistent activation. One Shaka cannot toggle.                                               |
| Shaka candidate / latch   | Suppresses playback. Both hands must visibly release for 0.20 seconds before playback resumes; missing hands do not count as release. |
| Persistent activation     | Permits right-hand control without the left hand after Shaka release.                                                                 |
| Focus/window change       | Clears HOLD and persistent activation silently.                                                                                       |

Two ascending beeps indicate ON; one lower beep indicates OFF. HOLD and focus resets do not play sounds. Configuration defines the frequencies and durations.

## Right-hand gesture state

### Recognition and continuity

- Finger extension uses 155° activation / 140° retention hysteresis.
- Seeking takes priority over volume while the middle finger remains extended. Volume requires a clearly folded middle finger; thumb position is ignored.
- Switching between movement gestures requires a stable target pose for 0.12 seconds, then its own confirmation and a fresh baseline.
- Confirmed volume tolerates 0.18 seconds of uncertain pose; other movement gestures use a 0.15-second tolerance. Commands pause during uncertainty.
- Volume/seek recovery rebases movement, retains accumulated displacement and suppresses the recovery frame. Abrupt fingertip bending also rebases movement.
- Genuine pose changes clear movement accumulators. Disabled activation and focus loss reset the right-hand state.

### Movement signals and defaults

All distances use image coordinates with Y scaled by image aspect ratio. Palm-relative signals are normalized by hand size.

| Control    | Default signal                                                 | Increment / threshold                          | Confirmation / cooldown     |
| ---------- | -------------------------------------------------------------- | ---------------------------------------------- | --------------------------- |
| Volume     | Index tip 8 relative to MCP 5, vertically                      | 0.055 palm widths; jitter 0.010                | 0.10 s / 0.10 s             |
| Seek       | Mean index/middle tips 8/12 relative to MCPs 5/9, horizontally | 0.18 palm widths; jitter 0.015                 | 0.10 s / 0.30 s             |
| Chapter    | Mean tips 8/12/16 relative to wrist 0                          | 0.23 starting palm widths                      | 0.20 s / 0.25 s             |
| Video      | Wrist 0 travel, including curved arm sweeps                    | 0.80 starting palm widths                      | 0.35 s / 0.35 s             |
| Play/pause | Open palm including thumb                                      | One action, then neutral-pose release required | 0.25 s hold; 0.20 s release |

Volume and seeking use bounded cumulative displacement and require new movement to issue commands. They do not drain a command backlog while stationary. Seek direction changes clear the previous direction's remainder.

`MOVEMENT_TRACKING = "palm"` selects full-hand movement for volume/seek: volume step 0.010 image height (jitter 0.002), seek step 0.5 palm widths (jitter 0.025). This is an alternative to the default fingertip mode, not an additional calculation layered onto it.

### Chapter/video return-to-neutral

```text
CONFIRMING → ARMED → command → RETURNING → stable neutral → ARMED
```

- The starting neutral reference and palm scale stay fixed for the gesture.
- Movement begun during pose confirmation is retained, including the video arm sweep.
- Horizontal displacement must dominate vertical displacement by a factor of 1.2; curved paths are allowed.
- RETURNING never emits reverse commands. Holding the far endpoint does not repeat the action.
- Rearming requires 0.18 seconds near neutral at no more than 0.45 palm widths/second. Neutral zones are 0.08 palms for chapters and 0.22 for videos.
- Pose release/change establishes a new reference on reconfirmation. RETURNING survives missing identity so recovery cannot turn return travel into a reverse command.
- A large recovery jump can enter RETURNING **without a navigation command**. This is intentional protection, now explicitly logged; a later rearming message is not evidence of an unlogged command.

## VLC command delivery

| Action                       | Delivery                                                                  |
| ---------------------------- | ------------------------------------------------------------------------- |
| Play/pause                   | Space                                                                     |
| Small seek                   | Shift + Left/Right; intended VLC very-short jump length is 3 seconds.     |
| Chapter previous/next        | Shift + P/N                                                               |
| Playlist video previous/next | P/N                                                                       |
| Volume                       | Targeted wheel message by default; VLC determines the volume increment.   |
| Optional keyboard fallbacks  | U/D for volume, J/L for seeking, requiring matching ordinary VLC hotkeys. |

Keyboard dispatch uses one ordered `SendInput` batch. Modified shortcuts include Shift-down, key-down, key-up and Shift-up. Win32 input structures include the complete union and pointer-sized fields for correct layout.

- Foreground VLC is checked immediately before dispatch. Keyboard input is not HWND-targeted, so a focus change during delivery remains possible.
- Physical target keys/modifiers already held by the user suppress keyboard injection. The current caller resets activation after suppressed delivery.
- Partial acceptance attempts key-up cleanup for accepted keydowns and logs failures.
- Wheel messages target VLC's HWND and do not move the physical cursor.
- Logs prove Windows acceptance/queueing, not VLC execution. Compare commands against playback during manual verification.
- VLC/controller privilege levels must match; preferences are never changed automatically.

## Process lifecycle and logging

### Startup and shutdown

1. Create timestamped file logging; add console output only when stdout exists.
2. Acquire a Windows named mutex before heavy imports or webcam initialization. Its name is scoped to the resolved project path and login session.
3. Reject duplicate launches without affecting the active controller. PID and instance-lock acquisition are logged.
4. Stop signals a named event and waits up to 10 seconds for the completion event. It uses neither PID files nor broad Python process termination.
5. Shutdown releases capture/model resources, flushes logs, signals completion and closes Windows handles. A crash lets Windows close the instance handle.

The capture worker owns release: shutdown requests stop and joins it. A blocked driver read can delay cleanup beyond the initial join timeout; the controller waits instead of releasing the camera concurrently with a read.

### Diagnostics and retention

- Every five seconds while processing: frame/hand counts, activation, recognized gesture, movement state and thresholds.
- Performance: actual capture/result FPS, capture/inference durations, replaced frames, stale/invalidated results and approximate capture-to-result latency.
- Threaded capture FPS is measured separately; single-mode capture delivery is constrained by processing.
- Latency starts at camera-read completion, not sensor exposure. Driver buffering can remain even when a one-frame buffer is requested.
- Startup removes correctly named controller logs older than 30 days by filename timestamp. Cleanup checks direct containment, skips links/reparse points and redirected folders, never recurses, and logs deletion failures.

## Known limits and review follow-ups

| Area                 | Limit / consideration                                                                                                                                       |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tracking             | Depth changes and hand rotation affect 2D motion measurements; model identity errors cannot be ruled out.                                                   |
| Identity acquisition | Initial confirmation can span a brief detection gap. Tightening it was deferred to avoid changing working acquisition responsiveness without manual checks. |
| Focus                | `SendInput` has a small foreground-change race despite the immediate check.                                                                                 |
| Physical keyboard    | Suppressed input currently resets activation; changing this needs gesture-state regression checks.                                                          |
| Camera shutdown      | Driver reads may block, delaying release and completion signalling.                                                                                         |
| MediaPipe warnings   | Feedback/NORM_RECT warnings are retained when harmless; diagnose actual detection/recognition failures with preview.                                        |
| Network              | The controller makes no runtime network requests. Third-party package telemetry behavior is separate; local inference needs no online service.              |

Manual testing reported approximately **30 capture FPS, 26 inference FPS and 39 ms capture-to-result latency** on the original system. These are observations, not guaranteed throughput on other hardware.

## Manual verification checklist

- [ ] Preview: verify anatomical Left/Right labels with each hand separately; confirm all VLC commands are disabled.
- [ ] Activation: right hand alone does nothing; left-index HOLD works; brief uncertainty pauses safely.
- [ ] Toggle: both-hand Shaka toggles once while held, blocks playback until both release, and plays the expected cues.
- [ ] Focus: Alt+Tab resets activation and releases capture; returning starts disabled with fresh baselines. Repeat in fullscreen.
- [ ] Volume/seek: check sensitivity, direction changes, release and no repetition while stationary; verify one seek increment is 3 seconds.
- [ ] Chapter/video: check one action per outward movement, no reverse action on return, stable-neutral rearming and recovery after occlusion.
- [ ] Play/pause: one command per deliberate palm; neutral release permits the next command.
- [ ] Keyboard: compare shortcut logs with VLC actions, including physical held-key suppression and configured fallbacks.
- [ ] Lifecycle: duplicate launches from every launcher are rejected; Stop releases resources; console Ctrl+C works; hidden mode still logs.
- [ ] Logs: inspect FPS/latency diagnostics and retention behavior using disposable old timestamped logs inside the real logs folder.

No automated or runtime validation was performed during the documentation update. Use the checklist for hardware and playback verification.
