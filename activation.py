"""Left-hand activation and conservative handedness routing."""
import logging
import math
import threading
import winsound
import config as c
from gestures import distance, straight, finger_angle

log = logging.getLogger(__name__)


def shaka(points, aspect, retaining=False):
    if not points:
        return False
    thumb_angle = c.SHAKA_THUMB_OFF_ANGLE if retaining else c.SHAKA_THUMB_ON_ANGLE
    pinky_angle = c.SHAKA_PINKY_OFF_ANGLE if retaining else c.SHAKA_PINKY_ON_ANGLE
    curl_angle = c.SHAKA_CURL_OFF_ANGLE if retaining else c.SHAKA_CURL_ON_ANGLE
    curl_reach = c.SHAKA_CURL_OFF_REACH if retaining else c.SHAKA_CURL_ON_REACH
    scale = max(distance(points[5], points[17], aspect), distance(points[0], points[9], aspect), 0.01)
    curled = all(finger_angle(points, base, joint, tip, aspect) <= curl_angle and
                 distance(points[tip], points[0], aspect) <= curl_reach * distance(points[joint], points[0], aspect)
                 for base, joint, tip in ((5, 6, 8), (9, 10, 12), (13, 14, 16)))
    thumb_reach = c.SHAKA_THUMB_OFF_REACH if retaining else c.SHAKA_THUMB_ON_REACH
    pinky_reach = c.SHAKA_PINKY_OFF_REACH if retaining else c.SHAKA_PINKY_ON_REACH
    return (curled and finger_angle(points, 1, 3, 4, aspect) >= thumb_angle and
            finger_angle(points, 17, 18, 20, aspect) >= pinky_angle and
            distance(points[4], points[2], aspect) / scale >= thumb_reach and
            distance(points[20], points[17], aspect) / scale >= pinky_reach)


def sound(enabled):
    def play():
        try:
            for frequency, duration in (c.TOGGLE_ON_BEEPS if enabled else c.TOGGLE_OFF_BEEPS):
                winsound.Beep(frequency, duration)
        except Exception:
            log.warning("Toggle audio unavailable", exc_info=True)
    threading.Thread(target=play, name="activation-beeps", daemon=True).start()


class HandRouter:
    def __init__(self):
        self.reset()

    def reset(self):
        self.candidates = {}
        self.last_warning = -math.inf

    def select(self, result, now, aspect):
        self.candidates = {label: track for label, track in self.candidates.items()
                           if now - track[1] <= c.HAND_ID_LOSS_SECONDS}
        detections = []
        for points, categories in zip(result.hand_landmarks, result.handedness):
            category = max(categories, key=lambda item: item.score) if categories else None
            label = category.category_name if category else None
            confident = category is not None and category.score >= c.HANDEDNESS_CONFIDENCE
            # Account for inference mirroring, then apply the camera's label correction.
            if label in ("Left", "Right") and (not c.MIRROR) != c.SWAP_HANDEDNESS:
                label = "Right" if label == "Left" else "Left"
            detections.append((points, label, confident))
        # Match wrist and middle knuckle; require unique, well-separated assignments.
        def separation(a, b):
            return (distance(a[0], b[0], aspect) + distance(a[9], b[9], aspect)) / 2
        proposals = {}
        for index, (points, label, confident) in enumerate(detections):
            choices = sorted((separation(points, track[2]), role)
                             for role, track in self.candidates.items())
            if choices and choices[0][0] <= c.HAND_ID_MAX_JUMP:
                if len(choices) > 1 and choices[1][0] - choices[0][0] < c.HAND_ID_MATCH_MARGIN:
                    continue
                proposals[index] = choices[0][1]
            elif confident and label in ("Left", "Right") and label not in self.candidates:
                proposals[index] = label
        accepted = {}
        for index, role in proposals.items():
            if list(proposals.values()).count(role) != 1:
                continue
            points, label, confident = detections[index]
            previous = self.candidates.get(role)
            # New identities require sustained confident labels; established roles use spatial continuity.
            if previous is None:
                if not confident or label != role:
                    continue
                since = now
            else:
                since = previous[0]
                if now - since < c.HAND_ID_CONFIRM_SECONDS and now - previous[1] > 2 / c.FPS:
                    since = now
                if now - since < c.HAND_ID_CONFIRM_SECONDS and (not confident or label != role):
                    self.candidates.pop(role, None)
                    continue
            self.candidates[role] = (since, now, points)
            if now - since >= c.HAND_ID_CONFIRM_SECONDS:
                accepted[role] = points
        if len(accepted) < len(detections) and now - self.last_warning >= c.DIAGNOSTICS_SECONDS:
            log.warning("Hand identity pending/ambiguous; affected hands paused (recent identities retained)")
            self.last_warning = now
        return accepted


