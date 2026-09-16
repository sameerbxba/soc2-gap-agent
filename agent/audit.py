"""Append-only audit log.

Control AC-4 in the assessment. Every tool call the agent makes, every argument
it passed, every guardrail decision and every human approval is written here
before the result is returned to the model. The log is the answer to the
question an auditor actually asks about an agent, which is not "what did it
say" but "what did it do".

The file is opened in append mode on every write and never rewritten, so a run
that crashes still leaves a complete record up to the point of failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path


def new_run_id() -> str:
    return f"run-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"


def digest(value) -> str:
    """Short stable hash of a tool result.

    The log records what came back without storing the whole document inside
    it, so the log stays readable and still detects a changed source file.
    """
    blob = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


class AuditLog:
    def __init__(self, path: str | Path, run_id: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.entries = 0

    def write(self, event: str, **fields) -> dict:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "run_id": self.run_id,
            "seq": self.entries,
            "event": event,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self.entries += 1
        return record

    def read_run(self, run_id: str | None = None) -> list[dict]:
        run_id = run_id or self.run_id
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("run_id") == run_id:
                out.append(rec)
        return out
