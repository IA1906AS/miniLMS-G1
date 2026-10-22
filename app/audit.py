from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_AUDIT_LOG_PATH: str = "audit.log"


def configure_audit(log_path: str) -> None:
    global _AUDIT_LOG_PATH
    _AUDIT_LOG_PATH = log_path


def write_audit_log(
    *,
    actor_id: str | None,
    action: str,
    resource: str,
    result: str,
    old_score: float | None = None,
    new_score: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    entry: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "actorId": actor_id or "anonymous",
        "action": action,
        "resource": resource,
        "result": result,
    }
    if old_score is not None:
        entry["oldScore"] = old_score
    if new_score is not None:
        entry["newScore"] = new_score
    if extra:
        for k, v in extra.items():
            if k.lower() not in {
                "password",
                "password_hash",
                "passwordhash",
                "token",
                "accesstoken",
            }:
                entry[k] = v

    path = Path(_AUDIT_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    path = Path(_AUDIT_LOG_PATH)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    records = []
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records
