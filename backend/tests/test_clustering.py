"""STEP 07 contracts; all storage and vectors are offline."""
import importlib
import json
import math
import sys
from types import ModuleType

import numpy as np
import pytest
from sklearn.metrics import adjusted_rand_score, silhouette_score

from app.jobs.manager import job_manager
from app.services import s3


@pytest.fixture
def service(monkeypatch):
    # Guard the old implementation's Voyage boundary as well during RED.
    voyage = ModuleType("app.services.voyage")
    def forbidden(*args, **kwargs):
        raise AssertionError("STEP 07 must use supplied embeddings")
    voyage.get_embeddings = forbidden
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, "app.services.voyage", voyage)
        module = importlib.import_module("app.services.clustering")
    return module


def execute(service, records, local_data_dir, **config):
    sid = "test-clustering"
    s3.save_jsonl(f"classified/{sid}/relevant_20260918_120000.jsonl", records)
    service.run_clustering({"sid": sid, **config})
    job = job_manager.get("cluster", sid)
    assert job["status"] == "done", job
    paths = sorted((local_data_dir / "clusters" / sid).glob("result_*.json"))
    assert paths, "STEP 07 must persist result_{ts}.json"
    result = json.loads(paths[-1].read_text())
    json.dumps(result, allow_nan=False)
    assert job["result_key"].endswith(paths[-1].name)
    return result


def test_e2e_006_schema_scan_and_ctfidf(service, golden_classified, golden_clusters, local_data_dir):
    result = execute(service, golden_classified()["records"], local_data_dir)
    assert result["primary_method"] == "embedding"
    assert result["selected_k"] == 3
    assert result["selection_reason"] == "maximum_silhouette; ties_choose_smaller_k"
    assert [k for k, _ in result["k_scan"]] == list(range(3, 15))
    assert all(math.isfinite(score) for _, score in result["k_scan"])
    assert result["silhouette"] == pytest.approx(max(s for _, s in result["k_scan"]))
    for actual, expected in zip(result["clusters"], golden_clusters()["clusters"], strict=True):
        assert actual["cluster_id"] == expected["cluster_id"]
        for key in ("size", "authors"):
            assert actual[key] == expected[key]
        assert actual["centroid"] == pytest.approx(expected["centroid"])
        assert actual["silhouette"] == pytest.approx(expected["silhouette"])
        assert np.asarray(actual["k_scan"]) == pytest.approx(np.asarray(expected["k_scan"]))
        assert dict(actual["c_tfidf"]) == pytest.approx(dict(expected["c_tfidf"]))
        assert isinstance(actual["label"], str) and actual["label"]
        assert isinstance(actual["dominant_constraint"], str)


def test_neg_002_ward_has_no_cluster_id_and_comparison_is_measured(service, golden_classified, local_data_dir):
    records = golden_classified()["records"]
    # Even pre-existing primary IDs must never leak into Ward records.
    for record in records:
        record["cluster_id"] = "CL-old"
    result = execute(service, records, local_data_dir)
    ward = result["ward"]
    def assert_no_id(value):
        if isinstance(value, dict):
            assert "cluster_id" not in value
            for child in value.values():
                assert_no_id(child)
        elif isinstance(value, list):
            for child in value:
                assert_no_id(child)
    assert_no_id(ward)
    assert ward["method"] == "ward"
    assignments = {d["doc_id"]: c["cluster_id"] for c in result["clusters"] for d in c["documents"]}
    primary = [assignments[r["doc_id"]] for r in records]
    assert [d["doc_id"] for d in ward["documents"]] == [r["doc_id"] for r in records]
    labels = [d["label"] for d in ward["documents"]]
    assert len(set(labels)) == result["selected_k"]
    assert result["comparison"]["adjusted_rand_index"] == pytest.approx(adjusted_rand_score(primary, labels))
    assert ward["silhouette"] == pytest.approx(silhouette_score([r["embedding"] for r in records], labels))
    assert result["comparison"]["silhouette_delta"] == pytest.approx(result["silhouette"] - ward["silhouette"])


def test_edge_003_004_distances_bands_and_full_records_preserved(service, golden_classified, local_data_dir):
    records = golden_classified()["records"]
    result = execute(service, records, local_data_dir)
    source = {r["doc_id"]: r for r in records}
    seen = []
    for cluster in result["clusters"]:
        docs = cluster["documents"]
        distances = [np.linalg.norm(np.array(source[d["doc_id"]]["embedding"]) - cluster["centroid"]) for d in docs]
        p50, p90 = np.percentile(distances, [50, 90])
        assert cluster["band_thresholds"] == pytest.approx({"p50": p50, "p90": p90})
        assert sum(cluster["bands"].values()) == pytest.approx(1)
        assert cluster["bands"]["edge"] > 0
        for doc, distance in zip(docs, distances, strict=True):
            assert doc["dist_centroid"] == pytest.approx(distance)
            assert doc["band"] == ("core" if distance <= p50 else "fringe" if distance <= p90 else "edge")
            for key, value in source[doc["doc_id"]].items():
                assert doc[key] == value
            seen.append(doc["doc_id"])
    assert sorted(seen) == sorted(source)
    assert result["total"] == len(records)


def test_latest_input_and_restart_status(service, golden_classified, local_data_dir):
    records = golden_classified()["records"]
    s3.save_jsonl("classified/test-clustering/relevant_20000101_000000.jsonl", records[:1])
    s3.save_jsonl("classified/test-clustering/irrelevant_20990101_000000.jsonl", records[:2])
    s3.save_json("classified/test-clustering/run_20990101_000000.json", {"counts": {}})
    result = execute(service, records, local_data_dir)
    from app.routers.clustering import get_cluster_status
    job_manager.set("cluster", "test-clustering", {"status": "not_found"})
    restored = get_cluster_status("test-clustering")
    assert restored["clusters"] == result["clusters"]
    assert restored["ward"] == result["ward"]
    assert restored["status"] == "done"


