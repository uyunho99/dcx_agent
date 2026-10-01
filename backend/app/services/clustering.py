import numpy as np
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.s3 import load_data, save_jsonl
from app.services.voyage import get_embeddings
from app.jobs.manager import job_manager
from app.context import store
from app.context.stale import clear_stale
from app.known.filter import read_export
from app.known.store import prepared_root
from app.vectors.store import VectorStore


def run_clustering(config: dict) -> None:
    """Cluster exported documents using stage-three vectors (legacy: Voyage)."""
    sid = config.get("sid", "s0")
    num_clusters = config.get("num_clusters", 0)
    job_manager.set("cluster", sid, {"status": "running", "phase": "loading", "progress": 0})

    try:
        run_version = None
        session = store.load_session(sid) or {}
        if session and not store.is_legacy(session):
            with store.locked(sid):
                session = store.assert_writable(sid)
                run_version = session['version']
                data = read_export(sid, session)
                root = prepared_root(sid, session)
                if root is None:
                    raise ValueError("3단계 벡터가 없습니다")
                ids, vectors = VectorStore(root).get([doc['doc_id'] for doc in data])
                usable = {doc_id: vector for doc_id, vector in zip(ids, vectors)
                          if np.isfinite(vector).all() and np.linalg.norm(vector) > 0}
                data = [doc for doc in data if doc['doc_id'] in usable]
                X = np.asarray([usable[doc['doc_id']] for doc in data])
        else:
            data = load_data(f"classified/{sid}/relevant_")
            if not data:
                data = load_data(f"preprocessed/{sid}/")
            X = np.asarray(get_embeddings([f"{d.get('title', '')} {d.get('desc', '')}" for d in data])) if data else np.empty((0, 0))
        if not data:
            job_manager.set("cluster", sid, {"status": "error", "error": "no data"})
            return
        texts = [f"{d.get('title', '')} {d.get('desc', '')}" for d in data]

        job_manager.update("cluster", sid, progress=40, phase="clustering")

        # Auto-determine k
        if num_clusters == 0:
            best_k, best_score = 5, -1
            for k in range(3, min(15, len(data) // 10 + 1)):
                try:
                    km = KMeans(n_clusters=k, random_state=42, n_init=10)
                    lbls = km.fit_predict(X)
                    score = silhouette_score(X, lbls)
                    if score > best_score:
                        best_k, best_score = k, score
                except Exception:
                    pass
            num_clusters = best_k

        job_manager.update("cluster", sid, progress=60)
        num_clusters = max(1, min(num_clusters, len(data)))
        kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        job_manager.update("cluster", sid, progress=80)

        # Top keywords via TF-IDF
        vec = TfidfVectorizer(max_features=3000, ngram_range=(1, 2), min_df=2, max_df=0.95)
        try:
            tfidf = vec.fit_transform(texts)
            fnames = list(vec.get_feature_names_out())
        except Exception:
            fnames = []

        clusters = {}
        for i in range(num_clusters):
            idxs = [j for j, l in enumerate(labels) if l == i]
            if idxs and fnames:
                tfidf_mean = tfidf[idxs].mean(axis=0).A1
                top_kw = [fnames[x] for x in tfidf_mean.argsort()[-10:][::-1]]
            else:
                top_kw = []
            samples = []
            for j in idxs[:3]:
                samples.append({
                    "title": data[j].get("title", "")[:80],
                    "desc": data[j].get("desc", "")[:150],
                    "cafe": data[j].get("cafe", ""),
                    "kw": data[j].get("kw", ""),
                })
            clusters[str(i)] = {
                "id": i, "size": len(idxs), "keywords": top_kw,
                "name": " / ".join(top_kw[:3]), "samples": samples,
            }

        for i, item in enumerate(data):
            item["cluster"] = int(labels[i])

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for cid in range(num_clusters):
            cdata = [d for d in data if d.get("cluster") == cid]
            save_jsonl(f"clusters/{sid}/cluster_{cid}_{ts}.jsonl", cdata)

        if run_version is not None:
            with store.locked(sid):
                # A version switch during computation must not complete either
                # the now-readonly source or the new active version.
                store.assert_writable(sid, run_version)
                store._update_locked(sid, {'clustering': {
                    'status': 'done', 'version': run_version, 'at': store.now(),
                }})
                clear_stale(sid, run_version, 'stage6', already_locked=True)

        job_manager.set("cluster", sid, {
            "status": "done", "progress": 100,
            "num_clusters": num_clusters, "total": len(data), "clusters": clusters,
        })
    except Exception as e:
        job_manager.set("cluster", sid, {"status": "error", "error": str(e)})


def refine_clusters(config: dict) -> dict:
    """Refine clusters: keep/merge selected clusters."""
    sid = config.get("sid", "s_unknown")
    keep = config.get("keepClusters", [])
    merge = config.get("mergeClusters", [])

    try:
        all_data = load_data(f"clusters/{sid}/cluster_")
        if keep:
            all_data = [d for d in all_data if d.get("cluster") in set(keep)]
        if merge and len(merge) > 1:
            for item in all_data:
                if item.get("cluster") in set(merge):
                    item["cluster"] = merge[0]

        unique = sorted(set(d.get("cluster", -1) for d in all_data))
        cmap = {old: new for new, old in enumerate(unique)}
        for item in all_data:
            item["cluster"] = cmap.get(item.get("cluster", -1), 0)

        texts = [f"{d.get('title', '')} {d.get('desc', '')}" for d in all_data]
        vec = TfidfVectorizer(max_features=3000, ngram_range=(1, 2), min_df=2, max_df=0.95)
        X = vec.fit_transform(texts)
        fnames = list(vec.get_feature_names_out())

        clusters_info = {}
        for cid in range(len(unique)):
            idxs = [j for j, d in enumerate(all_data) if d.get("cluster") == cid]
            cdata = [all_data[j] for j in idxs]
            if idxs:
                tfidf_mean = X[idxs].mean(axis=0).A1
                top_kw = [fnames[x] for x in tfidf_mean.argsort()[-10:][::-1]]
            else:
                top_kw = []
            samples = [
                {"title": d.get("title", "")[:80], "desc": d.get("desc", "")[:150], "cafe": d.get("cafe", "")}
                for d in cdata[:5]
            ]
            clusters_info[str(cid)] = {
                "id": cid, "size": len(cdata), "keywords": top_kw, "samples": samples, "name": "",
            }

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_jsonl(f"clusters_refined/{sid}/data_{ts}.jsonl", all_data)

        return {
            "status": "done", "kept_clusters": len(unique),
            "total_docs": len(all_data), "clusters": clusters_info,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
