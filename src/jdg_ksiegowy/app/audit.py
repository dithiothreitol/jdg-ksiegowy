"""Dziennik audytu czynnosci zmieniajacych stan lub wysylajacych dane na zewnatrz.

Aktor (cli / mcp / cron) ustawia adapter wejsciowy przez `set_actor`. Szczegoly
sa zapisywane jako JSON — bez sekretow (tokenow, hasel, PESEL).
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select

from jdg_ksiegowy.registry.db import AuditRecord, get_session, init_db

Outcome = Literal["ok", "error", "refused", "pending"]

_actor: ContextVar[str] = ContextVar("jdg_actor", default="cli")


def set_actor(actor: str) -> None:
    _actor.set(actor)


def audit(action: str, target: str | None, outcome: Outcome, detail: dict[str, Any]) -> None:
    init_db()
    with get_session() as s:
        s.add(
            AuditRecord(
                ts=datetime.now(),
                actor=_actor.get(),
                action=action,
                target=target,
                outcome=outcome,
                detail=json.dumps(detail, ensure_ascii=False, default=str),
            )
        )
        s.commit()


def recent(limit: int = 50) -> list[AuditRecord]:
    init_db()
    with get_session() as s:
        return list(s.scalars(select(AuditRecord).order_by(AuditRecord.id.desc()).limit(limit)))
