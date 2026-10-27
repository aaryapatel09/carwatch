import io
import json
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import cv2
import pandas as pd
import streamlit as st

from config import CameraConfig
from features import LABELS, NAMES
from media import extract_track_clip
from store import (
    ROOT,
    analysis_session,
    dataset_rows,
    delete_run,
    list_runs,
    new_run,
    read_json,
    run_dir,
    save_event_review,
    save_review,
    write_json,
)
from vision import analyze

st.set_page_config(page_title="Carwatch · Activity lab", page_icon="◉", layout="wide")
st.markdown(
    """<style>
.block-container {max-width:1280px;padding-top:3.5rem}
h1 {letter-spacing:-.055em;font-size:3.3rem!important}
[data-testid="stMetric"] {border:1px solid #34473e;border-radius:12px;padding:18px}
[data-testid="stSidebar"] {border-right:1px solid #34473e}
</style>""",
    unsafe_allow_html=True,
)
profiles_path = ROOT / "cameras.json"
profiles = read_json(profiles_path, {"Driver side": CameraConfig().to_dict()})
runs = list_runs()
with st.sidebar:
    st.title("◉ Carwatch")
    st.caption("ACTIVITY LAB · LOCAL")
    page = st.radio(
        "Workspace",
        [
            "Overview",
            "Analyze video",
            "Live camera",
            "Review & label",
            "Train models",
            "Settings",
        ],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("PROCESSING STATUS")
    st.write("Local video + opt-in camera")
    st.caption(
        "Camera access starts only when you press Start camera. Phone delivery is not configured."
    )
    st.divider()
    st.caption("Research prototype. Activity cues are not a safety assessment.")


def model_options():
    result = {}
    for path in (ROOT / "models").glob("*/model.json"):
        card = read_json(path)
        if card.get("origin") == "real_experimental":
            result[path.parent.name] = path.parent
    return result


def select_run():
    completed = [r for r in list_runs() if r["status"] == "complete"]
    if not completed:
        st.info("Analyze a recording first. Its clips and review windows will appear here.")
        return None, None
    lookup = {r["id"]: r for r in completed}
    rid = st.selectbox(
        "Recording",
        list(lookup),
        format_func=lambda k: (
            f"{lookup[k]['camera']} · {lookup[k]['session_id']} · {lookup[k]['created'][:16]} · {k[:6]}"
        ),
    )
    return lookup[rid], run_dir(rid)


if page == "Overview":
    st.caption("SEE THE ACTIVITY. REVIEW THE EVIDENCE.")
    st.title("A clearer view of your parked car.")
    st.write(
        "Analyze recordings, inspect short clips, and build a reviewed dataset for your own activity model."
    )
    completed = [r for r in runs if r["status"] == "complete"]
    rows = dataset_rows()
    events = sum(
        len(read_json(run_dir(r["id"]) / "report.json", {}).get("events", [])) for r in completed
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Camera profiles", len(profiles))
    c2.metric("Processed recordings", len(completed))
    c3.metric("Activity events", events)
    c4.metric("Labeled windows", len(rows))
    left, right = st.columns([1.5, 1])
    with left:
        st.subheader("Your next recording")
        st.write(
            "Start with a fixed camera beside a parked car. Mark the ground area around a door and the smaller image region around its handle."
        )
        st.write(
            "The system looks for sustained presence, repeated zone entries, and estimated wrists near your marked region. It records evidence for you to review."
        )
        st.info(
            "A wrist in an image region does not confirm touching a handle. Occlusion, darkness, reflections and ID switches can change results."
        )
    with right:
        st.subheader("Built into this lab")
        st.markdown(
            "- Saved camera setups\n- Person + pose tracking\n- Silent event clips\n- Manual activity labels\n- Custom sequence-model training\n- Separate validation and test results"
        )
    st.subheader("Recent recordings")
    if runs:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        k: r.get(k)
                        for k in [
                            "camera",
                            "session_id",
                            "split",
                            "origin",
                            "status",
                            "created",
                        ]
                    }
                    for r in runs[:12]
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption(
            "No recordings yet. Use Analyze video to start, or explore the synthetic model in Train models."
        )
    st.caption(
        "Videos and labels are saved locally in carwatch/runtime. You can delete a recording and its evidence in Settings."
    )

elif page == "Analyze video":
    st.title("Analyze a recording")
    st.write(
        "Use the same recording group for every camera and clip from one filming session. This keeps related footage together during training."
    )
    profile_name = st.selectbox("Saved camera profile", list(profiles))
    base = CameraConfig.from_dict(profiles[profile_name])
    with st.expander("Camera calibration", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Camera name", base.name, key=f"name-{profile_name}")
            hx = st.slider(
                "Ground zone · left / right",
                0.0,
                1.0,
                (float(base.zone[0]), float(base.zone[2])),
                0.01,
                key=f"hx-{profile_name}",
            )
            vy = st.slider(
                "Ground zone · top / bottom",
                0.0,
                1.0,
                (float(base.zone[1]), float(base.zone[3])),
                0.01,
                key=f"vy-{profile_name}",
            )
            dwell = st.number_input(
                "Presence duration (seconds)", 1.0, 120.0, float(base.dwell), 1.0
            )
        with c2:
            pose = st.checkbox("Estimate wrists with pose tracking", value=base.pose)
            wh = st.slider(
                "Handle image region · left / right",
                0.0,
                1.0,
                (float(base.hand_zone[0]), float(base.hand_zone[2])),
                0.01,
                key=f"wh-{profile_name}",
            )
            wv = st.slider(
                "Handle image region · top / bottom",
                0.0,
                1.0,
                (float(base.hand_zone[1]), float(base.hand_zone[3])),
                0.01,
                key=f"wv-{profile_name}",
            )
            hand_seconds = st.number_input(
                "Wrist duration (seconds)", 0.25, 30.0, float(base.hand_seconds), 0.25
            )
        a, b, c = st.columns(3)
        repeat = a.number_input("Entries for repeated approach", 2, 10, base.repeat)
        window = b.number_input(
            "Entry counting window (seconds)", 5.0, 300.0, float(base.window), 5.0
        )
        conf = c.slider("Detection confidence", 0.1, 0.95, float(base.confidence), 0.05)
        st.caption(
            "Detection region: focus on your car when people look small in a wide view. "
            "Only this blue region is analyzed. Keep the person's full body and the door visible."
        )
        rx = st.slider(
            "Detection region · left / right",
            0.0,
            1.0,
            (float(base.detection_region[0]), float(base.detection_region[2])),
            0.01,
            key=f"rx-{profile_name}",
        )
        ry = st.slider(
            "Detection region · top / bottom",
            0.0,
            1.0,
            (float(base.detection_region[1]), float(base.detection_region[3])),
            0.01,
            key=f"ry-{profile_name}",
        )
        config = CameraConfig(
            name=name,
            zone=(hx[0], vy[0], hx[1], vy[1]),
            hand_zone=(wh[0], wv[0], wh[1], wv[1]),
            dwell=dwell,
            repeat=repeat,
            window=window,
            hand_seconds=hand_seconds,
            confidence=conf,
            pose=pose,
            detection_region=(rx[0], ry[0], rx[1], ry[1]),
        )
        if st.button("Save camera profile"):
            try:
                profiles[name] = config.to_dict()
                write_json(profiles_path, profiles)
                st.success("Camera profile saved.")
            except ValueError as exc:
                st.error(str(exc))
    upload = st.file_uploader("Video from this camera", type=["mp4", "mov", "avi", "mkv"])
    session = st.text_input("Recording group", placeholder="e.g. driveway-2026-10-26-afternoon")
    c1, c2 = st.columns(2)
    split = c1.selectbox(
        "Dataset split",
        ["train", "val", "test"],
        help="Keep entire filming sessions, people and locations in one split. Choose test before viewing results.",
    )
    limit = c2.slider("Maximum video duration to analyze", 10, 300, 60, 10)
    models = model_options()
    selected = st.selectbox("Optional custom model", ["Rules only"] + list(models))
    st.caption(
        "Custom model scores appear on review windows. They do not trigger notifications. The pose detector may need a one-time public weight download."
    )
    permitted = st.checkbox(
        "I have permission to use this recording and want it saved locally for review."
    )
    if upload:
        with tempfile.TemporaryDirectory(prefix="carwatch-upload-") as td:
            source = Path(td) / ("upload" + Path(upload.name).suffix.lower())
            source.write_bytes(upload.getbuffer())
            cap = cv2.VideoCapture(str(source))
            ok, frame = cap.read()
            cap.release()
            if ok:
                h, w = frame.shape[:2]
                for rect, color in [
                    (config.detection_region, (255, 180, 100)),
                    (config.zone, (125, 225, 165)),
                    (config.hand_zone, (80, 180, 250)),
                ]:
                    a, b, c, d = rect
                    cv2.rectangle(
                        frame,
                        (int(a * w), int(b * h)),
                        (int(c * w), int(d * h)),
                        color,
                        3,
                    )
                st.image(
                    frame,
                    channels="BGR",
                    caption="Blue: analyzed region · green: ground zone · amber: handle region",
                    width=800,
                )
            else:
                st.error("This file could not be decoded.")
            if st.button(
                "Analyze & save recording",
                type="primary",
                disabled=not (ok and permitted and session.strip()),
            ):
                out = None
                try:
                    config.validate()
                    info, out = new_run(source, config.to_dict(), session, split)
                    bar = st.progress(0.0)
                    preview = st.empty()

                    def progress(value, img):
                        bar.progress(value)
                        preview.image(img, channels="BGR", width=800)

                    with analysis_session(out):
                        report = analyze(
                            out / info["source"],
                            out,
                            config=config,
                            max_seconds=limit,
                            progress=progress,
                            model_path=models.get(selected),
                        )
                    bar.progress(1.0)
                    st.success(
                        f"Saved {len(report['events'])} activity events and {len(read_json(out / 'windows.json'))} review windows. Open Review & label."
                    )
                    for warning in report["warnings"]:
                        st.warning(warning)
                except Exception as exc:
                    st.error(f"Analysis failed: {exc}")

elif page == "Live camera":
    from live import LiveMonitor

    @st.cache_resource
    def local_monitor():
        return LiveMonitor()

    monitor = local_monitor()
    st.title("Try a local camera")
    st.write(
        "Connect a USB camera or use a local webcam to test activity cues. This view stays on this computer and does not send phone notifications."
    )
    camera = st.number_input("Local camera index", 0, 9, 0)
    profile = st.selectbox("Camera calibration", list(profiles))
    minutes = st.slider("Automatically stop after (minutes)", 1, 10, 2)
    consent = st.checkbox(
        "Start this camera and save event snapshots locally. I have permission to record this scene."
    )
    a, b = st.columns(2)
    if a.button("Start camera", type="primary", disabled=not consent):
        try:
            monitor.start(camera, CameraConfig.from_dict(profiles[profile]), minutes)
        except Exception as exc:
            st.error(str(exc))
    if b.button("Stop camera"):
        monitor.stop()
    st.caption(
        "Closing the tab does not stop the session. Use Stop camera or wait for the automatic time limit. Live sessions save event snapshots and logs, not full video or audio. Device access has not been hardware-tested here."
    )

    @st.fragment(run_every="1s")
    def live_view():
        import time

        state = monitor.snapshot()
        st.write("Session status:", state["status"])
        if state["error"]:
            st.error(state["error"])
        if state.get("warning"):
            st.warning(state["warning"])
        if (
            state["status"] == "running"
            and state["last_frame"]
            and time.time() - state["last_frame"] > 3
        ):
            st.warning("Frames are delayed. Do not treat this view as current.")
        if state["frame"]:
            st.image(state["frame"], width=800)
        if state["events"]:
            st.dataframe(
                pd.DataFrame(state["events"])[["time", "track", "kind"]],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption(
                "No recorded activity cues in this session. This is not a safety assessment."
            )

    live_view()

elif page == "Review & label":
    st.title("Review the evidence")
    meta, out = select_run()
    if out:
        report = read_json(out / "report.json")
        windows = read_json(out / "windows.json", [])
        st.caption(
            f"{report['duration_seconds']:.1f}s analyzed · {report['sampled_frames']} sampled frames · {meta['split']} split · {meta['origin']} footage"
        )
        for warning in report.get("warnings", []):
            st.warning(warning)
        t1, t2, t3 = st.tabs(["Activity events", "Training windows", "Export"])
        with t1:
            events = report["events"]
            if not events:
                st.info(
                    "No configured events detected. This is not a safety assessment. You can still label ordinary activity in Training windows."
                )
            for event in events:
                with st.expander(
                    f"{event['time']:.1f}s · {event['kind'].replace('_', ' ')} · track {event['track']}"
                ):
                    st.write(event["description"])
                    a, b = st.columns([1.5, 1])
                    with a:
                        if event.get("clip"):
                            st.video(str(out / event["clip"]))
                        else:
                            st.image(str(out / event["image"]))
                    with b:
                        choices = [
                            "unreviewed",
                            "useful observation",
                            "ordinary activity",
                            "tracking error",
                        ]
                        review = st.selectbox(
                            "Event review",
                            choices,
                            index=choices.index(event.get("review", "unreviewed"))
                            if event.get("review") in choices
                            else 0,
                            key=f"{meta['id']}-{event['id']}",
                        )
                        if st.button("Save event review", key=f"save-{meta['id']}-{event['id']}"):
                            try:
                                save_event_review(out, event["id"], review)
                                report = read_json(out / "report.json")
                                st.success("Saved.")
                            except (ValueError, OSError) as exc:
                                st.error(str(exc))
                        st.caption(
                            "Event feedback does not automatically label model-training windows."
                        )
        with t2:
            st.write(
                "Label the activity of the selected track over this entire 8-second window. Choose Exclude if the track is wrong, obscured, or the window contains ambiguous mixed activity."
            )
            if windows:
                lookup = {w["id"]: w for w in windows}
                wid = st.selectbox(
                    "Track window",
                    list(lookup),
                    format_func=lambda k: (
                        f"{lookup[k]['start']:.1f}–{lookup[k]['end']:.1f}s · track {lookup[k]['track']} · {lookup[k]['label']}"
                    ),
                )
                item = lookup[wid]
                a, b = st.columns([1.5, 1])
                clip = out / f"window-{wid}.mp4"
                with a:
                    if not clip.exists():
                        if st.button("Prepare window clip"):
                            try:
                                extract_track_clip(
                                    out / meta["source"],
                                    clip,
                                    item["start"],
                                    item["end"],
                                    read_json(out / "samples.json"),
                                    item["track"],
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                    else:
                        st.video(str(clip))
                    st.caption(
                        "The review clip marks the selected track in green. Missing overlays mean the track was not observed at that time."
                    )
                    chart = pd.DataFrame(item["sequence"], columns=NAMES)
                    st.line_chart(chart[["in_zone", "wrist_visible", "wrist_in_zone"]], height=180)
                with b:
                    st.write(f"Track {item['track']} · window {wid}")
                    if item.get("prediction"):
                        st.write(
                            "Experimental model suggestion:",
                            item["prediction"]["label"],
                        )
                        st.caption(item["prediction"]["note"])
                    options = ["unreviewed"] + LABELS + ["exclude"]
                    label = st.selectbox(
                        "Human label",
                        options,
                        index=options.index(item["label"]),
                        key=f"label-{meta['id']}-{wid}",
                    )
                    st.caption(
                        "ordinary_activity = ordinary pass-by or routine interaction; lingering = sustained presence; repeated_approach = multiple approaches; hand_near_zone = estimated wrist in the marked region. These labels do not describe intent."
                    )
                    if st.button("Save window label", type="primary"):
                        try:
                            save_review(out, wid, label)
                            windows = read_json(out / "windows.json", [])
                            st.success("Saved. The training dataset updates automatically.")
                        except (ValueError, OSError) as exc:
                            st.error(str(exc))
            else:
                st.info("No track lasted long enough to make a review window.")
        with t3:
            st.download_button(
                "Download event report",
                json.dumps(report, indent=2),
                "carwatch-report.json",
                "application/json",
            )
            st.download_button(
                "Download labeled feature windows",
                json.dumps(windows, indent=2),
                "carwatch-windows.json",
                "application/json",
            )
            if st.button("Prepare evidence ZIP"):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
                    for path in out.iterdir():
                        if path.name.startswith(("source", ".")) or not path.is_file():
                            continue
                        z.write(path, path.name)
                st.download_button(
                    "Save evidence bundle",
                    buffer.getvalue(),
                    f"carwatch-{meta['id'][:8]}.zip",
                    "application/zip",
                )

elif page == "Train models":
    st.title("Train from reviewed activity")
    st.write(
        "A small custom recurrent model learns from sequences of body position, zone membership, estimated wrists and motion. It classifies observable activity across an 8-second window."
    )
    t1, t2, t3 = st.tabs(["Real recordings", "Synthetic demonstration", "Model registry"])
    with t1:
        rows = dataset_rows(real_only=True)
        st.metric("Human-labeled windows", len(rows))
        if rows:
            counts = pd.crosstab(
                pd.Series([r["label"] for r in rows], name="activity"),
                pd.Series([r["split"] for r in rows], name="split"),
            )
            st.dataframe(counts, width="stretch")
        st.caption(
            "Training requires all 4 activities in train, validation and test, at least 2 examples per activity per split. This minimum checks the pipeline; a useful field model needs substantially more varied data."
        )
        from temporal import validate_dataset

        eligible = False
        try:
            validate_dataset(rows)
            eligible = True
            st.success(
                "Dataset passes structural checks. Human label quality and field coverage still need review."
            )
        except ValueError as exc:
            st.info(str(exc))
        epochs = st.slider("Training epochs", 10, 150, 60, 10)
        if st.button("Train custom model", type="primary", disabled=not eligible):
            from temporal import fit

            out = (
                ROOT
                / "models"
                / (
                    "activity-"
                    + datetime.now().strftime("%Y%m%d-%H%M%S")
                    + "-"
                    + uuid.uuid4().hex[:5]
                )
            )
            bar = st.progress(0.0)
            try:
                card = fit(
                    rows,
                    out,
                    epochs=epochs,
                    progress=lambda p, h: bar.progress(
                        p,
                        text=f"Epoch {h['epoch']} · validation loss {h['val_loss']:.3f}",
                    ),
                )
                st.success(
                    "Training complete. Saved in the model registry; available for optional scoring during video analysis."
                )
                st.json({k: card[k] for k in ["origin", "best_epoch", "test"]})
            except Exception as exc:
                st.error(str(exc))
        st.download_button(
            "Export reviewed training dataset",
            json.dumps(rows, indent=2),
            "carwatch-dataset.json",
            "application/json",
        )
    with t2:
        st.warning(
            "Generated movement sequences only. This demonstration is not trained on camera footage and cannot be selected for real-video scoring."
        )
        path = ROOT / "models" / "synthetic-demo"
        if st.button("Run synthetic training exercise"):
            from demo import synthetic_dataset
            from temporal import fit

            bar = st.progress(0.0)
            card = fit(
                synthetic_dataset(),
                path,
                epochs=50,
                allow_synthetic=True,
                progress=lambda p, h: bar.progress(p),
            )
            st.success("Synthetic exercise complete.")
        card = read_json(path / "model.json")
        if card:
            st.write(
                f"Custom GRU trained for {card['epochs']} epochs on generated sequences. Best validation epoch: {card['best_epoch']}."
            )
            st.line_chart(
                pd.DataFrame(card["history"]).set_index("epoch")[["train_loss", "val_loss"]],
                height=220,
            )
            from demo import synthetic_dataset
            from temporal import Predictor

            pattern = st.selectbox("Explore a generated pattern", LABELS)
            sample = next(
                r for r in synthetic_dataset(seed=71, per_class=1) if r["label"] == pattern
            )
            prediction = Predictor(path, allow_demo=True).predict(sample["sequence"])
            st.write("Demonstration prediction:", prediction["label"])
            st.line_chart(
                pd.DataFrame(sample["sequence"], columns=NAMES)[
                    ["in_zone", "wrist_in_zone", "foot_x"]
                ],
                height=200,
            )
            st.caption(
                "A high score here only shows that the model learned these generated patterns."
            )
    with t3:
        cards = list((ROOT / "models").glob("*/model.json"))
        if not cards:
            st.caption("No models saved yet.")
        for path in cards:
            card = read_json(path)
            with st.expander(f"{path.parent.name} · {card['origin']}"):
                st.write(card["status"])
                st.dataframe(
                    pd.DataFrame(card["test"]["confusion_matrix"], index=LABELS, columns=LABELS),
                    width="stretch",
                )
                st.caption(
                    "Held-out window confusion matrix: rows are human/generated labels; columns are model predictions. This is not a false-alerts-per-hour measurement."
                )
                st.download_button(
                    "Download model card",
                    json.dumps(card, indent=2),
                    path.parent.name + "-model.json",
                    key=path.parent.name,
                )

elif page == "Settings":
    st.title("Your local workspace")
    st.write("Storage:", str(ROOT))
    st.write(
        "Full source recordings, derived clips, keypoint features and labels remain on this computer until deleted. Closing the browser does not delete them."
    )
    st.caption(
        "The server listens on localhost. Remote access, account authentication, cellular hardware and phone push delivery are not implemented. Local camera mode is experimental and requires explicit activation."
    )
    st.subheader("Camera profiles")
    st.json(profiles, expanded=False)
    st.subheader("Delete a recording")
    if runs:
        lookup = {r["id"]: r for r in runs}
        rid = st.selectbox(
            "Recording to remove",
            list(lookup),
            format_func=lambda k: f"{lookup[k]['camera']} · {lookup[k]['session_id']} · {k[:8]}",
        )
        confirm = st.checkbox(
            "Delete this source recording, its clips, events and training labels."
        )
        if st.button("Delete selected recording", disabled=not confirm):
            try:
                delete_run(rid)
                st.success(
                    "Recording removed. Already trained models are unchanged; retrain or delete them if their data should be removed."
                )
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(str(exc))
    st.subheader("Live session records")
    live_paths = {
        p.parent.name: p.parent
        for p in (ROOT / "live").glob("*/session.json")
        if read_json(p).get("status") in ("stopped", "error")
    }
    if live_paths:
        live_id = st.selectbox("Completed live session", list(live_paths))
        delete_live = st.checkbox("Delete this completed live session and its snapshots.")
        if st.button("Delete live session", disabled=not delete_live):
            import shutil

            shutil.rmtree(live_paths[live_id])
            st.rerun()
    st.subheader("Delete a saved model")
    model_paths = {p.parent.name: p.parent for p in (ROOT / "models").glob("*/model.json")}
    if model_paths:
        selected = st.selectbox("Model to remove", list(model_paths))
        confirm_model = st.checkbox("Delete this model and its training manifest.")
        if st.button("Delete selected model", disabled=not confirm_model):
            import shutil

            shutil.rmtree(model_paths[selected])
            st.rerun()
    st.subheader("Hardware integration path")
    st.markdown(
        "1. Test a fixed camera and calibrate each view.\n2. Measure missed events, false alerts per hour and processing delay on full recordings.\n3. Validate camera mounting, automotive power and heat handling.\n4. Add authenticated phone delivery with offline and delayed-alert states.\n5. Evaluate multiple cameras together; current runs remain independent per camera."
    )
