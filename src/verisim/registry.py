from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from uuid import UUID, uuid5, NAMESPACE_URL


class UniquenessRegistry:
    def __init__(self, namespace: str = "verisim") -> None:
        self.namespace = namespace
        self._values: dict[str, set[str]] = defaultdict(set)
        self._counters: dict[str, int] = defaultdict(int)

    def reserve(self, key: str, value: object) -> None:
        self._values[key].add(str(value))

    def contains(self, key: str, value: object) -> bool:
        return str(value) in self._values[key]

    def unique(self, key: str, factory: Callable[[int], object], max_attempts: int = 50_000) -> object:
        for attempt in range(max_attempts):
            value = factory(attempt)
            serialized = str(value)
            if serialized not in self._values[key]:
                self._values[key].add(serialized)
                return value
        raise RuntimeError(f"could not generate unique value for {key}")

    def next_index(self, key: str) -> int:
        value = self._counters[key]
        self._counters[key] += 1
        return value

    def uuid(self, key: str) -> UUID:
        index = self.next_index(f"uuid:{key}")
        value = uuid5(NAMESPACE_URL, f"{self.namespace}:{key}:{index}")
        self.reserve(f"uuid:{key}", value)
        return value
