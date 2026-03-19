import json
import numpy as np
from datetime import datetime

from app.services.s3 import load_data, load_json, save_jsonl
from app.config import settings
from app.jobs.manager import job_manager


def train_models(config: dict) -> None:
    """3중 준지도 학습: LSTM + CNN + GRU + LLM 앙상블"""
    sid = config.get("sid", "s0")
    job_manager.set("train", sid, {"status": "running", "phase": "init", "progress": 0})

    try:
        # Load labeled data from session
        labeled = []
        try:
            session = load_json(f"sessions/{sid}/session.json")
            if session:
                labeled = session.get("labeledData", [])
        except Exception:
            pass

        if len(labeled) < 5:
            job_manager.set("train", sid, {"status": "error", "error": "Need at least 5 labeled samples"})
            return

        texts = [f"{d.get('title', '')} {d.get('desc', '')}" for d in labeled]
        labels = [1 if d.get("label") == "relevant" or d.get("label") == 1 else 0 for d in labeled]

        job_manager.update("train", sid, progress=10, phase="preparing")

        # Try tensorflow first, fallback to sklearn
        use_tf = False
        try:
            import tensorflow as tf
            from tensorflow.keras.preprocessing.text import Tokenizer
            from tensorflow.keras.preprocessing.sequence import pad_sequences
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import (
                Embedding, LSTM, GRU, Conv1D, GlobalMaxPooling1D, Dense, Dropout,
            )
            use_tf = True
        except ImportError:
            pass

        if use_tf:
            _train_tensorflow(sid, texts, labels)
        else:
            _train_sklearn(sid, texts, labels)

    except Exception as e:
        job_manager.set("train", sid, {"status": "error", "error": str(e)})


def _train_tensorflow(sid: str, texts: list[str], labels: list[int]) -> None:
    import tensorflow as tf
    from tensorflow.keras.preprocessing.text import Tokenizer
    from tensorflow.keras.preprocessing.sequence import pad_sequences
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import (
        Embedding, LSTM, GRU, Conv1D, GlobalMaxPooling1D, Dense, Dropout,
    )

    MAX_WORDS = 10000
    MAX_LEN = 200

    tokenizer = Tokenizer(num_words=MAX_WORDS, oov_token="<OOV>")
    tokenizer.fit_on_texts(texts)
    sequences = tokenizer.texts_to_sequences(texts)
    X = pad_sequences(sequences, maxlen=MAX_LEN, padding="post", truncating="post")
    y = np.array(labels)

    job_manager.update("train", sid, progress=20, phase="LSTM")

    # Model 1: LSTM
    m1 = Sequential([
        Embedding(MAX_WORDS, 128, input_length=MAX_LEN),
        LSTM(64, dropout=0.2, recurrent_dropout=0.2),
        Dense(32, activation="relu"), Dropout(0.5), Dense(1, activation="sigmoid"),
    ])
    m1.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
    m1.fit(X, y, epochs=5, batch_size=32, verbose=0)
    s1 = m1.evaluate(X, y, verbose=0)[1]

    job_manager.update("train", sid, progress=40, phase="CNN")

    # Model 2: CNN
    m2 = Sequential([
        Embedding(MAX_WORDS, 128, input_length=MAX_LEN),
        Conv1D(64, 5, activation="relu"), GlobalMaxPooling1D(),
        Dense(32, activation="relu"), Dropout(0.5), Dense(1, activation="sigmoid"),
    ])
    m2.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
    m2.fit(X, y, epochs=5, batch_size=32, verbose=0)
    s2 = m2.evaluate(X, y, verbose=0)[1]

    job_manager.update("train", sid, progress=60, phase="GRU")

    # Model 3: GRU
    m3 = Sequential([
        Embedding(MAX_WORDS, 128, input_length=MAX_LEN),
        GRU(64, dropout=0.2, recurrent_dropout=0.2),
        Dense(32, activation="relu"), Dropout(0.5), Dense(1, activation="sigmoid"),
    ])
    m3.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])
    m3.fit(X, y, epochs=5, batch_size=32, verbose=0)
    s3_score = m3.evaluate(X, y, verbose=0)[1]

    job_manager.update("train", sid, progress=80, phase="classifying")

    all_data = load_data(f"preprocessed/{sid}/")
    if all_data:
        all_texts = [f"{d.get('title', '')} {d.get('desc', '')}" for d in all_data]
        all_seq = tokenizer.texts_to_sequences(all_texts)
        X_all = pad_sequences(all_seq, maxlen=MAX_LEN, padding="post", truncating="post")

        p1 = m1.predict(X_all, verbose=0).flatten()
        p2 = m2.predict(X_all, verbose=0).flatten()
        p3 = m3.predict(X_all, verbose=0).flatten()
        ensemble = (p1 + p2 + p3) / 3

        relevant, irrelevant = [], []
        for i, item in enumerate(all_data):
            if ensemble[i] >= 0.5:
                item["relevance_score"] = float(ensemble[i])
                relevant.append(item)
            else:
                irrelevant.append(item)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_jsonl(f"classified/{sid}/relevant_{ts}.jsonl", relevant)
        save_jsonl(f"classified/{sid}/irrelevant_{ts}.jsonl", irrelevant)

        job_manager.set("train", sid, {
            "status": "done", "progress": 100, "phase": "complete",
            "total": len(all_data), "relevant": len(relevant), "irrelevant": len(irrelevant),
            "scores": {"LSTM": round(s1, 3), "CNN": round(s2, 3), "GRU": round(s3_score, 3)},
            "models": ["LSTM", "CNN", "GRU"],
        })
    else:
        job_manager.set("train", sid, {"status": "error", "error": "No preprocessed data"})


