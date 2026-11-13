"""Dwufazowe potwierdzanie czynnosci nieodwracalnych (KSeF, bramka MF, e-mail).

Faza 1 (bez tokena): przypadek uzycia liczy podsumowanie i token, nic nie wysyla.
Faza 2 (`--confirm <token>`): token musi sie zgadzac z ponownie policzonym.

Token wiaze: rodzaj czynnosci, cel (np. numer faktury), skrot wysylanej tresci,
srodowisko (test/prod) i date. Zmiana pliku, srodowiska albo nowy dzien —
token przestaje pasowac i trzeba ponownie pokazac podsumowanie czlowiekowi.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from jdg_ksiegowy.app.audit import audit
from jdg_ksiegowy.app.errors import ConfirmationRequiredError


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def confirmation_token(
    action: str, target: str, payload_digest: str, env: str, today: date | None = None
) -> str:
    day = (today or date.today()).isoformat()
    raw = f"{action}|{target}|{payload_digest}|{env}|{day}".encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def require_confirmation(
    *,
    action: str,
    target: str,
    payload_digest: str,
    env: str,
    summary: dict[str, Any],
    confirm: str | None,
) -> None:
    """Przepusc tylko z poprawnym tokenem; inaczej rzuc ConfirmationRequiredError."""
    token = confirmation_token(action, target, payload_digest, env)
    if confirm == token:
        return
    stale = confirm is not None
    audit(action, target, "refused" if stale else "pending", {"env": env, **summary})
    raise ConfirmationRequiredError(
        action=action, token=token, summary={"env": env, **summary}, stale=stale
    )
