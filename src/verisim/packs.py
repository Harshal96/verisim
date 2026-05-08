from __future__ import annotations

from verisim.data import LiteDataPack


class DataPackManager:
    """Versioned data-pack lookup surface for lite/full package growth."""

    def __init__(self) -> None:
        self._packs = {"lite": LiteDataPack}

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._packs))

    def load(self, name: str = "lite") -> LiteDataPack:
        try:
            pack_type = self._packs[name]
        except KeyError as exc:
            raise ValueError(f"unknown data pack {name!r}") from exc
        return pack_type()
