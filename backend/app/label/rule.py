"""Deterministic evidence grades and probabilities under independent tags."""

from typing import Literal


SEM = ("sense", "feel", "think", "act", "relate", "outcome")
GRADE_FIELDS = ("anchor",) + SEM + ("situation",)
RULE_VERSION = "r1"


def grade(tags: dict) -> Literal["core", "supporting", "non"]:
    """Grade a complete set of binary tags using rule r1."""
    if not tags["anchor"]:
        return "non"
    sem_count = sum(tags[field] for field in SEM)
    if sem_count >= 2 and tags["situation"]:
        return "core"
    if sem_count >= 1:
        return "supporting"
    return "non"


def grade_probs(p: dict[str, float]) -> dict[str, float]:
    """Compute grade probabilities from complete, independent tag probabilities."""
    # distribution[k] is the probability of exactly k positive semantic tags.
    distribution = [1.0]
    for field in SEM:
        probability = p[field]
        updated = [0.0] * (len(distribution) + 1)
        for count, mass in enumerate(distribution):
            updated[count] += mass * (1.0 - probability)
            updated[count + 1] += mass * probability
        distribution = updated

    at_least_one = sum(distribution[1:])
    at_least_two = sum(distribution[2:])
    core = p["anchor"] * at_least_two * p["situation"]
    supporting = p["anchor"] * (at_least_one - at_least_two * p["situation"])
    return {"core": core, "supporting": supporting, "non": 1.0 - core - supporting}
