"""Bledy warstwy aplikacyjnej — stabilny kontrakt dla CLI, MCP i agentow.

Kazdy blad ma kod (nie zmienia znaczenia miedzy wersjami), podpowiedz naprawy
i informacje, czy ponowienie ma sens. Kod wyjscia CLI wynika z klasy bledu.
"""

from __future__ import annotations

from typing import Any


class ExitCode:
    OK = 0
    DOMAIN = 1  # walidacja, brak obiektu, konflikt stanu
    USAGE = 2  # zle argumenty (zwraca parser)
    CONFIG = 3  # brak konfiguracji w .env
    CONFIRMATION = 4  # czynnosc nieodwracalna czeka na potwierdzenie
    EXTERNAL = 5  # blad uslugi zewnetrznej (KSeF, bramka MF, SMTP, Google)


class AppError(Exception):
    code = "ERROR"
    exit_code = ExitCode.DOMAIN
    retryable = False

    def __init__(
        self, message: str, *, hint: str | None = None, details: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "retryable": self.retryable,
            "details": self.details,
        }


class NotFoundError(AppError):
    code = "NOT_FOUND"


class ConflictError(AppError):
    """Stan nie pozwala na czynnosc (np. faktura juz wyslana, deklaracja juz zlozona)."""

    code = "CONFLICT"


class InvalidInputError(AppError):
    code = "INVALID_INPUT"


class ConfigMissingError(AppError):
    code = "CONFIG_MISSING"
    exit_code = ExitCode.CONFIG


class ExternalServiceError(AppError):
    code = "EXTERNAL_SERVICE"
    exit_code = ExitCode.EXTERNAL
    retryable = True


class ConfirmationRequiredError(AppError):
    """Czynnosc nieodwracalna: zwracamy podsumowanie i token do potwierdzenia."""

    code = "CONFIRMATION_REQUIRED"
    exit_code = ExitCode.CONFIRMATION

    def __init__(self, *, action: str, token: str, summary: dict[str, Any], stale: bool = False):
        reason = "Token potwierdzenia nieaktualny. " if stale else ""
        super().__init__(
            f"{reason}Czynnosc '{action}' wymaga potwierdzenia przez czlowieka.",
            hint=f"Pokaz podsumowanie uzytkownikowi; po akceptacji powtorz z --confirm {token}",
            details={"action": action, "token": token, "summary": summary},
        )
        self.action = action
        self.token = token
        self.summary = summary
