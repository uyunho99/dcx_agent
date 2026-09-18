"""Contract checks only: never import STEP 07–11 business implementations."""
from collections import Counter
from datetime import date
import math
import re
import socket

import numpy as np
import pytest
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_samples, silhouette_score


@pytest.mark.parametrize("session", ["a", "b"])
def test_pipeline_contract(golden_load, session):
    source = golden_load("classified", session)
    docs = source["records"]
    by_id = {d["doc_id"]: d for d in docs}
    assert 20 <= len(docs) <= 40 and len(by_id) == len(docs)
    assert source["sid"] == f"golden-{session}"
    known = source["known_insights"]
    assert (5 <= len(known) <= 10) if session == "a" else known == []
    for k in known:
        assert isinstance(k["id"], str) and isinstance(k["text"], str)
        assert len(k["embedding"]) == 8
    for d in docs:
        assert re.fullmatch(r"d_\d{6}", d["doc_id"])
        assert d["author_hash"] is None or re.fullmatch(r"[0-9a-f]{8}", d["author_hash"])
        assert date.fromisoformat(d["date"]).isoformat() == d["date"]
        assert d["decision"] in {"auto", "escalated", "human"}
        assert type(d["label"]) is int and d["label"] == 1
        assert (d["reviewed_by"] is not None) == (d["decision"] == "human")
        assert 0 <= d["relevance_score"] <= 1
        assert len(d["embedding"]) == 8 and all(math.isfinite(v) for v in d["embedding"])
        assert d["text"] == d["body"] and d["keywords"]
        assert {"kw", "title", "desc", "link", "cafe"} <= d.keys()
    run = source["run"]
    assert {"alpha", "escalate_threshold", "calibration", "ensemble", "counts"} <= run.keys()
    assert run["counts"] == {"total": len(docs), **dict(Counter(d["decision"] for d in docs))}

    clusters = golden_load("clusters", session)
    assert clusters["sid"] == source["sid"] and clusters["primary_method"] == "embedding"
    cs = {c["cluster_id"]: c for c in clusters["clusters"]}
    assert len(cs) == 3
    members = {m["doc_id"]: (c, m) for c in cs.values() for m in c["documents"]}
    assert set(members) == set(by_id)
    assert sum(c["size"] for c in cs.values()) == len(docs)
    x = np.array([d["embedding"] for d in docs])
    labels = [members[d["doc_id"]][0]["cluster_id"] for d in docs]
    silhouettes = silhouette_samples(x, labels)
    scan = []
    for k in range(3, 15):
        km = KMeans(n_clusters=k, random_state=42, n_init=10).fit(x)
        scan.append([k, silhouette_score(x, km.labels_)])
    for c in cs.values():
        rows = c["documents"]
        idx = [i for i, d in enumerate(docs) if d["doc_id"] in {r["doc_id"] for r in rows}]
        centroid = x[idx].mean(axis=0)
        distances = np.linalg.norm(x[idx] - centroid, axis=1)
        assert c["centroid"] == pytest.approx(centroid)
        assert c["silhouette"] == pytest.approx(float(silhouettes[idx].mean()), abs=1e-7)
        assert np.array(c["k_scan"]) == pytest.approx(np.array(scan), abs=1e-7)
        p50, p90 = np.percentile(distances, [50, 90])
        assert c["band_thresholds"] == pytest.approx({"p50": p50, "p90": p90})
        counts = Counter()
        for row, dist in zip(rows, distances):
            assert row["dist_centroid"] == pytest.approx(dist)
            band = "core" if dist <= p50 else "fringe" if dist <= p90 else "edge"
            assert row["band"] == band
            counts[band] += 1
        assert counts["edge"] > 0
        assert c["bands"] == pytest.approx({b: counts[b] / len(rows) for b in ("core", "fringe", "edge")})
        assert c["size"] == len(rows)
        assert c["authors"] == len({by_id[r["doc_id"]]["author_hash"] for r in rows} - {None})
        assert isinstance(c["dominant_constraint"], str)
        assert all(isinstance(t, str) and isinstance(v, (int, float)) for t, v in c["c_tfidf"])
        expected_terms = {t for row in rows for t in by_id[row["doc_id"]]["keywords"]}
        assert {t for t, _ in c["c_tfidf"]} == expected_terms
        assert all(v == pytest.approx(math.log(4) / 3) for _, v in c["c_tfidf"])

    personas = golden_load("personas", session)
    assert personas["schema_version"] == 2 and personas["sid"] == source["sid"]
    ps = personas["personas"]
    assert len({p["persona_id"] for p in ps}) == len(ps) == 3
    assert {d for p in ps for d in p["doc_ids"]} == set(by_id)
    for p in ps:
        pid, cid = p["persona_id"], p["cluster_id"]
        assert re.fullmatch(re.escape(cid) + r"-P[1-9]\d*", pid) and cid in cs
        assert not {"situation", "pain_point", "insight"} & p.keys()
        assert all(members[d][0]["cluster_id"] == cid for d in p["doc_ids"])
        assert isinstance(p["desire"], str) and all(isinstance(g, str) for g in p["goals"])
        assert {t for t, _ in p["centrality_top"]} == {t for t, _ in cs[cid]["c_tfidf"]}
        assert all(v == pytest.approx(1 / math.sqrt(3)) for _, v in p["centrality_top"])
        assert p["modularity_q"] == 0
        assert p["authors"] == cs[cid]["authors"]
        assert p["status"] == "confirmed" and p["size"] == len(p["doc_ids"])
        ep = golden_load("evidence", session, pid)
        assert ep["sid"] == source["sid"] and ep["persona_id"] == pid
        assert ep["cluster_id"] == cid
        actions = {a["action_id"]: a for a in ep["actions"]}
        assert len(actions) == 2
        ev = ep["evidence"]
        centroid = ep["centroid_sentence"]
        assert centroid["doc_id"] in p["doc_ids"]
        assert centroid["text"] == by_id[centroid["doc_id"]]["text"]
        assert centroid["dist_centroid"] == pytest.approx(min(members[d][1]["dist_centroid"] for d in p["doc_ids"]))
        assert centroid["doc_id"] not in {e["doc_id"] for e in ev}
        assert {e["doc_id"] for e in ev} | {centroid["doc_id"]} == set(p["doc_ids"])
        for e in ev:
            assert e["action_id"] in actions
            assert e["persona_id"] == pid and e["cluster_id"] == cid
            assert e["context_id"] == actions[e["action_id"]]["context_id"]
            assert e["quote"] == by_id[e["doc_id"]]["text"]
            assert e["band"] == members[e["doc_id"]][1]["band"]
            assert e["role"] in {"support", "refute"} and e["source"] == "auto"
            assert e["known"] == e["max_sim_to_known"] and e["rarity"] == e["combo_rarity"]
            assert all(0 <= e[key] <= 1 for key in ("relevance", "known", "rarity"))
            v = np.array(by_id[e["doc_id"]]["embedding"])
            sims = [float(np.dot(v, k["embedding"]) / (np.linalg.norm(v) * np.linalg.norm(k["embedding"]))) for k in known]
            assert e["known"] == pytest.approx(max([0.0] + sims), abs=1e-7)
            q = e["relevance"] * (1 - .5 * e["known"]) * (1 + .3 * e["rarity"]) if known else e["relevance"]
            assert e["quality"] == pytest.approx(q, abs=1e-7)
        for score in ("relevance", "quality"):
            ranked = sorted(ev, key=lambda e: (-e[score], e["doc_id"]))
            assert [e[f"rank_{score}"] for e in ranked] == list(range(1, len(ev) + 1))
        if known:
            assert any(e["rank_quality"] != e["rank_relevance"] for e in ev)
            assert ep["warnings"] == []
        else:
            assert ep["warnings"] == ["KNOWN_INSIGHTS_EMPTY"]
            assert all(e["quality"] == e["relevance"] and e["known"] == 0 for e in ev)
        assert set(ep["coverage"]["dims"]) == {dim for e in ev for dim in e["dims"]}
        assert ep["coverage"]["min"] == 4 and len(ep["coverage"]["dims"]) >= 4
        for aid, a in actions.items():
            assert aid.startswith(pid + "-A")
            assert a["docs"] == len(a["doc_ids"])
            assert set(a["doc_ids"]) == {e["doc_id"] for e in ev if e["action_id"] == aid}
            assert isinstance(a["lda_topic"], int) and 0 <= a["topic_weight"] <= 1

        cam = golden_load("cam", session, pid)
        assert cam["sid"] == source["sid"] and cam["persona_id"] == pid
        assert {c["action_id"] for c in cam["columns"]} == set(actions)
        grades = Counter()
        sufficient = insufficient = null_barrier = False
        for col in cam["columns"]:
            a = actions[col["action_id"]]
            assert col["context_id"] == a["context_id"]
            for key in ("context", "action", "barrier"):
                cell = col[key]
                if cell is None:
                    assert key == "barrier" and col["barrier_gen_fail"] is True
                    null_barrier = True
                    continue
                assert isinstance(cell["text"], str)
                assert cell["grade"] in {"confirmed", "speculated"}
                assert set(cell["cites"]) <= set(a["doc_ids"])
                if cell["grade"] == "confirmed":
                    assert cell["cites"]
                grades[cell["grade"]] += 1
            measures = col["measurements"]
            assert {m["doc_id"] for m in measures} == set(a["doc_ids"])
            assert len(measures) == len(a["doc_ids"])
            assert col["importance"] == pytest.approx(sum(m["importance"] for m in measures) / len(measures))
            ratings = [m["satisfaction"] for m in measures if m["satisfaction"] is not None]
            assert col["satisfaction_n"] == len(ratings)
            if len(ratings) < cam["constants"]["satisfaction_min_n"]:
                assert col["satisfaction"] is None and col["odi"] is None
                insufficient = True
            else:
                assert col["satisfaction"] == pytest.approx(sum(ratings) / len(ratings))
                i, s = col["importance"], col["satisfaction"]
                assert col["odi"] == pytest.approx(i + max(i - s, 0))
                sufficient = True
        assert sufficient and insufficient and null_barrier
        assert cam["grades"] == {**grades, "ratio_spec": pytest.approx(grades["speculated"] / sum(grades.values()))}


def test_offline_storage_and_network(local_data_dir):
    from app.services import s3
    s3.save_json("probe/result.json", {"ok": True})
    assert s3.load_json("probe/result.json") == {"ok": True}
    assert (local_data_dir / "probe/result.json").exists()
    s3.save_jsonl("rows/rows.jsonl", [{"doc_id": "d_1"}])
    assert s3.load_data("rows/rows.jsonl") == [{"doc_id": "d_1"}]
    with pytest.raises(RuntimeError, match="Network disabled"):
        socket.create_connection(("example.invalid", 443))
    with socket.socket() as sock:
        with pytest.raises(RuntimeError, match="Network disabled"):
            sock.connect(("127.0.0.1", 443))
    with pytest.raises(RuntimeError, match="Network disabled"):
        socket.getaddrinfo("example.invalid", 443)


def test_loader_returns_independent_copies(golden_classified, golden_clusters, golden_personas, golden_evidence, golden_cam):
    for load in (golden_classified, golden_clusters, golden_personas, golden_evidence, golden_cam):
        one = load()
        one.clear()
        assert load()
