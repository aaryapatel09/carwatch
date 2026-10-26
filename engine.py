"""Deterministic activity cues. These rules do not infer threat or intention."""

from dataclasses import dataclass, field

from config import finite_number, validate_zone


def inside(point, zone):
    x, y = point
    a, b, c, d = zone
    return a <= x <= c and b <= y <= d


@dataclass
class Track:
    last: float
    inside: bool = False
    entered: float = 0
    outside_since: float | None = None
    visits: list = field(default_factory=list)
    linger_sent: bool = False
    repeat_sent: bool = False
    hand_start: float | None = None
    hand_sent: bool = False


class ActivityEngine:
    def __init__(
        self,
        zone=(0.3, 0.2, 0.7, 0.95),
        dwell=10.0,
        repeat=3,
        window=60.0,
        gap=1.0,
        hand_zone=None,
        hand_seconds=1.5,
        exit_seconds=0.75,
    ):
        validate_zone(zone)
        if hand_zone is not None:
            validate_zone(hand_zone)
        values = [dwell, window, gap, hand_seconds, exit_seconds]
        if type(repeat) is not int or not all(finite_number(v) for v in values):
            raise ValueError("Invalid zone or thresholds")
        if (
            dwell <= 0
            or repeat < 2
            or window <= 0
            or gap <= 0
            or hand_seconds <= 0
            or exit_seconds < 0
        ):
            raise ValueError("Invalid thresholds")
        self.zone, self.dwell, self.repeat, self.window, self.gap = (
            zone,
            dwell,
            repeat,
            window,
            gap,
        )
        self.hand_zone, self.hand_seconds, self.exit_seconds = (
            hand_zone,
            hand_seconds,
            exit_seconds,
        )
        self.tracks = {}
        self.time = -1.0

    def update(self, t, people):
        if not finite_number(t) or t < 0 or t < self.time:
            raise ValueError("Timestamps must be finite, nonnegative and monotonic")
        self.time = t
        events = []
        valid = []
        seen = set()
        for person in people:
            if len(person) not in (2, 3):
                raise ValueError("Each observation needs an ID, box and optional wrists")
            tid, box = person[:2]
            if type(tid) is not int or tid < 0 or tid in seen:
                raise ValueError("Track IDs must be unique nonnegative integers per frame")
            if len(box) != 4 or not all(finite_number(v) for v in box):
                continue
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
                continue
            wrists = person[2] if len(person) == 3 else []
            wrists = [
                p
                for p in wrists
                if len(p) == 2 and all(finite_number(v) and 0 <= v <= 1 for v in p)
            ]
            valid.append((tid, box, wrists))
            seen.add(tid)
        # Missing observations break evidence for continuous occupancy or hand dwell.
        for tid, s in list(self.tracks.items()):
            if t - s.last > self.window:
                del self.tracks[tid]
            elif tid not in seen:
                s.inside = False
                s.linger_sent = False
                s.hand_start = None
                s.hand_sent = False
                s.visits = []
                s.repeat_sent = False
        for tid, box, wrists in valid:
            x1, y1, x2, y2 = box
            is_inside = inside(((x1 + x2) / 2, y2), self.zone)
            s = self.tracks.setdefault(tid, Track(t))
            if t - s.last > self.gap:
                s = Track(t)
                self.tracks[tid] = s
            s.visits = [v for v in s.visits if t - v <= self.window]
            if len(s.visits) < self.repeat:
                s.repeat_sent = False
            if is_inside:
                if not s.inside:
                    s.entered = t
                    s.linger_sent = False
                    if s.outside_since is None or t - s.outside_since >= self.exit_seconds:
                        s.visits.append(t)
                s.outside_since = None
                if t - s.entered >= self.dwell and not s.linger_sent:
                    events.append(
                        self._event(
                            t,
                            tid,
                            "lingering",
                            "Person remained in the selected image zone",
                        )
                    )
                    s.linger_sent = True
                if len(s.visits) >= self.repeat and not s.repeat_sent:
                    events.append(
                        self._event(
                            t,
                            tid,
                            "repeated_approach",
                            "Track entered the selected zone repeatedly",
                        )
                    )
                    s.repeat_sent = True
            else:
                if s.inside or s.outside_since is None:
                    s.outside_since = t
            hand = bool(self.hand_zone and any(inside(p, self.hand_zone) for p in wrists))
            if hand:
                if s.hand_start is None:
                    s.hand_start = t
                if t - s.hand_start >= self.hand_seconds and not s.hand_sent:
                    events.append(
                        self._event(
                            t,
                            tid,
                            "hand_near_zone",
                            "Estimated wrist remained in the marked image region; contact is unconfirmed",
                        )
                    )
                    s.hand_sent = True
            else:
                s.hand_start = None
                s.hand_sent = False
            s.inside, s.last = is_inside, t
        return events

    @staticmethod
    def _event(t, tid, kind, description):
        return dict(
            time=round(t, 3),
            track=int(tid),
            kind=kind,
            description=description,
            source="rule",
            review="unreviewed",
        )
