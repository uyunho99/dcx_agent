"""Ordered subcategory codes for the three keyword axes."""

AXES: dict[str, list[str]] = {
    "physical": ["time", "space", "social", "sense", "body", "product_physical"],
    "psychological": ["emotion", "goal_ladder", "perceived_risk", "belief", "identity"],
    "behavioral": ["trigger", "constraint", "coping", "info_search", "switching"],
}


def is_valid(axis: str, sub: str) -> bool:
    """Accept known codes or custom codes with a nonempty name on a known axis."""
    return axis in AXES and (
        sub in AXES[axis]
        or (sub.startswith("custom:") and bool(sub[len("custom:"):].strip()))
    )