def test_explicit_k_still_scans(service, golden_classified, local_data_dir):
    result = execute(service, golden_classified()["records"], local_data_dir, num_clusters=4)
    assert result["selected_k"] == 4
    assert result["selection_reason"] == "requested_num_clusters"
    assert len(result["k_scan"]) == 12


@pytest.mark.parametrize("kind", ["empty", "small", "identical", "missing_embedding", "nan", "ragged", "duplicate_id", "invalid_k"])
def test_invalid_input_reports_error_without_partial_result(service, golden_classified, local_data_dir, kind):
    records = golden_classified()["records"]
    config = {"sid": "invalid"}
    if kind == "empty":
        records = []
    elif kind == "small":
        records = records[:3]
    elif kind == "identical":
        for r in records:
            r["embedding"] = [0.0, 0.0]
    elif kind == "missing_embedding":
        del records[0]["embedding"]
    elif kind == "nan":
        records[0]["embedding"][0] = float("nan")
    elif kind == "ragged":
        records[0]["embedding"] = [1.0]
    elif kind == "duplicate_id":
        records[1]["doc_id"] = records[0]["doc_id"]
    else:
        config["num_clusters"] = 15
    s3.save_jsonl("classified/invalid/relevant_20260918_120000.jsonl", records)
    service.run_clustering(config)
    assert job_manager.get("cluster", "invalid")["status"] == "error"
    assert not list(local_data_dir.glob("clusters/invalid/result_*.json"))


def test_small_scan_records_unavailable_k_without_fake_scores(service, golden_classified, local_data_dir):
    records = golden_classified()["records"]
    result = execute(service, records[:2] + records[10:12] + records[20:22], local_data_dir)
    assert [k for k, _ in result["k_scan"]] == [3, 4, 5]
    assert [row["k"] for row in result["k_scan_unavailable"]] == list(range(6, 15))
    assert all(row["reason"] for row in result["k_scan_unavailable"])


def test_constraint_is_observed_metadata_mode_with_provenance(service, golden_classified, local_data_dir):
    records = golden_classified()["records"]
    for i, record in enumerate(records):
        record["context"] = "기기 휴대" if i % 10 < 7 else "실내 운동"
        record["cat"] = "건강"
    result = execute(service, records, local_data_dir)
    for cluster in result["clusters"]:
        assert cluster["dominant_constraint"] == "기기 휴대"
        assert cluster["dominant_constraint_basis"] == {"field": "context", "count": 7, "coverage": 1.0, "share": .7, "method": "observed_metadata_mode"}


def test_tied_distances_are_core_and_empty_vocabulary_is_valid(service, golden_classified, local_data_dir):
    records = golden_classified()["records"]
    for index, record in enumerate(records):
        record["embedding"] = [float(index // 10) * 10, 0.0]
        record["keywords"] = []
        record.pop("kw")
    result = execute(service, records, local_data_dir)
    assert result["selected_k"] == 3
    for cluster in result["clusters"]:
        assert cluster["bands"] == {"core": 1.0, "fringe": 0.0, "edge": 0.0}
        assert cluster["band_thresholds"] == {"p50": 0.0, "p90": 0.0}
        assert cluster["c_tfidf"] == []
        assert cluster["dominant_constraint"] == "unknown"
        assert cluster["dominant_constraint_basis"]["count"] == 0


def test_class_tfidf_uses_corpus_frequency_and_class_lengths(service):
    groups = [[{"keywords": ["a", "a", "b"]}], [{"keywords": ["b"]}]]
    result = service._class_tfidf(groups, 10)
    assert dict(result[0]) == pytest.approx({"a": 2 / 3 * math.log(2), "b": 1 / 3 * math.log(2)})
    assert dict(result[1]) == pytest.approx({"b": math.log(2)})
    assert service._class_tfidf(groups, 1)[0][0][0] == "a"


def test_repeated_runs_restore_latest_snapshot_without_accumulating_documents(service, golden_classified, local_data_dir):
    records = golden_classified()["records"]
    first = execute(service, records, local_data_dir)
    second = execute(service, records, local_data_dir, num_clusters=4)
    assert first["timestamp"] != second["timestamp"]
    assert second["total"] == first["total"] == 30
    key, restored = service.load_latest_result("test-clustering")
    assert restored == second
    assert second["timestamp"] in key


def test_storage_error_does_not_report_done(service, golden_classified, monkeypatch):
    s3.save_jsonl("classified/save-failure/relevant_20260918_120000.jsonl", golden_classified()["records"])
    def fail(*args):
        raise OSError("storage unavailable")
    monkeypatch.setattr(s3, "save_json", fail)
    service.run_clustering({"sid": "save-failure"})
    job = job_manager.get("cluster", "save-failure")
    assert job["status"] == "error"
    assert job["phase"] == "saving"
    assert job["error"] == "storage unavailable"


def test_legacy_refinement_cannot_delete_edge_members(service, golden_classified, local_data_dir):
    result = execute(service, golden_classified()["records"], local_data_dir)
    response = service.refine_clusters({"sid": "test-clustering", "keepClusters": [0], "mergeClusters": [0, 1]})
    assert response["status"] == "error"
    assert service.load_latest_result("test-clustering")[1] == result
