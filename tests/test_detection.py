from types import SimpleNamespace

import numpy as np
import pytest
import torch

from config import CameraConfig
from detection import crop_bounds, track_frame


def test_region_detections_map_back_to_full_image():
    class Model:
        def track(self, frame, **kwargs):
            assert frame.shape == (50, 100, 3)
            pose = torch.zeros((1, 17, 3))
            pose[0, 9] = torch.tensor([50, 25, 0.9])
            return [
                SimpleNamespace(
                    boxes=SimpleNamespace(
                        id=torch.tensor([7]), xyxy=torch.tensor([[10, 5, 90, 45]])
                    ),
                    keypoints=SimpleNamespace(data=pose),
                    plot=lambda: np.full_like(frame, 200),
                )
            ]

    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    config = CameraConfig(detection_region=(0.25, 0.25, 0.75, 0.75))
    people, rendered = track_frame(Model(), frame, config)
    assert people[0][0] == 7
    assert people[0][1] == pytest.approx([0.3, 0.3, 0.7, 0.7])
    assert people[0][2] == [(0.5, 0.5)]
    assert rendered.shape == frame.shape and rendered[50, 100, 0] == 200
    assert rendered[0, 0, 0] == 0 and not frame.any()


def test_legacy_profiles_keep_full_frame_and_invalid_regions_fail():
    config = CameraConfig.from_dict({"name": "Existing profile"})
    assert crop_bounds(config.detection_region, 200, 100) == (0, 0, 200, 100)
    with pytest.raises(ValueError):
        CameraConfig(detection_region=(0.8, 0, 0.2, 1)).validate()
    with pytest.raises(ValueError, match="pixels"):
        crop_bounds((0, 0, 0.001, 0.001), 100, 100)
