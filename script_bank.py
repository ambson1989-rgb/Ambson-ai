"""Fact-checked scripts. pick_script advances every run and skips already-used topics."""
import json
import os
import re
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


def _normalize(topic: str) -> str:
    t = re.sub(r"\s+", " ", (topic or "").lower().strip())
    return re.sub(r"[^a-z0-9\s]", "", t)[:100]


def pick_script() -> dict:
    """Next bank script that is not in used_topics."""
    state = _load_state()
    scripts = _load_scripts()
    n = len(scripts)
    last_index = int(state.get("last_index", -1))
    used = {_normalize(x) for x in (state.get("used_topics") or []) if x}

    chosen = None
    for step in range(n):
        idx = (last_index + 1 + step) % n
        topic = scripts[idx]["topic"]
        norm = _normalize(topic)
        if norm not in used and not any(norm in u or u in norm for u in used if len(u) > 15):
            chosen = idx
            break

    if chosen is None:
        # All bank scripts used at least once — pick next index anyway
        chosen = (last_index + 1) % n
        log_msg = scripts[chosen]["topic"]
        print(f"WARNING: all bank scripts already used; recycling: {log_msg}")

    topic = scripts[chosen]["topic"]
    used_list = list(state.get("used_topics") or [])
    used_list.append(topic)
    used_list = used_list[-500:]

    _save_state({
        "last_index": chosen,
        "last_run_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "used_topics": used_list,
    })
    return scripts[chosen]
