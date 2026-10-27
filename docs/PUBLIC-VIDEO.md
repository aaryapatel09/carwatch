# Public video development probe

The first real-motion probe uses MEVA's `2018-03-12.10-00-02.10-05-02.school.G339.r13.avi`, a 1920 × 1080, 30 fps parking-lot recording with example annotations for opening and closing a vehicle door. MEVA was released by Kitware Inc. and IARPA under [CC BY 4.0](https://mevadata.org/resources/MEVA-data-license.txt). [Dataset and access information](https://mevadata.org/resources/README-meva-kf1-data.html).

Carwatch analyzed the first 106 seconds at 4 Hz with YOLO11n-pose, image size 640 and confidence threshold 0.35. Only the supplied **Person** annotations were measured, using one-to-one box matching at intersection-over-union (IoU) ≥ 0.5. This produced 17 annotated person samples from two short interactions. Unannotated frames and other people were not treated as negatives.

| Configuration | Matched / annotated person samples |
|---|---:|
| Full image | 0 / 17 |
| Focused detection region | 7 / 17 |

The focused region is `(190, 180, 540, 490)` in source pixels. It was selected after inspecting the full-image failure, so these are **development results**, not independent validation. Detection coordinates and estimated wrists are mapped back to the original image. The focused result still misses people. It does not justify unattended safety use, even on similar-looking scenes.

There is no measurement here of activity-class accuracy, actual handle contact, malicious intent, false alerts per hour, or accuracy of the estimated wrist locations. No weights were trained on this footage, and its annotations were not converted into the app's four human activity labels. The camera viewpoint also differs from a camera mounted on a car.

## Reproduce

```sh
python scripts/probe_meva.py --download
python scripts/probe_meva.py --focused
```

The first command explicitly permits a bounded 182 MB download from the dataset's public S3 bucket. Source, annotations, derived clips and measurement JSON stay under `runtime/public-data/meva/`, excluded from Git. Each run creates its own `probe-*` folder; `latest-measurement.json` points to the latest measurement. The downloaded video is unchanged; evidence clips are silent, scaled and annotated by Carwatch. These public test artifacts can be removed from that directory when no longer needed. They are not added to the training dataset or the app's recording history.

The manually dispatched CV integration workflow has an optional `public_probe` input to run both configurations on Linux. It is off by default. A completed measurement step confirms that the probe ran; it does not mean the detector met a performance target.

Video SHA-256: `f76858fd66fd38500d7e7a716ee15662f557d0af54bd06489c6acd94d24ac020`. Each report records annotation hashes, settings and scope. Do not repeatedly tune on this clip and then describe it as held-out data. Use different recording sessions and intended camera hardware for subsequent evaluation.

Reference: Corona, Osterdahl, Collins and Hoogs, *MEVA: A Large-Scale Multiview, Multimodal Video Dataset for Activity Detection*, WACV 2021, pp. 1060–1068. Dataset attribution: Multiview Extended Video with Activities (MEVA), Kitware Inc. and IARPA.
