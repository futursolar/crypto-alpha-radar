"""本地去重存储（JSON）。避免重复推送同一条信号。"""
from __future__ import annotations

import json
import os
from pathlib import Path

STORE_PATH = Path(os.getenv("STORE_PATH", "data/seen.json"))


def load() -> dict:
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save(store: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def is_new(store: dict, chain: str, address: str) -> bool:
    return f"{chain}:{address}" not in store


def mark(store: dict, chain: str, address: str, score: float) -> None:
    store[f"{chain}:{address}"] = {"score": score}
