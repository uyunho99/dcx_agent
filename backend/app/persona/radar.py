"""Absolute-cosine radar values and midrank percentiles (0–100).

The standalone radar compares its weighted mean with its member Contexts.
Insight generation replaces those percentiles with ranks among session insights.
Zero vectors have similarity zero; missing/invalid vectors and weights fail.
"""
import inspect

import numpy as np

from app.persona.params import RADAR_AXES


def embed_axes(embedder) -> np.ndarray:
    embed = embedder.embed
    parameters = inspect.signature(embed).parameters
    supports_query = ('input_type' in parameters and
                      parameters['input_type'].kind != inspect.Parameter.POSITIONAL_ONLY)
    supports_query |= any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values())
    kwargs = {'input_type': 'query'} if supports_query else {}
    return np.asarray(embed(list(RADAR_AXES.values()), **kwargs), dtype=float)


def session_percentiles(values) -> list[float]:
    """Mid-distribution rank: 100 * (count below + half count equal) / N."""
    values = np.asarray(values, dtype=float)
    return [float(100 * (np.sum(values < v) + .5 * np.sum(values == v)) / len(values))
            for v in values]


def radar(context_centroids: dict[str, np.ndarray], weights: dict[str, int],
          axes_vecs: np.ndarray) -> dict:
    ids = list(context_centroids)
    vectors = np.asarray([context_centroids[cid] for cid in ids], dtype=float)
    axes = np.asarray(axes_vecs, dtype=float)
    counts = np.asarray([weights[cid] for cid in ids], dtype=float)
    if (not ids or vectors.ndim != 2 or axes.ndim != 2 or
            axes.shape != (len(RADAR_AXES), vectors.shape[1]) or
            not np.isfinite(vectors).all() or not np.isfinite(axes).all() or
            not np.isfinite(counts).all() or np.any(counts < 0) or counts.sum() <= 0):
        raise ValueError('Invalid radar vectors or document counts')
    denominator = np.linalg.norm(vectors, axis=1)[:, None] * np.linalg.norm(axes, axis=1)[None, :]
    similarities = np.divide(np.abs(vectors @ axes.T), denominator,
                             out=np.zeros_like(denominator), where=denominator != 0)
    similarities = np.clip(similarities, 0, 1)
    mean = np.average(similarities, axis=0, weights=counts)
    percentile = [float(100 * (np.sum(column < value) + .5 * np.sum(column == value)) / len(ids))
                  for column, value in zip(similarities.T, mean)]
    return {'raw': dict(zip(RADAR_AXES, mean.tolist())),
            'percentile': dict(zip(RADAR_AXES, percentile))}
