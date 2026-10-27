"""Measure annotated-actor visibility on one licensed public parking-lot video."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from public_probe import DETECTORS, run_probe

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--download", action="store_true", help="Fetch the 182 MB CC-BY fixture if missing"
    )
    parser.add_argument(
        "--focused",
        action="store_true",
        help="Use the development crop selected after baseline inspection",
    )
    parser.add_argument(
        "--detector", choices=DETECTORS, default=DETECTORS[0], help="Pretrained detector to measure"
    )
    args = parser.parse_args()
    print(
        json.dumps(run_probe(args.download, focused=args.focused, detector=args.detector), indent=2)
    )
