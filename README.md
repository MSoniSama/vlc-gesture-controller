# VLC Gesture Controller

Windows 11, Python 3.14 (standard 64-bit build), one webcam, existing VLC.
No preview window. All inference uses a local model; no application network calls.

## Setup

Install Python 3.14 first, then double-click **Set Up.bat** and press **Y**
at the first-time setup prompt. It creates `.venv` inside this project folder,
installs dependencies and downloads the hand model. Pressing **N** cancels.
Errors remain visible in the console. If retrying after a failed setup, press Y;
an existing Python 3.14 environment and completed model download are reused.

Alternatively, run these commands in PowerShell in this folder:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task' -OutFile 'models\hand_landmarker.task'
```

Setup needs internet. Normal operation needs neither a connection nor downloads.
MediaPipe 1.1.0 lists Python 3.14 and Windows x64 wheels on [PyPI](https://pypi.org/project/mediapipe/).
Uses the [Tasks Hand Landmarker VIDEO/LIVE_STREAM API](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python).

Double-click **Run.bat** for background control, or **Run-Hidden.vbs** for startup
without a terminal flash. Both use the local pythonw.exe. **Stop.bat** requests
graceful shutdown and webcam release. Only one instance per project/login session
is allowed through every launcher, using a Windows named mutex before heavy imports.
Startup/shutdown logs include PID; Task Manager's Details > Command line shows
the project main.py path. Stop uses a lightweight named-event helper and waits up
to 10 seconds for resource cleanup/log flushing, without terminating processes.
If it reports pending shutdown, inspect the controller log; blocked driver calls
must return before cleanup can finish. Windows closes the lock handle on a crash.
The instance restriction includes preview. **Run-Test.bat** retains the visible console and
Y/N debug-preview prompt; stop the background instance before using preview.
The console remains open
and each execution creates a flushed timestamped file in `logs/`. To stop, focus
the console and press Ctrl+C. Windows may also ask whether to terminate the batch.
The launcher does not install anything automatically.

## Controls and configuration

Keyboard shortcuts now use foreground-checked Windows SendInput in one ordered batch,
including Shift-down/key-down/key-up/Shift-up for seeks and chapters. Input structure
sizes include the complete Win32 union and pointer-sized fields. Held user keys/modifiers
suppress injection; partial acceptance attempts matching key-up cleanup and logs errors.
Logs report Windows acceptance, not proof of VLC execution. SendInput is foreground
input, not window-targeted: a focus change during delivery cannot be atomically excluded.
Use the same privilege level for VLC/controller and verify Alt+Tab behavior manually.

Right-hand navigation: three extended fingers (index/middle/ring), pinky folded,
then sideways tilt for **Shift+N / Shift+P** chapter next/previous. Chapters track
average tips 8/12/16 relative to wrist 0, normalized by frozen starting palm size;
trigger is 0.23 palm widths. Closed fist (thumb ignored) uses smoothed wrist-0 travel
for **N / P** video next/previous, with a 0.80 palm-width horizontal threshold.
Horizontal dominance of 1.2 allows curved elbow-pivot sweeps; no elbow model is used.
Video pose confirmation remains 0.35 seconds and retains movement begun during it.

Navigation follows ARMED -> RETURNING -> ARMED. After one command, return movement
never issues the opposite command. The original neutral position remains fixed;
settle within 0.08 palms (chapter) or 0.22 palms (video) for 0.18 seconds to rearm.
Rearm also checks low movement speed (0.45 palms/second) against jitter. Holding the
far endpoint does not repeat commands. Releasing/changing pose establishes a new
reference on reconfirmation. Short pose glitches preserve state; reacquisition skips
the current frame, retaining small displacement changes but requiring neutral after
a large jump. RETURNING survives missing identity so reacquisition cannot trigger
a reverse command. Genuine pose release, disabled activation or focus loss resets it.
Cooldowns are 0.25/0.35 seconds, without an additional delay after a settled return.
Tune `CHAPTER_*`, `VIDEO_*` and `NAVIGATION_*` for manual sensitivity/rearm checks.
Moving substantially toward/away from the camera or rotating the hand in depth can
affect these 2D measurements; verify comfortable neutral positions and sweep arcs.

Persistent toggle now requires **both hands displaying relaxed Shaka for 0.50 seconds**.
One Shaka alone cannot toggle. Both candidates and the post-toggle latch suppress
playback; both hands must visibly release Shaka for 0.20 seconds before resuming.
Missing/ambiguous hands do not count as release. Left-index HOLD and toggle sounds
are unchanged. Verify only one toggle while held and no navigation during Shaka.

The intended seek is now **one 3-second jump per increment** using simultaneous
Shift+Left/Right. Your physical-key test confirms VLC's current very-short interval
is already 3 seconds; no preference changes are needed. If changed previously, set VLC's
Very short jump length back to 3 manually. Check one Windows-accepted log event
against one actual jump; no compensating reverse seeks or extra arrow events are used.

Confirmed HOLD now tolerates 0.28 seconds of uncertain left pose/identity; commands
remain paused until the current activation hand is safe. A clear alternate pose
confirms release in 0.06 seconds. Reacquisition within grace retains HOLD without
new activation confirmation or right-state resets. Confirmed volume tolerates
0.18 seconds of right-pose uncertainty; recovery rebases movement and retains its
accumulator. Tune `LEFT_DEACTIVATION_GRACE_SECONDS`, `LEFT_CLEAR_RELEASE_SECONDS`
and `VOLUME_POSE_LOSS_SECONDS`. Initial activation, sensitivities and pipeline remain
unchanged. Logs distinguish temporary pauses/recovery from confirmed release.

`PROCESSING_MODE` defaults to `"auto"`: eight or more logical CPUs selects a dedicated
latest-frame capture thread plus MediaPipe LIVE_STREAM; smaller systems use VIDEO.
`"threaded"` requests the optimized mode; `"single"` selects the synchronous fallback.
Initialization failures log a traceback and fall back to VIDEO. Camera disconnection,
callback errors or timeout during operation stop cleanly for inspection instead of
silently restarting hardware. The CPU threshold is a heuristic; compare both modes.

Capture has one replaceable frame slot. Only one inference/result is outstanding,
with strictly increasing timestamps. Callbacks only transfer results; the main thread
alone updates identities, activation, gestures and VLC commands. Focus loss invalidates
the session and stops/releases capture; old results cannot reactivate it. Result age
is limited by `MAX_RESULT_AGE_SECONDS` (0.12s), checked again before dispatch. No code
can detect a physical release before a newer frame has been inferred; this age limit
bounds that uncertainty. Diagnostics show capture/result FPS, replaced frames,
inference time and approximate capture-return-to-result latency (not sensor exposure).
Driver-internal buffering can still exist. Debug preview displays the result's own
frame. Threaded code retains frame references rather than copying full capture frames.
Shutdown joins the camera worker; a blocked driver read can delay hardware release,
which is logged rather than releasing the camera concurrently with the read.

VLC's Very short backward/forward jump hotkeys should remain Shift+Left/Right, with
Very short jump length at 3 seconds. No preferences are changed automatically.

Movement defaults to fingertip-relative articulation: volume uses index tip minus
its MCP vertically; seek uses the average index/middle tip minus MCP horizontally.
Both are palm-normalized, smoothed and dead-zone filtered. Set `MOVEMENT_TRACKING`
to `"palm"` for the previous full-hand movement. Tune `FINGERTIP_VOLUME_STEP` (0.055),
`FINGERTIP_SEEK_STEP` (0.18), corresponding jitter settings and `FINGERTIP_SMOOTHING`.
Abrupt bending pauses/rebases movement; slow bending that remains a valid pose can
still change the fingertip signal, so manually check comfortable finger articulation.

Right-finger extension uses activation/release angle hysteresis. Seeking has priority
over volume while the middle finger remains extended; volume requires it to be clearly
folded. Volume/seek switches require a stable 0.12-second target pose, then the existing
activation confirmation and fresh baseline. Accumulators clear on genuine switches.
Preview shows detected pose, active state, displacement and confirmation status.
Shaka uses relaxed thumb/pinky angles, naturally curled finger checks and palm-relative
reach with separate retention thresholds. Tune `SHAKA_*_ANGLE`/`SHAKA_*_REACH` if needed;
its both-hand 0.50-second hold and release requirement preserve the existing sounds.

Playback uses the **right hand** only. Raise the **left index** for 0.18 seconds for
temporary activation, or hold **both-hand Shaka** for 0.50 seconds to toggle persistent
activation. Visibly release both Shakas before resuming playback. Toggle ON works without
the left hand remaining visible. Hold mode tolerates 0.28 seconds of uncertainty;
a clearly different valid pose confirms release in 0.06 seconds. Commands
pause immediately during missing/uncertain activation evidence, even while HOLD is
retained. Activation changes reset playback
baselines. Leaving VLC clears both modes silently.

Two ascending beeps confirm toggle ON; one lower beep confirms OFF. Built-in winsound
runs on a short-lived daemon thread only on a toggle change. Frequencies/durations
and activation thresholds are in config.py. No sound is played for hold or focus reset.

Handedness is assigned from MediaPipe labels, never detection order or screen side.
Mirroring correction is combined with `SWAP_HANDEDNESS = True` to correct the
reversed anatomical labels observed on this camera. This does not change preview
mirroring or movement direction. Uncertain
or conflicting labels do not discard established identities when wrist/knuckle
positions give a unique match. Recent identities survive 0.22 seconds of loss;
ambiguous spatial matches pause only the affected roles. New identities still need
confident labels and a short stable assignment.
This reduces accidental reassignment but model errors cannot be ruled out. Verify
anatomical left/right labels in Run-Test preview using each hand separately before
normal operation; camera drivers that already mirror frames require particular care.
Preview shows both hand labels, left pose, activation mode, right gesture and FPS,
while all VLC commands stay disabled. Two hands may lower processed FPS; compare logs.

Manual activation checks: right hand alone must do nothing in normal mode; test
left-index hold/release, Shaka ON with left hand removed, held-Shaka duplicate
prevention, Shaka OFF, and focus loss while toggled. Returning to VLC must start
DISABLED without old movement causing a command. Verify each existing right-hand
control while activated and confirm Stop.bat still releases the camera.

- Raise only the index finger, folding middle/ring/little fingers; thumb is ignored.
  Hold briefly, then move up/down for incremental volume.
  Release to stop. Each step sends one wheel notch; VLC sets the actual volume increment.
- Extend index/middle and curl ring/little fingers; move horizontally for continuous
  seek increments. Right forwards, left backwards; no release between increments.
- Hold an open palm for 0.25 seconds for Space. Return to neutral before another toggle.

Keep one hand visible, palm facing the camera. Movement is mirrored by default.
Settings, thresholds, frame rate, camera index and key codes live in `config.py`.
Capture defaults to 640x480 at 30 FPS. Set CAMERA_WIDTH/CAMERA_HEIGHT to 1280/720
in config.py for comparison; fallback remains 640x480. No upscaling is performed.
Driver-reported resolution/FPS are logged. VIDEO/LIVE_STREAM tracking and the model remain active
across focus changes; only the webcam is released. Actual throughput depends on hardware.
Index volume uses 0.10-second confirmation and a fresh knuckle-center baseline.
Movement accumulates in 0.010 image-height steps with a 0.002 jitter dead zone,
at most one command per 0.10 seconds; excess backlog is bounded and commands require
new movement. Releasing the pose clears accumulated displacement. Seeking tracks
knuckle-center travel in 0.5 palm-width increments with a 0.025 palm-width dead zone
and 0.30-second cooldown. Direction changes clear the previous direction's remainder.
Only new movement triggers commands; release clears seek state. Palm release rules remain unchanged.
These are starting values for manual tuning; reduce FPS if 30 is unsustainable.
Inference uses a configurable 640x360 bounding box, preserving capture aspect ratio.
Only preview retains the full-resolution image for display. Diagnostics report capture
delivery FPS, processed FPS and capture/resize/conversion/landmark timings. Capture
delivery in single mode is limited by processing; threaded mode measures the capture
worker separately. Neither measures independent sensor exposure FPS. No unbounded
application frame queue is added. A one-frame camera buffer is requested,
but DirectShow may ignore it, so check driver buffering and latency manually.

Seek uses SendInput Shift+Right/Left; the optional `SEEK_MODE = "keyboard"` fallback
uses custom **J/L** bindings to VLC's Very short backward/forward jump actions.
For volume fallback, assign **U** to VLC's Volume up and **D** to Volume down
in VLC Preferences > Hotkeys (ordinary VLC hotkeys, not global hotkeys), save and
restart VLC if required. Then set `VOLUME_MODE = "keyboard"` in `config.py`.
Change `KEYS` if you prefer different single-key bindings. Native Ctrl+Up/Down
are not used by the existing configurable volume fallback.

## Manual check

While active, a diagnostic summary appears every five seconds with cumulative
processed frames and hand-containing frames since camera activation, the current
gesture and the confirmation/movement/release state. No frame-by-frame logging.

For a visual check independent of VLC foreground status, run in this folder:

```powershell
.\.venv\Scripts\python.exe main.py --debug-preview
```

Preview shows landmarks, current gesture and confirmation state. All VLC commands
are disabled in this mode. Press Q or Esc, close the preview, or use Ctrl+C to stop.
MediaPipe warnings are left unchanged; these diagnostics help establish where
detection or recognition is stopping before changing thresholds.

1. Start Run-Test.bat; with another app focused, confirm inactive status and camera off.
2. Focus VLC playing a video; confirm active/camera initialized messages.
3. Check single-index up/down and release. Check continuous seeking, immediate direction
   changes and no seeking while stationary. Check one play/pause per held palm;
   release to neutral between toggles.
4. Repeat in VLC fullscreen. Alt+Tab during a gesture; confirm webcam release,
   no other app receives input, and fresh gesture baselines on returning to VLC.
5. Try keyboard volume fallback if wheel messages are ignored. Check log entries,
   then Ctrl+C and confirm camera release/shutdown.

Written code was reviewed without execution. No dependencies were installed and
no automated tests or physical gesture tests were run. Camera drivers can ignore
requested resolution/FPS or block during capture; focus loss is checked between
capture/inference operations, so hardware release cannot be instantaneous during
a blocking driver call. Volume wheel messages are targeted; keyboard events use
foreground-guarded SendInput, with the focus-race limitation explained above. The
pointer is not moved. Differing privilege levels can block delivery. Input is logged as accepted/queued,
not proof VLC acted on it. Use the same normal privilege level for VLC/controller.
Gesture sensitivity, hardware performance and playback delivery need your manual
validation. Stop after a capture or control error, inspect the log, then relaunch.

MediaPipe's upstream package documents performance/utilization metrics collection;
the controller itself makes no network requests and requires no online service.
If strict zero outbound traffic is required, block the project's Python executable
with Windows Firewall during operation; local inference does not need network access.
