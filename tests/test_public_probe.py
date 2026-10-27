import hashlib
import io

import pytest
import yaml

from public_probe import fetch, match_boxes, measure_samples, person_annotations, run_probe


def test_unsupported_probe_model_rejected_before_download(tmp_path, monkeypatch):
    monkeypatch.setattr("public_probe.fetch", lambda *a, **k: pytest.fail("must not download"))
    with pytest.raises(ValueError, match="supported public pose detector"):
        run_probe(True, tmp_path, detector="arbitrary.pt")


def test_one_detection_cannot_satisfy_two_actors():
    assert len(match_boxes([[0, 0, 1, 1]] * 2, [[0, 0, 1, 1]])) == 1
    assert match_boxes([[0, 0, 0.2, 0.2]], [[0.8, 0.8, 1, 1]]) == []


def test_matching_maximizes_actor_count_before_overlap():
    truth = [[0, 0, 0.5, 1], [0.2, 0, 0.7, 1]]
    predicted = [[0.1, 0, 0.6, 1], [0, 0, 0.4, 1]]
    assert sorted(match_boxes(truth, predicted)) == [(0, 1), (1, 0)]


def test_unannotated_frames_are_not_counted_as_negatives():
    person = dict(features=[1, 0, 0.5, 1, 1, 0, 1, 1, 0, 0])
    result = measure_samples(
        [dict(time=0, people=[person]), dict(time=1, people=[])], {0: [[0, 0, 1, 1]]}, 30
    )
    assert result["annotated_person_samples"] == 1 and result["matched_person_samples"] == 1
    with pytest.raises(ValueError, match="No sampled"):
        measure_samples([dict(time=1, people=[])], {0: [[0, 0, 1, 1]]}, 30)


def test_annotation_alignment_and_types(tmp_path):
    types = tmp_path / "types.yml"
    geometry = tmp_path / "geom.yml"
    types.write_text(yaml.safe_dump([dict(types=dict(id1=1, cset3=dict(Person=1.0)))]))
    row = dict(id1=1, ts0=30, ts1=1, g0="10 20 30 40")
    geometry.write_text(yaml.safe_dump([dict(geom=row)]))
    assert person_annotations(types, geometry, 100, 100, 30) == {30: [[0.1, 0.2, 0.3, 0.4]]}
    row["ts1"] = 3
    geometry.write_text(yaml.safe_dump([dict(geom=row)]))
    with pytest.raises(ValueError, match="alignment"):
        person_annotations(types, geometry, 100, 100, 30)


def test_probe_download_is_explicit_and_validates_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("public_probe.urllib.request.urlopen", lambda *a, **k: pytest.fail())
    with pytest.raises(ValueError, match="--download"):
        fetch("fixture.avi", tmp_path, 100)
    (tmp_path / "fixture.avi").write_bytes(b"incorrect fixture")
    with pytest.raises(ValueError, match="checksum"):
        fetch("fixture.avi", tmp_path, 100, expected_hash="0" * 64)


@pytest.mark.parametrize("failure", ["header", "body", "checksum"])
def test_bad_download_never_publishes_partial_fixture(tmp_path, monkeypatch, failure):
    response = io.BytesIO(b"fixture bytes")
    response.headers = {"Content-Length": "200" if failure == "header" else "0"}
    monkeypatch.setattr("public_probe.urllib.request.urlopen", lambda *a, **k: response)
    with pytest.raises(ValueError):
        fetch(
            "fixture.avi",
            tmp_path,
            5 if failure == "body" else 100,
            allow_download=True,
            expected_hash="0" * 64,
        )
    assert not list(tmp_path.iterdir())


def test_download_publishes_verified_bytes_and_reuses_cache(tmp_path, monkeypatch):
    data = b"fixture bytes"
    calls = []

    def response(*args, **kwargs):
        calls.append(args[0])
        stream = io.BytesIO(data)
        stream.headers = {"Content-Length": str(len(data))}
        return stream

    monkeypatch.setattr("public_probe.urllib.request.urlopen", response)
    digest = hashlib.sha256(data).hexdigest()
    assert fetch("fixture.avi", tmp_path, 100, True, digest).read_bytes() == data
    assert fetch("fixture.avi", tmp_path, 100, True, digest).read_bytes() == data
    assert len(calls) == 1 and len(list(tmp_path.iterdir())) == 1
