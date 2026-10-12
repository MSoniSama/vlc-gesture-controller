"""One-hand gesture state machine; has no camera or Windows dependencies."""
import math
import logging
import config as c

log = logging.getLogger(__name__)


def distance(a, b, aspect=1.0):
    # In width-normalized image units, y must be scaled by height/width.
    return math.hypot(a.x - b.x, (a.y - b.y) * aspect)


def finger_angle(points, base, joint, tip, aspect=1.0):
    a, b, d = points[base], points[joint], points[tip]
    u = (a.x - b.x, (a.y - b.y) * aspect, a.z - b.z)
    v = (d.x - b.x, (d.y - b.y) * aspect, d.z - b.z)
    divisor = math.sqrt(sum(x*x for x in u) * sum(x*x for x in v))
    if divisor < 1e-8:
        return 0.0
    return math.degrees(math.acos(max(-1, min(1, sum(x*y for x, y in zip(u, v)) / divisor))))


def straight(points, base, joint, tip, aspect=1.0):
    angle = finger_angle(points, base, joint, tip, aspect)
    b, d = points[joint], points[tip]
    return angle >= c.FINGER_STRAIGHT_ANGLE and distance(d, points[0], aspect) > distance(b, points[0], aspect)


class Gestures:
    def __init__(self):
        self.reset()

    def reset(self):
        self.kind = None
        self.since = 0.0
        self.fired = False
        self.locked = False
        self.release_since = None
        self.volume_accumulated = 0.0
        self.seek_accumulated = 0.0
        self.seek_direction = 0
        self.details = ""
        self.x = self.y = self.baseline = None
        self.last_action = -math.inf
        self.recognized = None
        self.status = "no hand"
        self.interrupted_since = None
        self.extended = [False] * 4
        self.pending_kind = None
        self.pending_since = None
        self.motion_x = self.motion_y = None
        self.last_finger_angles = None
        self.last_uncertainty_log = -math.inf
        self.navigation_state = "CONFIRMING"
        self.navigation_origin = None
        self.navigation_position = None
        self.navigation_scale = None
        self.navigation_neutral_since = None
        self.navigation_last_sample = None

    def log_uncertainty(self, now, message):
        if now - self.last_uncertainty_log >= c.DIAGNOSTICS_SECONDS:
            log.info(message, self.kind)
            self.last_uncertainty_log = now

    def pause(self, now, preserve_activation=False):
        """Retain bounded state, never emit commands or consume stale landmarks."""
        self.pending_kind = self.pending_since = None
        if self.interrupted_since is None:
            self.interrupted_since = now
            if self.fired and self.kind in ("index_volume", "swipe"):
                self.log_uncertainty(now, "Confirmed %s temporarily paused; state retained")
        if self.locked:
            self.release_since = None  # Uncertain frames cannot prove palm release.
        if self.kind in ("chapter", "video"):
            self.navigation_neutral_since = None
        grace = c.VOLUME_POSE_LOSS_SECONDS if self.kind == "index_volume" else c.RIGHT_POSE_LOSS_SECONDS
        returning = self.kind in ("chapter", "video") and self.navigation_state == "RETURNING"
        if not preserve_activation and not self.locked and not returning and now - self.interrupted_since >= grace:
            if self.fired and self.kind in ("index_volume", "swipe"):
                log.info("Confirmed %s released: tracking/uncertainty grace expired", self.kind)
            self.reset()
        self.status = "tracking/activation uncertain; commands paused"

    def update(self, points, now, aspect=1.0):
        self.details = ""
        if not points:
            kind = None
        else:
            scale = max(distance(points[5], points[17], aspect), 0.01)
            angles = [finger_angle(points, *indices, aspect=aspect) for indices in
                      ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))]
            fingers = [angle >= c.FINGER_STRAIGHT_ANGLE and
                       distance(points[tip], points[0], aspect) > distance(points[joint], points[0], aspect)
                       for angle, joint, tip in zip(angles, (6, 10, 14, 18), (8, 12, 16, 20))]
            self.extended = [angle >= (c.FINGER_EXTENSION_RELEASE_ANGLE if previous else c.FINGER_STRAIGHT_ANGLE)
                             and distance(points[tip], points[0], aspect) > distance(points[joint], points[0], aspect)
                             for angle, previous, joint, tip in zip(angles, self.extended, (6, 10, 14, 18), (8, 12, 16, 20))]
            thumb = straight(points, 1, 3, 4, aspect)
            folded = [distance(points[tip], points[0], aspect) <=
                      c.FOLDED_TIP_RATIO * distance(points[joint], points[0], aspect)
                      for joint, tip in ((10, 12), (14, 16), (18, 20))]
            kind = ("palm" if all(fingers) and thumb else
                    "chapter" if self.extended == [True, True, True, False] and all(fingers[:3]) and folded[2] else
                    "swipe" if self.extended == [True, True, False, False] else
                    "index_volume" if self.extended == [True, False, False, False] and all(folded) and angles[1] <= c.VOLUME_MIDDLE_FOLDED_ANGLE else
                    "video" if not any(self.extended) and all(angle <= c.NAVIGATION_FOLDED_ANGLE for angle in angles) and
                    all(distance(points[tip], points[0], aspect) <= c.FOLDED_TIP_RATIO * distance(points[joint], points[0], aspect)
                        for joint, tip in ((6, 8), (10, 12), (14, 16), (18, 20))) else None)
            self.details = f"Extended I/M/R/P: {fingers} | folded M/R/P: {folded}"

        self.recognized = kind
        self.status = "pose thresholds not met" if points else "no hand"
        switch_confirmed = False
        if self.kind in ("index_volume", "swipe", "chapter", "video") and kind in ("index_volume", "swipe", "chapter", "video") and kind != self.kind and not self.locked:
            if self.pending_kind != kind:
                self.pending_kind, self.pending_since = kind, now
            if now - self.pending_since < c.GESTURE_SWITCH_SECONDS:
                self.status = f"switch {self.kind} -> {kind} pending; commands paused"
                self.interrupted_since = now
                return None
            self.interrupted_since = None
            switch_confirmed = True
        else:
            self.pending_kind = self.pending_since = None
        if not switch_confirmed and not self.locked and self.fired and self.kind in ("index_volume", "swipe", "chapter", "video") and kind != self.kind:
            if self.interrupted_since is None:
                self.interrupted_since = now
                self.log_uncertainty(now, "Confirmed %s pose uncertain; commands paused, state retained")
            grace = c.VOLUME_POSE_LOSS_SECONDS if self.kind == "index_volume" else c.RIGHT_POSE_LOSS_SECONDS
            if now - self.interrupted_since < grace:
                self.status = "pose interruption; commands paused"
                return None
        recovering = self.interrupted_since is not None
        self.interrupted_since = None
        # Only a completed palm requires release; seeking remains continuous.
        if self.locked:
            self.status = "waiting for gesture release"
            if kind is None:
                if self.release_since is None:
                    self.release_since = now
                if now - self.release_since >= c.RELEASE_SECONDS:
                    self.locked = False
                    self.kind = None
            else:
                self.release_since = None
            return None

        if kind != self.kind:
            if self.kind == "index_volume":
                log.info("Index pose released; volume adjustment ended")
            self.kind, self.since, self.fired = kind, now, False
            self.x = self.y = self.baseline = None
            self.volume_accumulated = 0.0
            self.seek_accumulated = 0.0
            self.seek_direction = 0
            self.motion_x = self.motion_y = None
            self.last_finger_angles = None
            self.navigation_state = "CONFIRMING"
            self.navigation_origin = self.navigation_position = self.navigation_scale = None
            self.navigation_neutral_since = self.navigation_last_sample = None
        if kind is None:
            return None
        if recovering and not self.fired:
            self.since = now  # Missing evidence must not complete a new gesture hold.
            self.x = self.y = self.baseline = None
            if kind in ("chapter", "video"):
                self.navigation_origin = self.navigation_position = self.navigation_scale = None
        if kind in ("chapter", "video"):
            return self.navigation(points, now, aspect, recovering)
        # Knuckle center avoids fingertip motion during pose changes.
        palm_x = sum(points[i].x for i in (5, 9, 13, 17)) / 4
        palm_y = sum(points[i].y for i in (5, 9, 13, 17)) / 4
        fingertip = c.MOVEMENT_TRACKING == "fingertip" and kind in ("index_volume", "swipe")
        if fingertip:
            if kind == "index_volume":
                palm_x = (points[8].x - points[5].x) / scale
                palm_y = (points[8].y - points[5].y) * aspect / scale
            else:
                palm_x = ((points[8].x + points[12].x) - (points[5].x + points[9].x)) / (2*scale)
                palm_y = ((points[8].y + points[12].y) - (points[5].y + points[9].y)) * aspect / (2*scale)
            bend = self.last_finger_angles is not None and any(
                abs(angles[i] - self.last_finger_angles[i]) > c.FINGERTIP_MAX_ANGLE_CHANGE
                for i in ((0,) if kind == "index_volume" else (0, 1)))
            self.last_finger_angles = angles
            if self.motion_x is None or recovering or bend:
                self.motion_x, self.motion_y = palm_x, palm_y
            else:
                self.motion_x += c.FINGERTIP_SMOOTHING * (palm_x - self.motion_x)
                self.motion_y += c.FINGERTIP_SMOOTHING * (palm_y - self.motion_y)
            palm_x, palm_y = self.motion_x, self.motion_y
            if bend and self.fired and not recovering:
                self.x, self.y, self.baseline, self.start_y = palm_x, palm_y, palm_y, palm_y
                self.volume_accumulated = self.seek_accumulated = 0.0
                self.status = "finger bending; movement rebased"
                return None
        if recovering and kind == self.kind and self.fired:
            self.x, self.y, self.baseline, self.start_y = palm_x, palm_y, palm_y, palm_y
            self.log_uncertainty(now, "Confirmed %s recovered; baseline rebased, accumulator retained")
            self.status = "pose recovered; movement rebased"
            return None
        if self.x is None:
            self.x = palm_x
            self.y = palm_y
            self.baseline = self.y
            self.start_y = palm_y
            self.swipe_scale = 1.0 if fingertip else scale
        elapsed = now - self.since
        self.status = f"confirmation pending ({elapsed:.2f}/{c.CONFIRM_SECONDS:.2f}s)"
        if kind == "index_volume":
            step = c.FINGERTIP_VOLUME_STEP if fingertip else c.VOLUME_STEP
            jitter = c.FINGERTIP_VOLUME_JITTER if fingertip else c.VOLUME_JITTER_ZONE
            self.y += (1.0 if fingertip else c.SMOOTHING) * (palm_y - self.y)
            if elapsed < c.VOLUME_CONFIRM_SECONDS:
                self.status = f"index confirmation pending ({elapsed:.2f}/{c.VOLUME_CONFIRM_SECONDS:.2f}s)"
                self.baseline = self.y
                return None
            if not self.fired:
                log.info("Index pose confirmed; volume adjustment started")
                self.fired = True
                self.baseline = self.y
                self.volume_accumulated = 0.0
                self.status = "index confirmed; fresh volume baseline"
                return None
            delta = self.baseline - self.y
            moving = abs(delta) >= jitter
            if moving:
                self.volume_accumulated += delta
                self.baseline = self.y
                # Bound backlog to one step plus a fractional remainder.
                self.volume_accumulated = max(-2*step, min(2*step, self.volume_accumulated))
            self.details = f"{c.MOVEMENT_TRACKING} volume dy {delta:+.3f}; accumulated {self.volume_accumulated:+.3f}/{step:.3f}"
            self.status = f"index confirmed; accumulated {self.volume_accumulated:+.3f}/{step:.3f}; " + (
                "jitter dead zone" if not moving else "movement / rate limit")
            if moving and abs(self.volume_accumulated) >= step and now - self.last_action >= c.VOLUME_COOLDOWN:
                self.status = "confirmed; volume threshold reached"
                direction = 1 if self.volume_accumulated > 0 else -1
                self.volume_accumulated -= direction * step
                self.volume_accumulated = max(-0.99*step, min(0.99*step, self.volume_accumulated))
                self.last_action = now
                return "volume_up" if direction > 0 else "volume_down"
        elif kind == "palm":
            self.status = (f"confirmation pending ({elapsed:.2f}/{c.PALM_HOLD_SECONDS:.2f}s)"
                           if elapsed < c.PALM_HOLD_SECONDS else "confirmed; action cooldown")
            if elapsed >= c.PALM_HOLD_SECONDS and now - self.last_action >= c.ACTION_COOLDOWN:
                self.status = "confirmed; toggle triggered; release required"
                self.locked = True
                self.release_since = None
                self.last_action = now
                return "play_pause"
        elif kind == "swipe":
            step = c.FINGERTIP_SEEK_STEP if fingertip else c.SEEK_STEP
            jitter = c.FINGERTIP_SEEK_JITTER if fingertip else c.SEEK_JITTER_ZONE
            if elapsed < c.CONFIRM_SECONDS or not self.fired:
                self.x, self.start_y = palm_x, palm_y
                if elapsed >= c.CONFIRM_SECONDS:
                    self.fired = True
                    self.status = "two-finger seek confirmed; fresh baseline"
                return None
            dx = (palm_x - self.x) / self.swipe_scale
            dy = (palm_y - self.start_y) * (1.0 if fingertip else aspect) / self.swipe_scale
            moving = abs(dx) >= jitter
            horizontal = abs(dx) >= c.SEEK_MIN_HORIZONTAL_RATIO * abs(dy)
            if moving or abs(dy) >= jitter:
                self.x, self.start_y = palm_x, palm_y
                if horizontal and moving:
                    direction = 1 if dx > 0 else -1
                    if direction != self.seek_direction:
                        self.seek_accumulated = 0.0
                    self.seek_direction = direction
                    self.seek_accumulated += dx
                    self.seek_accumulated = max(-2*step, min(2*step, self.seek_accumulated))
                else:
                    self.seek_accumulated = 0.0
            self.details = f"{c.MOVEMENT_TRACKING} seek dx {dx:+.3f}, dy {dy:+.3f}; accumulated {self.seek_accumulated:+.3f}/{step:.2f} palms"
            self.status = "seek confirmed; " + ("dead zone" if not moving else
                          "vertical movement rejected" if not horizontal else "movement / cooldown")
            if moving and horizontal and abs(self.seek_accumulated) >= step and now - self.last_action >= c.SEEK_COOLDOWN:
                direction = 1 if self.seek_accumulated > 0 else -1
                self.seek_accumulated -= direction * step
                self.seek_accumulated = max(-0.99*step, min(0.99*step, self.seek_accumulated))
                self.last_action = now
                self.status = "continuous seek increment triggered"
                return "seek_right" if direction > 0 else "seek_left"
        return None

    def navigation(self, points, now, aspect, recovering):
        """One-shot chapter/video motion with a fixed neutral reference."""
        chapter = self.kind == "chapter"
        confirmation = c.CHAPTER_CONFIRM_SECONDS if chapter else c.VIDEO_CONFIRM_SECONDS
        threshold = c.CHAPTER_SWIPE_STEP if chapter else c.VIDEO_SWIPE_STEP
        neutral = c.CHAPTER_NEUTRAL_ZONE if chapter else c.VIDEO_NEUTRAL_ZONE
        cooldown = c.CHAPTER_COOLDOWN if chapter else c.VIDEO_COOLDOWN
        if self.navigation_scale is None:
            self.navigation_scale = max(distance(points[5], points[17], aspect),
                                        distance(points[0], points[9], aspect), 0.01)
        if chapter:
            raw_x = (sum(points[i].x for i in (8, 12, 16))/3 - points[0].x) / self.navigation_scale
            raw_y = (sum(points[i].y for i in (8, 12, 16))/3 - points[0].y) * aspect / self.navigation_scale
        else:
            raw_x, raw_y = points[0].x / self.navigation_scale, points[0].y * aspect / self.navigation_scale
        previous = self.navigation_position
        if previous is None or recovering:
            position = (raw_x, raw_y)
        else:
            position = tuple(old + c.NAVIGATION_SMOOTHING * (new-old)
                             for old, new in zip(previous, (raw_x, raw_y)))
        speed = math.inf
        if previous is not None and self.navigation_last_sample is not None and not recovering:
            speed = math.hypot(position[0]-previous[0], position[1]-previous[1]) / max(now-self.navigation_last_sample, 1e-6)
        self.navigation_position, self.navigation_last_sample = position, now
        if self.navigation_origin is None:
            # Preserve motion starting during confirmation, especially the arm sweep.
            self.navigation_origin = position
        dx, dy = (value-origin for value, origin in zip(position, self.navigation_origin))
        self.details = (f"{self.kind} {self.navigation_state}: dx {dx:+.2f}, dy {dy:+.2f}; "
                        f"step {threshold:.2f}, neutral {neutral:.2f}; origin {self.navigation_origin[0]:.2f}/{self.navigation_origin[1]:.2f}")
        if now-self.since < confirmation:
            self.status = f"{self.kind} confirmation {now-self.since:.2f}/{confirmation:.2f}s; motion retained"
            return None
        if not self.fired:
            self.fired = True
            self.navigation_state = "ARMED"
            log.info("%s navigation confirmed; ARMED", self.kind)
            self.status = "ARMED; confirmation complete"
            return None
        if recovering:
            # Small reacquisition changes retain progress; large jumps require neutral.
            jump = math.inf if previous is None else math.hypot(position[0]-previous[0], position[1]-previous[1])
            if jump > neutral:
                if self.navigation_state != "RETURNING":
                    log.info("%s navigation RETURNING after tracking jump %.3f > %.3f; no command issued",
                             self.kind, jump, neutral)
                self.navigation_state = "RETURNING"
            self.navigation_neutral_since = None
            self.status = f"{self.navigation_state}; tracking recovered, current frame suppressed"
            return None
        if self.navigation_state == "RETURNING":
            near_neutral = abs(dx) <= neutral and abs(dy) <= neutral
            if near_neutral and speed <= c.NAVIGATION_REARM_MAX_SPEED:
                if self.navigation_neutral_since is None:
                    self.navigation_neutral_since = now
                if now-self.navigation_neutral_since >= c.NAVIGATION_REARM_SECONDS:
                    self.navigation_state = "ARMED"
                    self.navigation_neutral_since = None
                    log.info("%s navigation rearmed after stable return to neutral", self.kind)
                    self.status = "ARMED; stable neutral return confirmed"
                    return None
                self.status = "RETURNING; near neutral, awaiting stable rearm"
            else:
                self.navigation_neutral_since = None
                self.status = "RETURNING; move back to neutral and settle (no reverse command)"
            return None
        if abs(dx) < threshold:
            self.status = "ARMED; horizontal displacement below threshold"
        elif abs(dx) < c.NAVIGATION_HORIZONTAL_RATIO * abs(dy):
            self.status = "ARMED; predominantly vertical motion rejected"
        elif now-self.last_action < cooldown:
            self.status = "ARMED; navigation cooldown"
        else:
            self.last_action = now
            self.navigation_state = "RETURNING"
            self.navigation_neutral_since = None
            self.status = "RETURNING; one navigation command triggered"
            return f"{self.kind}_next" if dx > 0 else f"{self.kind}_previous"
        return None
