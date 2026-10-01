"""Fact-checked scripts. pick_script advances on EVERY run (manual or scheduled)."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")
_DIR = Path(__file__).resolve().parent


def _load_scripts():
    scripts = []
    for path in sorted(_DIR.glob("script_*.json")):
        with open(path, encoding="utf-8") as f:
            scripts.append(json.load(f))
    if not scripts:
        raise RuntimeError("No script_*.json files found")
    return scripts


SCRIPTS = _load_scripts()


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_index": -1, "last_run_date": None, "post_count": 0, "used_topics": []}


def _save_state(state: dict) -> None:
    existing = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                existing = json.load(f) or {}
        except (json.JSONDecodeError, OSError):
            existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing.update(state)
    with open(STATE_FILE, "w") as f:
        json.dump(existing, f, indent=2)


def pick_script() -> dict:
    """Advance to the next script on EVERY call. Never repeats the same topic until the pool cycles."""
    state = _load_state()
    scripts = _load_scripts()
    n = len(scripts)
    last_index = int(state.get("last_index", -1))
    next_index = (last_index + 1) % n

    used = list(state.get("used_topics") or [])
    recent = set(used[-(max(n - 1, 1)):])
    chosen = next_index
    for step in range(n):
        idx = (next_index + step) % n
        topic = scripts[idx]["topic"]
        if topic not in recent or step == n - 1:
            chosen = idx
            break

    topic = scripts[chosen]["topic"]
    used.append(topic)
    used = used[-(n * 2):]

    _save_state({
        "last_index": chosen,
        "last_run_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "used_topics": used,
    })
    return scripts[chosen]
