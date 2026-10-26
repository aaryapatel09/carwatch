"""Serializable camera calibration. Coordinates are image-relative, not metres."""
from dataclasses import asdict, dataclass
import math

@dataclass
class CameraConfig:
    name: str = 'Driver side'
    zone: tuple = (0.25, 0.15, 0.75, 0.98)
    hand_zone: tuple = (0.40, 0.35, 0.60, 0.65)
    dwell: float = 10.0
    repeat: int = 3
    window: float = 60.0
    hand_seconds: float = 1.5
    confidence: float = 0.35
    pose: bool = True

    def validate(self):
        if not self.name.strip() or len(self.name)>80:
            raise ValueError('Camera name must contain 1–80 characters.')
        for box in (self.zone,self.hand_zone):
            if len(box)!=4 or not all(math.isfinite(v) for v in box):
                raise ValueError('Zone coordinates must be finite.')
            a,b,c,d=box
            if not (0<=a<c<=1 and 0<=b<d<=1):
                raise ValueError('Each zone must have positive width and height inside the image.')
        if not all(math.isfinite(v) for v in [self.dwell,self.window,self.hand_seconds,self.confidence]):
            raise ValueError('Thresholds must be finite.')
        if not (1<=self.dwell<=120 and 2<=self.repeat<=10 and 5<=self.window<=300 and .25<=self.hand_seconds<=30 and .1<=self.confidence<=.95):
            raise ValueError('Camera thresholds are outside supported ranges.')
        return self

    def to_dict(self):
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data).validate()
