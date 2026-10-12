"""Collect due analytics snapshots now (manual run of the 15-minute sweep).

Usage (repo root):
    python scripts/collect_metrics.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.scheduler import collect_due_metrics_job  # noqa: E402

if __name__ == "__main__":
    print(f"collected {collect_due_metrics_job()} snapshot(s)")
