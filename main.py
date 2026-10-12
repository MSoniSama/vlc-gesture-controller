"""VLC Gesture Controller: run with the project's virtual environment."""
import logging
import argparse
import os
from pathlib import Path
import stat
import sys
import time
from datetime import datetime, timedelta
from contextlib import ExitStack
import config as c

ROOT = Path(__file__).resolve().parent
log = logging.getLogger(__name__)


def discard_old_logs(folder):
    """Delete only timestamped controller logs directly inside the real logs folder."""
    cutoff = datetime.now() - timedelta(days=30)
    removed = 0
    try:
        if folder != ROOT / "logs" or folder.resolve() != folder or folder.is_junction() or folder.is_symlink():
            log.warning("Log cleanup skipped: logs folder is redirected")
            return
        for path in folder.iterdir():
            try:
                timestamp = datetime.strptime(path.name, "controller_%Y%m%d_%H%M%S_%f.log")
            except ValueError:
                continue
            if path.name != timestamp.strftime("controller_%Y%m%d_%H%M%S_%f.log") or timestamp >= cutoff:
                continue
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                # Recheck containment immediately before unlinking; never recurse or follow links.
                if folder.resolve() != folder or folder.is_junction() or folder.is_symlink():
                    log.warning("Log cleanup stopped: logs folder was redirected")
                    break
                if path.parent != folder or path.resolve() != path:
                    continue
                path.unlink()
                removed += 1
            except OSError as exc:
                log.warning("Could not remove old log %s: %s", path.name, exc)
    except OSError as exc:
        log.warning("Log cleanup skipped: %s", exc)
    if removed:
        log.info("Log cleanup removed %s controller logs older than 30 days", removed)


def setup_logging():
    folder = ROOT / "logs"
    folder.mkdir(exist_ok=True)
    filename = folder / f"controller_{datetime.now():%Y%m%d_%H%M%S_%f}.log"
    handlers = [logging.FileHandler(filename, encoding="utf-8")]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=handlers)
    log.info("VLC Gesture Controller starting; PID=%s; log: %s", os.getpid(), filename)
    discard_old_logs(folder)