class Activation:
    def __init__(self):
        self.reset()

    def reset(self):
        self.toggled = self.hold = False
        self.pose = None
        self.since = None
        self.shaka_latched = False
        self.release_since = None
        self.last_toggle = -math.inf
        self.safe = False
        self.hold_uncertain_since = None
        self.clear_release_since = None
        self.last_uncertainty_log = -math.inf
        self.right_shaka = False
        self.pair_since = self.pair_last_seen = None
        self.toggle_blocked = False

    @property
    def state(self):
        return "TOGGLED" if self.toggled else "HOLD" if self.hold else "DISABLED"

    @property
    def enabled(self):
        return self.hold or self.toggled

    @property
    def commands_allowed(self):
        return not self.toggle_blocked and (self.toggled or (self.hold and self.safe))

    def update(self, points, now, aspect, right_points=None):
        old_hold = self.hold
        pose = None
        clear_alternative = False
        if points:
            extended = [straight(points, *indices, aspect=aspect) for indices in
                        ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))]
            folded = [not extended[i] and distance(points[tip], points[0], aspect) <=
                      c.FOLDED_TIP_RATIO * distance(points[joint], points[0], aspect)
                      for i, joint, tip in ((0, 6, 8), (1, 10, 12), (2, 14, 16), (3, 18, 20))]
            if extended == [True, False, False, False] and all(folded[1:]):
                pose = "Index Hold"
            elif shaka(points, aspect, self.pose == "Shaka"):
                pose = "Shaka"
            clear_alternative = (pose == "Shaka" or all(extended) or all(folded) or
                                 (extended == [True, True, False, False] and all(folded[2:])))
        if pose != self.pose:
            self.pose, self.since = pose, now
        self.safe = points is not None and pose == "Index Hold"
        reason = "confirmed index pose"
        if pose == "Index Hold":
            if self.hold_uncertain_since is not None and self.hold:
                if now - self.last_uncertainty_log >= c.DIAGNOSTICS_SECONDS:
                    log.info("Left-index HOLD recovered within grace; confirmation retained")
                    self.last_uncertainty_log = now
            self.hold_uncertain_since = self.clear_release_since = None
            if now - self.since >= c.LEFT_HOLD_SECONDS:
                self.hold = True
        elif self.hold:
            if self.hold_uncertain_since is None:
                self.hold_uncertain_since = now
                if now - self.last_uncertainty_log >= c.DIAGNOSTICS_SECONDS:
                    log.info("Left-index HOLD uncertainty tolerated; playback commands paused")
                    self.last_uncertainty_log = now
            if clear_alternative:
                if self.clear_release_since is None:
                    self.clear_release_since = now
            else:
                self.clear_release_since = None
            if self.clear_release_since is not None and now - self.clear_release_since >= c.LEFT_CLEAR_RELEASE_SECONDS:
                reason = "confirmed alternate pose"
                self.hold = False
            elif now - self.hold_uncertain_since >= c.LEFT_DEACTIVATION_GRACE_SECONDS:
                reason = "uncertainty/tracking grace expired"
                self.hold = False
        if old_hold != self.hold:
            log.info("Left-index hold %s: %s", "activated" if self.hold else "deactivated", reason)
            if not self.hold:
                self.hold_uncertain_since = self.clear_release_since = None
        self.right_shaka = shaka(right_points, aspect, self.right_shaka)
        both = pose == "Shaka" and self.right_shaka
        if both:
            self.release_since = None
            if self.pair_since is None:
                self.pair_since = now
            self.pair_last_seen = now
            if not self.shaka_latched and now - self.pair_since >= c.SHAKA_HOLD_SECONDS and now - self.last_toggle >= c.SHAKA_COOLDOWN:
                self.toggled = not self.toggled
                self.shaka_latched = True
                self.last_toggle = now
                log.info("Both-hand Shaka confirmed")
                log.info("Persistent activation toggle %s", "ON" if self.toggled else "OFF")
                sound(self.toggled)
        else:
            if self.pair_last_seen is None or now - self.pair_last_seen > c.SHAKA_PAIR_LOSS_SECONDS:
                self.pair_since = None
            # Missing/ambiguous hands cannot establish release. Both must visibly release.
            if self.shaka_latched and points is not None and right_points is not None and pose != "Shaka" and not self.right_shaka:
                if self.release_since is None:
                    self.release_since = now
                if now - self.release_since >= c.SHAKA_RELEASE_SECONDS:
                    self.shaka_latched = False
                    self.pair_since = self.pair_last_seen = None
                    log.info("Both-hand Shaka released; playback may resume")
            else:
                self.release_since = None
        self.toggle_blocked = self.shaka_latched or self.pair_since is not None
