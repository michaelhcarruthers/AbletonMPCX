"""Threshold engine — alert when spectrum or meter values cross defined thresholds."""

from __future__ import annotations

_thresholds: dict[str, dict] = {}


def set_threshold(
    key: str,
    min_val: float | None = None,
    max_val: float | None = None,
    callback_label: str | None = None,
):
    """Register a threshold for a named metric.

    Args:
        key: Unique identifier for this metric (e.g. ``"track_0_level"``).
        min_val: Lower bound; a violation is raised when the metric falls below this.
        max_val: Upper bound; a violation is raised when the metric exceeds this.
        callback_label: Optional human-readable label included in violation messages.
    """
    _thresholds[key] = {
        "min_val": min_val,
        "max_val": max_val,
        "callback_label": callback_label,
    }


def check_thresholds(metrics: dict) -> list:
    """Check a dict of metric values against registered thresholds.

    Args:
        metrics: Mapping of ``{key: numeric_value}`` to evaluate.

    Returns:
        List of violation dicts, each containing:
            key, value, threshold_type ("min" or "max"),
            threshold_value, message
    """
    violations: list[dict] = []
    for key, value in metrics.items():
        spec = _thresholds.get(key)
        if spec is None:
            continue
        label = spec.get("callback_label") or key
        min_val = spec.get("min_val")
        max_val = spec.get("max_val")
        if min_val is not None and value < min_val:
            violations.append({
                "key": key,
                "value": value,
                "threshold_type": "min",
                "threshold_value": min_val,
                "message": "{} is {:.2f}, below minimum {:.2f}".format(label, value, min_val),
            })
        if max_val is not None and value > max_val:
            violations.append({
                "key": key,
                "value": value,
                "threshold_type": "max",
                "threshold_value": max_val,
                "message": "{} is {:.2f}, above maximum {:.2f}".format(label, value, max_val),
            })
    return violations


def clear_threshold(key: str | None = None):
    """Remove the threshold for *key*, or all thresholds if *key* is ``None``."""
    if key is None:
        _thresholds.clear()
    else:
        _thresholds.pop(key, None)
