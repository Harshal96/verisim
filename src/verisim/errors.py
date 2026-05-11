from __future__ import annotations

from collections.abc import Sequence


class VerisimError(Exception):
    """Base error for Verisim."""


class UnsupportedModelError(VerisimError):
    """Raised when no provider graph can generate the requested model."""


class ContextConflictError(VerisimError):
    """Raised when supplied context contradicts generated-model invariants."""

    def __init__(self, conflicts: Sequence[object]) -> None:
        self.conflicts = list(conflicts)
        message = "; ".join(
            self._safe_conflict_label(conflict) for conflict in conflicts
        )
        super().__init__(message or "context contains conflicting facts")

    @staticmethod
    def _safe_conflict_label(conflict: object) -> str:
        code = getattr(conflict, "code", None)
        path = getattr(conflict, "path", None)
        if code and path:
            return f"{code} at {path}"
        if code:
            return str(code)
        if path:
            return str(path)
        return conflict.__class__.__name__
