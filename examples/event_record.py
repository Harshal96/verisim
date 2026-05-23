from __future__ import annotations

from verisim import EventRecord, Verisim


def generate_example(seed: int = 123) -> EventRecord:
    verisim = Verisim(locale="en_US", seed=seed)
    return verisim.generate(EventRecord)
