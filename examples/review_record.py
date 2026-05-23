from __future__ import annotations

from verisim import ReviewRecord, Verisim


def generate_example(seed: int = 123) -> ReviewRecord:
    verisim = Verisim(locale="en_US", seed=seed)
    return verisim.generate(ReviewRecord)