def validate():
    if sys.platform != "win32":
        raise RuntimeError("Windows 11 is required")
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError("Use Python 3.14 in the project's .venv")
    if c.VOLUME_MODE not in ("wheel", "keyboard"):
        raise ValueError("VOLUME_MODE must be 'wheel' or 'keyboard'")
    if c.SEEK_MODE not in ("shift_arrows", "keyboard"):
        raise ValueError("SEEK_MODE must be 'shift_arrows' or 'keyboard'")
    if c.MOVEMENT_TRACKING not in ("fingertip", "palm"):
        raise ValueError("MOVEMENT_TRACKING must be 'fingertip' or 'palm'")
    if c.PROCESSING_MODE not in ("auto", "threaded", "single"):
        raise ValueError("PROCESSING_MODE must be auto, threaded or single")
    if not (0 < c.FINGERTIP_SMOOTHING <= 1 and
            0 < c.FINGERTIP_VOLUME_JITTER < c.FINGERTIP_VOLUME_STEP and
            0 < c.FINGERTIP_SEEK_JITTER < c.FINGERTIP_SEEK_STEP and
            0 < c.VOLUME_MIDDLE_FOLDED_ANGLE < c.FINGER_EXTENSION_RELEASE_ANGLE < c.FINGER_STRAIGHT_ANGLE <= 180):
        raise ValueError("Invalid fingertip sensitivity or finger hysteresis settings")
    if not 0 < c.SEEK_JITTER_ZONE < c.SEEK_STEP:
        raise ValueError("Seek dead zone must be smaller than its movement step")
    if not (0 < c.SMOOTHING <= 1 and 0 < c.VOLUME_JITTER_ZONE < c.VOLUME_STEP):
        raise ValueError("Invalid smoothing or volume dead zone settings")
    positive = (c.FPS, c.CAMERA_WIDTH, c.CAMERA_HEIGHT, c.INACTIVE_POLL_SECONDS,
                c.DIAGNOSTICS_SECONDS, c.VOLUME_CONFIRM_SECONDS, c.FOLDED_TIP_RATIO,
                c.SEEK_COOLDOWN, c.SEEK_MIN_HORIZONTAL_RATIO, c.INFERENCE_WIDTH, c.INFERENCE_HEIGHT,
                c.CAMERA_FALLBACK_WIDTH, c.CAMERA_FALLBACK_HEIGHT, c.CAMERA_FALLBACK_FPS,
                c.VOLUME_STEP, c.VOLUME_COOLDOWN, c.CONFIRM_SECONDS,
                c.RELEASE_SECONDS, c.SEEK_STEP, c.ACTION_COOLDOWN, c.PALM_HOLD_SECONDS)
    positive += (c.HAND_ID_CONFIRM_SECONDS, c.HAND_ID_MAX_JUMP, c.LEFT_HOLD_SECONDS,
                 c.HAND_ID_LOSS_SECONDS, c.HAND_ID_MATCH_MARGIN,
                 c.RIGHT_POSE_LOSS_SECONDS, c.SHAKA_HOLD_SECONDS,
                 c.SHAKA_RELEASE_SECONDS, c.SHAKA_COOLDOWN)
    positive += (c.LEFT_DEACTIVATION_GRACE_SECONDS, c.LEFT_CLEAR_RELEASE_SECONDS,
                 c.VOLUME_POSE_LOSS_SECONDS)
    positive += (c.CHAPTER_CONFIRM_SECONDS, c.CHAPTER_SWIPE_STEP, c.CHAPTER_COOLDOWN,
                 c.VIDEO_CONFIRM_SECONDS, c.VIDEO_SWIPE_STEP, c.VIDEO_COOLDOWN,
                 c.NAVIGATION_HORIZONTAL_RATIO, c.SHAKA_PAIR_LOSS_SECONDS,
                 c.NAVIGATION_REARM_SECONDS, c.NAVIGATION_REARM_MAX_SPEED)
    if not (0 < c.NAVIGATION_SMOOTHING <= 1 and
            0 < c.CHAPTER_NEUTRAL_ZONE < c.CHAPTER_SWIPE_STEP and
            0 < c.VIDEO_NEUTRAL_ZONE < c.VIDEO_SWIPE_STEP):
        raise ValueError("Invalid navigation smoothing or neutral dead zones")
    if not 0 < c.NAVIGATION_FOLDED_ANGLE < c.FINGER_EXTENSION_RELEASE_ANGLE:
        raise ValueError("Navigation fist angle must indicate clearly folded fingers")
    positive += (c.GESTURE_SWITCH_SECONDS, c.FINGERTIP_MAX_ANGLE_CHANGE)
    positive += (c.AUTO_THREAD_THRESHOLD, c.ASYNC_POLL_SECONDS, c.MAX_RESULT_AGE_SECONDS,
                 c.ASYNC_TIMEOUT_SECONDS, c.CAPTURE_JOIN_SECONDS)
    for on, off in ((c.SHAKA_THUMB_ON_ANGLE, c.SHAKA_THUMB_OFF_ANGLE),
                    (c.SHAKA_PINKY_ON_ANGLE, c.SHAKA_PINKY_OFF_ANGLE)):
        if not 0 < off < on <= 180:
            raise ValueError("Invalid Shaka extension hysteresis")
    if not (0 < c.SHAKA_CURL_ON_ANGLE < c.SHAKA_CURL_OFF_ANGLE <= 180 and
            0 < c.SHAKA_CURL_ON_REACH < c.SHAKA_CURL_OFF_REACH and
            0 < c.SHAKA_THUMB_OFF_REACH < c.SHAKA_THUMB_ON_REACH and
            0 < c.SHAKA_PINKY_OFF_REACH < c.SHAKA_PINKY_ON_REACH):
        raise ValueError("Invalid Shaka curl/reach hysteresis")
    if any(value <= 0 for value in positive):
        raise ValueError("Timing, movement and camera settings must be positive")
    for sequence in (c.TOGGLE_ON_BEEPS, c.TOGGLE_OFF_BEEPS):
        if not sequence or any(not isinstance(hz, int) or not isinstance(ms, int) or
                               not 37 <= hz <= 32767 or ms <= 0 for hz, ms in sequence):
            raise ValueError("Toggle sounds need valid integer frequencies and positive durations")
    if not all(0 <= v <= 1 for v in (c.DETECTION_CONFIDENCE,
                                    c.TRACKING_CONFIDENCE, c.PRESENCE_CONFIDENCE, c.HANDEDNESS_CONFIDENCE)):
        raise ValueError("Confidence settings must be between 0 and 1")
    if c.WHEEL_DELTA <= 0 or c.WHEEL_DELTA > 32767:
        raise ValueError("WHEEL_DELTA must be between 1 and 32767")
    for action in ("seek_left", "seek_right", "play_pause", "volume_up", "volume_down"):
        if not isinstance(c.KEYS.get(action), int) or not 1 <= c.KEYS[action] <= 254:
            raise ValueError(f"Invalid virtual key for {action}")
    model = ROOT / c.MODEL_PATH
    if not model.is_file():
        raise FileNotFoundError(f"Missing hand model: {model}. Follow README setup instructions.")
    return model


