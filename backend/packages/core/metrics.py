"""M42 monitoring: CloudWatch Embedded Metric Format (EMF) lines plus in-process counters.

On Lambda, stdout lines in EMF are turned into CloudWatch metrics with no extra API calls.
Locally the same lines are just structured logs, and ``snapshot()`` backs ``GET /admin/metrics``.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections import defaultdict
from typing import Any

__all__ = ["emit", "reset", "snapshot"]

NAMESPACE = "CoolRoof"
_lock = threading.Lock()
_counts: dict[str, float] = defaultdict(float)
_sums: dict[str, float] = defaultdict(float)
_n: dict[str, int] = defaultdict(int)


def emit(name: str, value: float = 1.0, unit: str = "Count", **dimensions: str) -> None:
    """Record one metric data point (and print its EMF line)."""
    key = name + "".join(f"|{k}={v}" for k, v in sorted(dimensions.items()))
    with _lock:
        _counts[key] += value
        _sums[key] += value
        _n[key] += 1
    line: dict[str, Any] = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": [list(dimensions)] if dimensions else [[]],
                    "Metrics": [{"Name": name, "Unit": unit}],
                }
            ],
        },
        name: value,
        **dimensions,
    }
    sys.stdout.write(json.dumps(line) + "\n")


def snapshot() -> dict[str, dict[str, float]]:
    with _lock:
        return {
            k: {"count": _n[k], "sum": round(_sums[k], 3), "mean": round(_sums[k] / _n[k], 3)}
            for k in sorted(_n)
        }


def reset() -> None:
    with _lock:
        _counts.clear()
        _sums.clear()
        _n.clear()
