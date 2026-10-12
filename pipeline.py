"""Latest-frame capture and single-flight inference; never updates gestures."""
import logging
import threading
import time
import config as c

log = logging.getLogger(__name__)


class LatestCamera:
    """The worker exclusively reads/releases VideoCapture after configuration."""
    def __init__(self, camera, instance, foreground_ok, fallback_used=False):
        self.camera = camera
        self.instance = instance
        self.foreground_ok = foreground_ok
        self.fallback_used = fallback_used
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.latest = None
        self.error = None
        self.focus_lost = threading.Event()
        self.captured = self.replaced = 0
        self.capture_seconds = 0.0
        self.thread = threading.Thread(target=self._capture, name="webcam-capture", daemon=False)
        self.thread.start()

    def _capture(self):
        try:
            while not self.stop.is_set() and not self.instance.stopping():
                if not self.foreground_ok():
                    self.focus_lost.set()
                    break
                started = time.monotonic()
                ok, frame = self.camera.read()
                if not ok and not self.fallback_used and not self.stop.is_set():
                    log.warning("Threaded capture failed; retrying existing fallback camera settings")
                    self.camera.set(3, c.CAMERA_FALLBACK_WIDTH)  # CAP_PROP_FRAME_WIDTH
                    self.camera.set(4, c.CAMERA_FALLBACK_HEIGHT)
                    self.camera.set(5, c.CAMERA_FALLBACK_FPS)
                    self.fallback_used = True
                    log.info("Fallback driver reports %sx%s at %.1f FPS",
                             self.camera.get(3), self.camera.get(4), self.camera.get(5))
                    ok, frame = self.camera.read()
                captured_at = time.monotonic()
                if self.stop.is_set() or self.instance.stopping():
                    break
                if not self.foreground_ok():
                    self.focus_lost.set()
                    break
                if not ok:
                    raise RuntimeError("Threaded webcam capture failed/disconnected")
                with self.lock:
                    self.captured += 1
                    self.capture_seconds += captured_at - started
                    self.replaced += int(self.latest is not None)
                    self.latest = (frame, captured_at)
        except Exception as exc:
            log.exception("Camera capture thread failed")
            with self.lock:
                self.error = exc
        finally:
            try:
                self.camera.release()
                log.info("Capture thread exited; camera released")
            except Exception as exc:
                log.exception("Camera worker resource release failed")
                with self.lock:
                    self.error = exc

    def take(self):
        with self.lock:
            if self.error is not None:
                raise RuntimeError("Camera capture thread failed") from self.error
            packet, self.latest = self.latest, None
            return packet

    def metrics(self):
        with self.lock:
            return self.captured, self.replaced, self.capture_seconds

    def release(self):
        self.stop.set()
        self.thread.join(c.CAPTURE_JOIN_SECONDS)
        with self.lock:
            self.latest = None
        if self.thread.is_alive():
            # Never release VideoCapture concurrently with a blocked read.
            log.warning("Camera driver read is blocked; waiting for worker cleanup, keeping instance lock held")
            self.thread.join()


class AsyncResults:
    """Callbacks transfer one packet; only the main processing owner consumes it."""
    def __init__(self, cv2, mp):
        self.cv2, self.mp = cv2, mp
        self.lock = threading.Lock()
        self.pending = self.ready = self.error = None
        self.generation = 0
        self.timestamp = self.last_result = -1
        self.last_submit = -float("inf")
        self.discarded = 0
        self.last_stale_warning = -float("inf")

    def invalidate(self):
        with self.lock:
            self.generation += 1
            if self.ready is not None:
                self.pending = None  # Its callback already completed; no later callback will clear it.
            self.ready = None
            # Keep an in-flight marker until its callback; don't queue a new request.

    def callback(self, result, output_image, timestamp_ms):
        try:
            now = time.monotonic()
            with self.lock:
                pending = self.pending
                if pending is None or pending[0] != timestamp_ms:
                    self.discarded += 1
                    return
                stamp, generation, frame, captured_at, submitted_at, image, size = pending
                if generation != self.generation or timestamp_ms <= self.last_result:
                    self.pending = None
                    self.discarded += 1
                    return
                self.last_result = timestamp_ms
                self.ready = (result, frame, captured_at, now - submitted_at, size, stamp, generation)
        except Exception as exc:
            log.exception("MediaPipe result callback failed")
            with self.lock:
                self.error = exc
                self.pending = self.ready = None

    def next(self, camera, landmarker):
        now = time.monotonic()
        with self.lock:
            if self.error:
                raise RuntimeError("Asynchronous result callback failed") from self.error
            if self.ready is not None:
                packet, self.ready = self.ready, None
                self.pending = None
                if packet[6] == self.generation and now - packet[2] <= c.MAX_RESULT_AGE_SECONDS:
                    return packet
                self.discarded += 1
                if now - self.last_stale_warning >= c.DIAGNOSTICS_SECONDS:
                    log.warning("Discarding stale/invalid inference result; age=%.1f ms, limit=%.1f ms, discarded=%s",
                                1000*(now-packet[2]), 1000*c.MAX_RESULT_AGE_SECONDS, self.discarded)
                    self.last_stale_warning = now
            if self.pending is not None:
                if now - self.pending[4] > c.ASYNC_TIMEOUT_SECONDS:
                    raise TimeoutError("MediaPipe LIVE_STREAM callback timed out")
                return None
        if now - self.last_submit < 1 / c.FPS:
            return None
        packet = camera.take()
        if packet is None:
            return None
        frame, captured_at = packet
        if now - captured_at > c.MAX_RESULT_AGE_SECONDS:
            self.discarded += 1
            return None
        height, width = frame.shape[:2]
        ratio = min(c.INFERENCE_WIDTH / width, c.INFERENCE_HEIGHT / height, 1.0)
        inference = self.cv2.resize(frame, (max(1, round(width*ratio)), max(1, round(height*ratio))),
                                    interpolation=self.cv2.INTER_AREA) if ratio < 1 else frame
        if c.MIRROR:
            inference = self.cv2.flip(inference, 1)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                              data=self.cv2.cvtColor(inference, self.cv2.COLOR_BGR2RGB))
        self.timestamp = max(self.timestamp + 1, int(captured_at * 1000))
        submitted_at = time.monotonic()
        self.last_submit = submitted_at
        with self.lock:
            self.pending = (self.timestamp, self.generation, frame, captured_at,
                            submitted_at, image, (inference.shape[1], inference.shape[0]))
        try:
            landmarker.detect_async(image, self.timestamp)
        except Exception:
            with self.lock:
                self.pending = None
            raise
        return None