def show_preview(cv2, frame, hands, gesture, activation, rates):
    """Draw normalized landmarks without depending on legacy mp.solutions."""
    for label, points in hands.items():
        height, width = frame.shape[:2]
        pixels = [(int(p.x * width), int(p.y * height)) for p in points]
        chains = ((0, 1, 2, 3, 4), (0, 5, 6, 7, 8), (5, 9, 10, 11, 12),
                  (9, 13, 14, 15, 16), (13, 17, 18, 19, 20), (0, 17))
        for chain in chains:
            for a, b in zip(chain, chain[1:]):
                cv2.line(frame, pixels[a], pixels[b], (0, 200, 0), 2)
        for pixel in pixels:
            cv2.circle(frame, pixel, 4, (0, 0, 255), -1)
        cv2.putText(frame, label, pixels[0], cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    for row, text in enumerate(("DEBUG: VLC commands disabled | Q/Esc exits",
                                f"Left: {activation.pose} | right Shaka: {activation.right_shaka} | toggle blocked: {activation.toggle_blocked}",
                                f"Activation: {activation.state} | safe: {activation.commands_allowed}",
                                f"Right pose: {gesture.recognized} | active: {gesture.kind} | {c.MOVEMENT_TRACKING}", gesture.status,
                                gesture.details,
                                f"Volume step {(c.FINGERTIP_VOLUME_STEP if c.MOVEMENT_TRACKING == 'fingertip' else c.VOLUME_STEP):.3f}",
                                f"Seek step {(c.FINGERTIP_SEEK_STEP if c.MOVEMENT_TRACKING == 'fingertip' else c.SEEK_STEP):.3f} | cooldown {c.SEEK_COOLDOWN:.2f}s",
                                rates)):
        cv2.putText(frame, text, (10, 25 + row * 25), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imshow("VLC Gesture Controller - Debug", frame)
    key = cv2.waitKey(1) & 0xff
    return key not in (27, ord("q")) and cv2.getWindowProperty(
        "VLC Gesture Controller - Debug", cv2.WND_PROP_VISIBLE) >= 1


def run(model, instance, debug_preview=False):
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError as exc:
        raise RuntimeError("Dependencies missing or incompatible. Run .venv\\Scripts\\python.exe -m pip install -r requirements.txt") from exc
    from gestures import Gestures
    from activation import Activation, HandRouter
    from vlc_control import foreground_vlc, execute
    from pipeline import LatestCamera, AsyncResults
    logical_cpus = os.cpu_count() or 1
    threaded = c.PROCESSING_MODE == "threaded" or (
        c.PROCESSING_MODE == "auto" and logical_cpus >= c.AUTO_THREAD_THRESHOLD)
    asynchronous = AsyncResults(cv2, mp) if threaded else None

    options = vision.HandLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.LIVE_STREAM if threaded else vision.RunningMode.VIDEO,
        result_callback=asynchronous.callback if threaded else None, num_hands=2,
        min_hand_detection_confidence=c.DETECTION_CONFIDENCE,
        min_hand_presence_confidence=c.PRESENCE_CONFIDENCE,
        min_tracking_confidence=c.TRACKING_CONFIDENCE)
    gesture = Gestures()
    activation, router = Activation(), HandRouter()
    controls_enabled = False
    camera = None
    active_hwnd = None
    timestamp = -1
    processed_frames = hand_frames = 0
    captured_interval = processed_interval = 0
    capture_seconds = inference_seconds = 0.0
    rates = "Measured FPS: waiting for first diagnostic interval"
    diagnostics_at = time.monotonic()
    captured_previous = replaced_previous = 0
    capture_time_previous = 0.0
    latency_seconds = 0.0
    last_processed_timestamp = -1
    log.info("Debug preview: VLC commands disabled; Q/Esc or Ctrl+C stops" if debug_preview
             else "Inactive: waiting for an existing VLC foreground window; Ctrl+C stops")
    try:
        try:
            landmarker_resource = vision.HandLandmarker.create_from_options(options)
        except Exception:
            if not threaded:
                raise
            log.exception("LIVE_STREAM initialization failed; falling back to single VIDEO mode")
            threaded, asynchronous = False, None
            options.running_mode = vision.RunningMode.VIDEO
            options.result_callback = None
            landmarker_resource = vision.HandLandmarker.create_from_options(options)
        log.info("Processing mode=%s; logical CPUs=%s; requested=%s (CPU threshold is a heuristic)",
                 "threaded/LIVE_STREAM" if threaded else "single/VIDEO", logical_cpus, c.PROCESSING_MODE)
        with ExitStack() as resources:
            landmarker = resources.enter_context(landmarker_resource)
            def close_camera():
                nonlocal camera
                if asynchronous is not None:
                    asynchronous.invalidate()
                if camera is not None:
                    camera.release()
                    camera = None
                    log.info("Camera released")
            resources.callback(close_camera)
            while not instance.stopping():
                hwnd = True if debug_preview else foreground_vlc()
                if threaded and camera is not None and camera.focus_lost.is_set():
                    hwnd = None  # Even a brief loss invalidates the prior camera session.
                if hwnd != active_hwnd:
                    if active_hwnd is not None:
                        log.info("VLC foreground deactivated; gesture states reset")
                    gesture.reset()
                    activation.reset()
                    router.reset()
                    controls_enabled = False
                    if asynchronous is not None:
                        asynchronous.invalidate()
                    if active_hwnd is not None:
                        log.info("Activation automatically reset to OFF on VLC focus/window change")
                    if camera is not None:
                        camera.release()
                        camera = None
                        log.info("Camera released")
                    active_hwnd = hwnd
                    if hwnd is not None:
                        log.info("Active: debug preview" if debug_preview else "Active: VLC foreground detected")
                        processed_frames = hand_frames = 0
                        diagnostics_at = time.monotonic()
                        captured_interval = processed_interval = 0
                        capture_seconds = inference_seconds = 0.0
                        captured_previous = replaced_previous = 0
                        capture_time_previous = 0.0
                        latency_seconds = 0.0
                        rates = "Measured FPS: waiting for first diagnostic interval"
                        camera = cv2.VideoCapture(c.CAMERA_INDEX, cv2.CAP_DSHOW)
                        if not camera.isOpened():
                            raise RuntimeError("Cannot open webcam; check camera index, privacy permission and other camera apps")
                        if not camera.set(cv2.CAP_PROP_BUFFERSIZE, 1):
                            log.info("Camera backend does not support a one-frame buffer; driver buffering may affect latency")
                        camera.set(cv2.CAP_PROP_FRAME_WIDTH, c.CAMERA_WIDTH)
                        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, c.CAMERA_HEIGHT)
                        camera.set(cv2.CAP_PROP_FPS, c.FPS)
                        camera_fallback = False
                        width = camera.get(cv2.CAP_PROP_FRAME_WIDTH)
                        height = camera.get(cv2.CAP_PROP_FRAME_HEIGHT)
                        reported_fps = camera.get(cv2.CAP_PROP_FPS)
                        if width != c.CAMERA_WIDTH or height != c.CAMERA_HEIGHT or (0 < reported_fps < c.FPS - 1):
                            log.warning("Requested camera mode unavailable (driver: %sx%s at %.1f FPS); using fallback",
                                        width, height, reported_fps)
                            camera.set(cv2.CAP_PROP_FRAME_WIDTH, c.CAMERA_FALLBACK_WIDTH)
                            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, c.CAMERA_FALLBACK_HEIGHT)
                            camera.set(cv2.CAP_PROP_FPS, c.CAMERA_FALLBACK_FPS)
                            camera_fallback = True
                        log.info("Camera driver reports %sx%s at %.1f FPS; loop capped at %s FPS",
                                 camera.get(cv2.CAP_PROP_FRAME_WIDTH), camera.get(cv2.CAP_PROP_FRAME_HEIGHT),
                                 camera.get(cv2.CAP_PROP_FPS), c.FPS)
                        log.info("Camera initialized: index %s, requested %sx%s at %s FPS",
                                 c.CAMERA_INDEX, c.CAMERA_WIDTH, c.CAMERA_HEIGHT, c.FPS)
                        if threaded:
                            try:
                                camera = LatestCamera(camera, instance,
                                    lambda target=hwnd: debug_preview or foreground_vlc() == target,
                                    fallback_used=camera_fallback)
                            except Exception:
                                log.exception("Capture thread initialization failed; falling back to single VIDEO mode")
                                asynchronous.invalidate()
                                # No capture worker started if Thread.start raised.
                                options.running_mode = vision.RunningMode.VIDEO
                                options.result_callback = None
                                landmarker = resources.enter_context(vision.HandLandmarker.create_from_options(options))
                                threaded, asynchronous = False, None
                    else:
                        log.info("Inactive: webcam off; waiting for VLC")
                if hwnd is None:
                    instance.stopping(c.INACTIVE_POLL_SECONDS)
                    continue
                started = time.monotonic()
                if threaded:
                    # Check worker errors even while inference is in flight.
                    with camera.lock:
                        camera_error = camera.error
                    if camera_error is not None:
                        raise RuntimeError("Camera worker failed") from camera_error
                    packet = asynchronous.next(camera, landmarker)
                    if packet is None:
                        if camera.focus_lost.is_set():
                            gesture.pause(time.monotonic())
                        instance.stopping(c.ASYNC_POLL_SECONDS)
                        continue
                    result, frame, captured_at, inference_duration, inference_size, result_stamp, generation = packet
                    if result_stamp <= last_processed_timestamp:
                        continue
                    last_processed_timestamp = result_stamp
                    inference_seconds += inference_duration
                    latency_seconds += time.monotonic() - captured_at
                    total_captured, total_replaced, total_capture_seconds = camera.metrics()
                    captured_interval = total_captured - captured_previous
                    capture_seconds = total_capture_seconds - capture_time_previous
                else:
                    captured_at = started
                    inference_size = None
                    result = None
                if not threaded:
                    ok, frame = camera.read()
                if not threaded and not ok and not camera_fallback:
                    log.warning("Capture failed in requested mode; retrying with fallback camera settings")
                    camera.set(cv2.CAP_PROP_FRAME_WIDTH, c.CAMERA_FALLBACK_WIDTH)
                    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, c.CAMERA_FALLBACK_HEIGHT)
                    camera.set(cv2.CAP_PROP_FPS, c.CAMERA_FALLBACK_FPS)
                    camera_fallback = True
                    log.info("Fallback camera driver reports %sx%s at %.1f FPS",
                             camera.get(cv2.CAP_PROP_FRAME_WIDTH), camera.get(cv2.CAP_PROP_FRAME_HEIGHT),
                             camera.get(cv2.CAP_PROP_FPS))
                    ok, frame = camera.read()
                if not threaded and not ok:
                    raise RuntimeError("Webcam frame capture failed")
                if instance.stopping():
                    break
                if not threaded:
                    captured_interval += 1
                    capture_seconds += time.monotonic() - started
                    captured_at = time.monotonic()
                if not debug_preview and foreground_vlc() != hwnd:
                    activation.reset()
                    router.reset()
                    gesture.reset()
                    controls_enabled = False
                    if asynchronous is not None:
                        asynchronous.invalidate()
                    log.info("Activation automatically reset to OFF on VLC focus loss")
                    continue  # Next iteration releases camera and resets states.
                if not threaded:
                    processing_started = time.monotonic()
                    height, width = frame.shape[:2]
                    resize_ratio = min(c.INFERENCE_WIDTH / width, c.INFERENCE_HEIGHT / height, 1.0)
                    inference_frame = cv2.resize(frame, (max(1, round(width * resize_ratio)),
                                                       max(1, round(height * resize_ratio))),
                                                 interpolation=cv2.INTER_AREA) if resize_ratio < 1 else frame
                    if c.MIRROR:
                        inference_frame = cv2.flip(inference_frame, 1)
                    image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                     data=cv2.cvtColor(inference_frame, cv2.COLOR_BGR2RGB))
                    timestamp = max(timestamp + 1, time.monotonic_ns() // 1_000_000)
                    result = landmarker.detect_for_video(image, timestamp)
                    inference_seconds += time.monotonic() - processing_started
                    latency_seconds += time.monotonic() - captured_at
                    inference_size = (inference_frame.shape[1], inference_frame.shape[0])
                processed_interval += 1
                processed_frames += 1
                hand_frames += int(bool(result.hand_landmarks))
                if not debug_preview and foreground_vlc() != hwnd:
                    gesture.reset()
                    activation.reset()
                    router.reset()
                    controls_enabled = False
                    if asynchronous is not None:
                        asynchronous.invalidate()
                    log.info("Activation automatically reset to OFF on VLC focus loss")
                    continue
                now = time.monotonic()
                if threaded and (camera.focus_lost.is_set() or now - captured_at > c.MAX_RESULT_AGE_SECONDS):
                    gesture.pause(now)
                    continue
                aspect = frame.shape[0] / frame.shape[1]
                hands = router.select(result, now, aspect)
                was_toggle_blocked = activation.toggle_blocked
                activation.update(hands.get("Left"), now, aspect, hands.get("Right"))
                if was_toggle_blocked != activation.toggle_blocked:
                    gesture.reset()
                enabled = activation.enabled
                if enabled != controls_enabled:
                    gesture.reset()
                    controls_enabled = enabled
                    log.info("Right-hand controls %s (%s)", "enabled" if enabled else "disabled", activation.state)
                action = None
                if activation.toggle_blocked:
                    gesture.status = "both-hand Shaka candidate/release; playback suppressed"
                elif enabled or debug_preview:
                    if "Right" not in hands or (not activation.commands_allowed and not debug_preview):
                        gesture.pause(now, preserve_activation=activation.hold and not activation.commands_allowed)
                    else:
                        action = gesture.update(hands["Right"], now, aspect)
                if instance.stopping():
                    break
                if action:
                    log.info("Recognized gesture: %s", action)
                    if threaded and (camera.focus_lost.is_set() or time.monotonic() - captured_at > c.MAX_RESULT_AGE_SECONDS):
                        gesture.pause(time.monotonic())
                        continue
                    if not debug_preview and activation.commands_allowed and not execute(hwnd, action):
                        gesture.reset()
                        activation.reset()
                        router.reset()
                        controls_enabled = False
                        if asynchronous is not None:
                            asynchronous.invalidate()
                now = time.monotonic()
                if now - diagnostics_at >= c.DIAGNOSTICS_SECONDS:
                    log.info("Activation diagnostics: left=%s; activation=%s; commands_allowed=%s; left_hand=%s; right_hand=%s",
                             activation.pose, activation.state, activation.commands_allowed, "Left" in hands, "Right" in hands)
                    interval = now - diagnostics_at
                    rates = f"{'threaded' if threaded else 'single'} | capture {captured_interval/interval:.1f} FPS | results {processed_interval/interval:.1f} FPS"
                    log.info("Camera diagnostics (since activation): processed_frames=%s; "
                             "hand_frames=%s; gesture=%s; state=%s; %s; capture %.1f ms/frame; "
                             "inference (single includes resize/conversion) %.1f ms/frame; inference %sx%s; details=%s",
                             processed_frames, hand_frames, gesture.recognized, gesture.status, rates,
                             1000*capture_seconds/max(1, captured_interval),
                             1000*inference_seconds/max(1, processed_interval),
                             inference_size[0], inference_size[1], gesture.details)
                    log.info("Pipeline latency %.1f ms capture-to-result; replaced=%s; stale/invalidated=%s",
                             1000*latency_seconds/max(1, processed_interval),
                             total_replaced-replaced_previous if threaded else 0,
                             asynchronous.discarded if threaded else 0)
                    if threaded:
                        captured_previous, replaced_previous = total_captured, total_replaced
                        capture_time_previous = total_capture_seconds
                    diagnostics_at = now
                    captured_interval = processed_interval = 0
                    capture_seconds = inference_seconds = 0.0
                    latency_seconds = 0.0
                if debug_preview:
                    if c.MIRROR:
                        frame = cv2.flip(frame, 1)
                    if not show_preview(cv2, frame, hands, gesture, activation, rates):
                        log.info("Debug preview closed")
                        break
                instance.stopping(c.ASYNC_POLL_SECONDS if threaded else max(0, 1/c.FPS - (time.monotonic() - started)))
            if instance.stopping():
                log.info("Shutdown signal received; PID=%s", os.getpid())
    finally:
        if asynchronous is not None:
            asynchronous.invalidate()
        if camera is not None:
            camera.release()
            log.info("Camera released")

        if debug_preview:
            cv2.destroyAllWindows()
        log.info("Camera/MediaPipe resource cleanup completed; PID=%s", os.getpid())


def main():
    setup_logging()
    instance = None
    acquired = False
    exit_code = 0
    try:
        parser = argparse.ArgumentParser(description="VLC Gesture Controller")
        parser.add_argument("--debug-preview", action="store_true",
                            help="Show hand landmarks independently of VLC; disable playback commands")
        parser.add_argument("--stop", action="store_true", help="Request graceful shutdown")
        args = parser.parse_args()
        from lifecycle import Instance, request_stop
        if args.stop:
            return request_stop()
        instance = Instance()
        if not instance.acquire():
            log.info("Duplicate instance detected; PID=%s exiting. Controller already running; "
                     "use Stop.bat before starting a new mode. Running instance is unaffected.", os.getpid())
            return 0
        acquired = True
        log.info("Instance lock acquired; PID=%s", os.getpid())
        run(validate(), instance, debug_preview=args.debug_preview)
        return 0
    except KeyboardInterrupt:
        log.info("Ctrl+C received; graceful termination")
        return 0
    except Exception:
        exit_code = 1
        log.exception("Controller stopped due to an error")
        return 1
    finally:
        try:
            if acquired:
                log.info("VLC Gesture Controller shutdown; PID=%s; %s", os.getpid(),
                         "successful exit" if exit_code == 0 else "exit after error")
            logging.shutdown()
            if acquired:
                instance.finished()
        finally:
            if instance is not None:
                instance.close()


if __name__ == "__main__":
    sys.exit(main())
