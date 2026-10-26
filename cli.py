"""Batch analysis and training without the UI."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from config import CameraConfig
from store import ROOT, analysis_session, dataset_rows, new_run, read_json, write_json
from vision import analyze


def main():
    parser = argparse.ArgumentParser(description="Carwatch local research tools")
    sub = parser.add_subparsers(dest="command", required=True)
    batch = sub.add_parser("batch", help="Analyze a JSON manifest of camera recordings")
    batch.add_argument("manifest", type=Path)
    train = sub.add_parser("train", help="Train on the reviewed local dataset")
    train.add_argument("--epochs", type=int, default=60)
    train.add_argument("--name", default="activity-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    export = sub.add_parser("export", help="Export reviewed feature windows")
    export.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "batch":
        manifest = read_json(args.manifest)
        if not manifest or not manifest.get("recordings"):
            raise ValueError("Manifest needs recordings")
        results = []
        for recording in manifest["recordings"]:
            source = (args.manifest.parent / recording["file"]).resolve()
            config = CameraConfig.from_dict(recording["camera"])
            meta, out = new_run(
                source,
                config.to_dict(),
                recording["session_id"],
                recording.get("split", "train"),
            )
            try:
                with analysis_session(out):
                    report = analyze(
                        out / meta["source"],
                        out,
                        config=config,
                        max_seconds=recording.get("max_seconds", 300),
                    )
                results.append(
                    dict(run=meta["id"], status="complete", events=len(report["events"]))
                )
            except Exception as exc:
                results.append(dict(run=meta["id"], status="failed", error=str(exc)))
        print(json.dumps(results, indent=2))
        if any(r["status"] == "failed" for r in results):
            raise SystemExit(1)
    elif args.command == "train":
        from temporal import fit

        if not args.name or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for c in args.name
        ):
            raise ValueError(
                "Use a simple model name containing letters, numbers, hyphens or underscores"
            )
        out = ROOT / "models" / args.name
        if out.exists():
            raise ValueError("Model name already exists; choose a new name")
        card = fit(dataset_rows(real_only=True), out, epochs=args.epochs)
        print(
            json.dumps(
                {k: card[k] for k in ["origin", "counts", "best_epoch", "test"]},
                indent=2,
            )
        )
    elif args.command == "export":
        if args.output.exists():
            raise ValueError("Export destination already exists")
        rows = dataset_rows()
        write_json(args.output, rows)
        print(f"Exported {len(rows)} reviewed windows to {args.output}")


if __name__ == "__main__":
    main()
