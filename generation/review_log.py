"""Append-only human review events. Logging must succeed before UI state changes."""
import json
import os
from pathlib import Path
from threading import Lock

from generation.semantic_review import review_event

_LOCK = Lock()


def review_log_path(base_dir):
    return Path(base_dir) / "Generated" / "semantic_review" / "semantic_reviews.jsonl"


def append_review_event(path, event):
    # Serialize before opening, so invalid data cannot truncate or add a partial row.
    line = json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
    path = Path(path)
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())


def record_review(path, snapshot, current_review, execution_status, state,
                  reason=None, note=None):
    review, event = review_event(snapshot, current_review, execution_status,
                                 state, reason, note)
    append_review_event(path, event)
    return review, event