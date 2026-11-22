"""Turn logging (step 6): one record per caller turn, for the study.

Status: implemented. Off unless switched on (python -m assistant.chat summarise --log).
Each call goes to its own file in logs/ (ignored by git), one JSON record per line.
The records hold what the caller typed, so keep them only with the caller's consent.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def turn_record(chat, said: str, reply: str) -> dict:
    """What happened in the turn the conversation has just answered."""
    turn = chat.turn
    return {
        "call": chat.call_id,
        "turn": chat.turns,
        "seconds": round(time.monotonic() - chat.started, 1),
        "strategy": chat.strategy,
        "mishear": chat.mishear,
        "said": said,
        "reader": turn["reader"],      # "saved model answer", "live model" or "keyword reader"
        "read": turn["read"],          # the details the reader gave, before any planted error
        "misheard": turn["misheard"],  # [said, heard] when the planted-error switch changed the time
        "decided": action_record(turn["decided"]),
        "booking": booking_record(turn["booking"]),
        "reply": reply,
        "not_understood": chat.not_understood,
        "finished": chat.finished,
    }


def action_record(action) -> dict | None:
    """The policy's action, or None if the policy was not asked this turn."""
    if action is None:
        return None
    return {"kind": action.kind, "detail": action.detail, "slot": slot_name(action.slot),
            "options": [slot_name(slot) for slot in action.options]}


def booking_record(result) -> dict | None:
    """What the booking desk returned, or None if no booking was tried this turn."""
    if result is None:
        return None
    return {"status": result.status, "service": result.service, "day": result.day, "time": result.time,
            "repeat": result.repeat}


def slot_name(slot) -> str | None:
    return None if slot is None else f"{slot.day} {slot.time}"


class TurnFile:
    """Writes each record as one line of JSON straight away, so a call is kept even if the chat stops."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()  # so a call started in the same second gets another name

    def append(self, record: dict) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record) + "\n")


def new_log_path(strategy: str) -> Path:
    """A new file for each call, such as logs/2026-11-22-153000-summarise.jsonl (or ...-153000-2-summarise.jsonl)."""
    stamp = time.strftime("%Y-%m-%d-%H%M%S")
    path = LOG_DIR / f"{stamp}-{strategy}.jsonl"
    number = 1
    while path.exists():  # another call started in the same second
        number += 1
        path = LOG_DIR / f"{stamp}-{number}-{strategy}.jsonl"
    return path