def _train_sklearn(sid: str, texts: list[str], labels: list[int]) -> None:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score

    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    X = vec.fit_transform(texts)
    y = np.array(labels)

    job_manager.update("train", sid, progress=20, phase="LogisticRegression")

    m1 = LogisticRegression(max_iter=500, C=1.0)
    s1 = cross_val_score(m1, X, y, cv=min(3, len(y)), scoring="accuracy").mean()
    m1.fit(X, y)

    job_manager.update("train", sid, progress=40, phase="RandomForest")

    m2 = RandomForestClassifier(n_estimators=100, random_state=42)
    s2 = cross_val_score(m2, X, y, cv=min(3, len(y)), scoring="accuracy").mean()
    m2.fit(X, y)

    job_manager.update("train", sid, progress=60, phase="GradientBoosting")

    m3 = GradientBoostingClassifier(n_estimators=100, random_state=42)
    s3_score = cross_val_score(m3, X, y, cv=min(3, len(y)), scoring="accuracy").mean()
    m3.fit(X, y)

    job_manager.update("train", sid, progress=80, phase="classifying")

    all_data = load_data(f"preprocessed/{sid}/")
    if all_data:
        all_texts = [f"{d.get('title', '')} {d.get('desc', '')}" for d in all_data]
        X_all = vec.transform(all_texts)
        p1 = m1.predict_proba(X_all)[:, 1]
        p2 = m2.predict_proba(X_all)[:, 1]
        p3 = m3.predict_proba(X_all)[:, 1]
        ensemble = (p1 + p2 + p3) / 3

        relevant, irrelevant = [], []
        for i, item in enumerate(all_data):
            if ensemble[i] >= 0.5:
                item["relevance_score"] = float(ensemble[i])
                relevant.append(item)
            else:
                irrelevant.append(item)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_jsonl(f"classified/{sid}/relevant_{ts}.jsonl", relevant)
        save_jsonl(f"classified/{sid}/irrelevant_{ts}.jsonl", irrelevant)

        job_manager.set("train", sid, {
            "status": "done", "progress": 100, "phase": "complete (sklearn fallback)",
            "total": len(all_data), "relevant": len(relevant), "irrelevant": len(irrelevant),
            "scores": {"LR": round(s1, 3), "RF": round(s2, 3), "GB": round(s3_score, 3)},
            "models": ["LogisticRegression", "RandomForest", "GradientBoosting"],
        })
    else:
        job_manager.set("train", sid, {"status": "error", "error": "No preprocessed data"})
