"""Offline fixture authoring only; never imported by tests or production.

Run with backend's venv. Serializes each boundary, then reads it for the next.
Numeric construction and deliberately small synthetic scoring rules: README.md.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_samples, silhouette_score

ROOT = Path(__file__).parent
TS = "20260918_120000"
TOPICS = [
    ("심박 워치 확인", "운동 중 심박을 확인하려고 워치와 이어폰을 함께 착용한다", "기기를 두 개 챙겨야 함"),
    ("배터리 충전 준비", "외출 전 배터리를 확인하고 충전 케이블을 챙긴다", "충전 준비에 시간이 듦"),
    ("알림 집중 설정", "일하는 동안 알림을 끄고 집중 시간을 설정한다", "알림 설정을 반복해야 함"),
]


def write(folder, name, obj):
    (folder / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read(folder, name):
    return json.loads((folder / f"{name}.json").read_text(encoding="utf-8"))


def build(session):
    folder = ROOT / f"session_{session}"
    folder.mkdir(exist_ok=True)
    sid = f"golden-{session}"
    records = []
    for group, (keywords, sentence, _) in enumerate(TOPICS):
        for j, offset in enumerate([-1.0, -.7, -.4, -.2, -.05, .1, .25, .45, .65, .9]):
            n = group * 10 + j + 1
            vector = [0.0] * 8
            vector[group] = 10.0
            vector[3] = offset
            vector[4] = (j % 3) * .07
            vector[5] = (j % 2) * .03
            text = sentence + (". 그러나 오늘은 이 행동이 필요하지 않았다." if j == 9 else f". 사용 기록 {j + 1}.")
            decision = ["auto", "escalated", "human"][j % 3]
            records.append(dict(doc_id=f"d_{n:06d}", author_hash=None if j == 0 else hashlib.sha256(f"golden-salt:{n}".encode()).hexdigest()[:8],
                date=f"2026-09-{j + 1:02d}", decision=decision, label=1,
                reviewed_by="golden-reviewer" if decision == "human" else None,
                relevance_score=round(.99 - .01 * j, 2), text=text, keywords=keywords.split(),
                embedding=vector, kw=keywords.split()[0], title=keywords, desc=text, body=text,
                link=f"https://example.invalid/docs/{n}", cafe="합성 연구 모임"))
    known = []
    if session == "a":
        for i in range(5):
            v = [0.0] * 8
            v[i % 3] = 10.0
            v[6] = i * .1
            known.append(dict(id=f"ki_{i + 1:02d}", text=TOPICS[i % 3][1] + f" (기준 {i + 1})", embedding=v))
    write(folder, "classified", dict(sid=sid, timestamp=TS, known_insights=known, records=records,
        run=dict(alpha=.03, escalate_threshold=.62, calibration=dict(n=30, agreement=.9, disagreements=3),
                 ensemble=dict(models=["synthetic"], scores={"synthetic": .9}, combined=.9),
                 counts=dict(total=30, **Counter(d["decision"] for d in records)))))

    source = read(folder, "classified")
    docs = source["records"]
    x = np.array([d["embedding"] for d in docs])
    fits = {k: KMeans(n_clusters=k, random_state=42, n_init=10).fit(x) for k in range(3, 15)}
    scan = [[k, float(silhouette_score(x, fit.labels_))] for k, fit in fits.items()]
    fit = fits[3]
    # Canonical labels: order by first source document, independent of KMeans label numbering.
    raw_labels = sorted(set(fit.labels_), key=lambda label: int(np.flatnonzero(fit.labels_ == label)[0]))
    sil = silhouette_samples(x, fit.labels_)
    clusters = []
    avg_length = len(docs) / 3 * 3  # whitespace keyword tokens in an aggregated class
    for i, raw in enumerate(raw_labels):
        idx = np.flatnonzero(fit.labels_ == raw)
        rows = [docs[j] for j in idx]
        center = x[idx].mean(axis=0)
        distances = np.linalg.norm(x[idx] - center, axis=1)
        p50, p90 = np.percentile(distances, [50, 90])
        members = [dict(doc_id=d["doc_id"], dist_centroid=float(dist), band="core" if dist <= p50 else "fringe" if dist <= p90 else "edge") for d, dist in zip(rows, distances)]
        counts = Counter(m["band"] for m in members)
        words = Counter(t for d in rows for t in d["keywords"])
        total_words = Counter(t for d in docs for t in d["keywords"])
        weights = [[w, count / sum(words.values()) * float(np.log(1 + avg_length / total_words[w]))] for w, count in sorted(words.items())]
        clusters.append(dict(cluster_id=f"CL{i}", label=TOPICS[i][0], c_tfidf=weights,
            size=len(rows), authors=len({d["author_hash"] for d in rows} - {None}), centroid=center.tolist(),
            silhouette=float(sil[idx].mean()), k_scan=scan, band_thresholds=dict(p50=float(p50), p90=float(p90)),
            bands={b: counts[b] / len(rows) for b in ("core", "fringe", "edge")}, documents=members,
            dominant_constraint=TOPICS[i][2]))
    write(folder, "clusters", dict(sid=sid, timestamp=TS, primary_method="embedding", clusters=clusters))

    clusters = read(folder, "clusters")["clusters"]
    personas = []
    for c in clusters:
        personas.append(dict(persona_id=c["cluster_id"] + "-P1", cluster_id=c["cluster_id"], name=c["label"] + " 사용자",
            desire=c["label"] + " 과정을 간단하게 끝내고 싶다", goals=[c["label"] + " 준비 시간을 줄인다"],
            centrality_top=[[w, 1 / np.sqrt(3)] for w, _ in c["c_tfidf"]], modularity_q=0.0,
            size=c["size"], authors=c["authors"], status="confirmed", doc_ids=[d["doc_id"] for d in c["documents"]]))
    write(folder, "personas", dict(schema_version=2, sid=sid, timestamp=TS, personas=personas))

    by_id = {d["doc_id"]: d for d in docs}
    for p in read(folder, "personas")["personas"]:
        cid, pid = p["cluster_id"], p["persona_id"]
        c = next(c for c in clusters if c["cluster_id"] == cid)
        center = min(c["documents"], key=lambda d: (d["dist_centroid"], d["doc_id"]))
        members = [d for d in c["documents"] if d["doc_id"] != center["doc_id"]]
        actions = []
        evidence = []
        for aidx, subset in enumerate([members[:7], members[7:]], 1):
            aid, ctx = f"{pid}-A{aidx}", f"{pid}-C{aidx}"
            actions.append(dict(action_id=aid, context_id=ctx, sentence=by_id[subset[0]["doc_id"]]["text"], lda_topic=aidx - 1,
                                topic_weight=len(subset) / len(members), docs=len(subset), doc_ids=[d["doc_id"] for d in subset]))
            for m in subset:
                j = members.index(m)
                d = by_id[m["doc_id"]]
                v = np.array(d["embedding"])
                known = max([0.0] + [float(np.dot(v, k["embedding"]) / (np.linalg.norm(v) * np.linalg.norm(k["embedding"]))) for k in source["known_insights"]])
                relevance, rarity = .95 - j * .01, j / 10
                quality = relevance * (1 - .5 * known) * (1 + .3 * rarity) if source["known_insights"] else relevance
                evidence.append(dict(doc_id=d["doc_id"], cluster_id=cid, persona_id=pid, context_id=ctx, action_id=aid,
                    quote=d["text"], role="refute" if j == 8 else "support", relevance=relevance, known=known,
                    max_sim_to_known=known, rarity=rarity, combo_rarity=rarity, quality=quality,
                    dims=[["Sense", "Feel"], ["Think", "Act"], ["Relate", "Outcome"]][j % 3], band=m["band"], source="auto"))
        for score in ("relevance", "quality"):
            for rank, e in enumerate(sorted(evidence, key=lambda e: (-e[score], e["doc_id"])), 1):
                e[f"rank_{score}"] = rank
        write(folder, f"evidence_{pid}", dict(sid=sid, timestamp=TS, persona_id=pid, cluster_id=cid, actions=actions,
            centroid_sentence=dict(doc_id=center["doc_id"], text=by_id[center["doc_id"]]["text"], dist_centroid=center["dist_centroid"]),
            evidence=sorted(evidence, key=lambda e: e["rank_quality"]),
            coverage=dict(dims=sorted({dim for e in evidence for dim in e["dims"]}), min=4),
            warnings=[] if source["known_insights"] else ["KNOWN_INSIGHTS_EMPTY"]))

        ep = read(folder, f"evidence_{pid}")
        columns = []
        for index, a in enumerate(ep["actions"]):
            scoped = [e for e in ep["evidence"] if e["action_id"] == a["action_id"]]
            scoped.sort(key=lambda e: e["doc_id"])
            cell = lambda e: dict(text=e["quote"], grade="confirmed", cites=[e["doc_id"]])
            measurements = [dict(doc_id=e["doc_id"], importance=8.0 if index == 0 else 4.0,
                                 satisfaction=5.0 if index == 0 else 8.0) for e in scoped]
            importance = sum(m["importance"] for m in measurements) / len(measurements)
            satisfaction = sum(m["satisfaction"] for m in measurements) / len(measurements) if len(measurements) >= 6 else None
            columns.append(dict(action_id=a["action_id"], context_id=a["context_id"], context=cell(scoped[0]), action=cell(scoped[-1]),
                barrier=dict(text="반복 준비로 다음 사용을 미룰 수 있다", grade="speculated", cites=[]) if index == 0 else None,
                barrier_gen_fail=index == 1, measurements=measurements, importance=importance,
                satisfaction_n=len(measurements), satisfaction=satisfaction,
                odi=None if satisfaction is None else importance + max(importance - satisfaction, 0)))
        grades = Counter(cell["grade"] for col in columns for key in ("context", "action", "barrier") if (cell := col[key]) is not None)
        write(folder, f"cam_{pid}", dict(sid=sid, timestamp=TS, persona_id=pid, columns=columns,
            constants=dict(satisfaction_min_n=6), grades=dict(**grades, ratio_spec=grades["speculated"] / sum(grades.values()))))


if __name__ == "__main__":
    for session in ("a", "b"):
        build(session)
