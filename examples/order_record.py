from __future__ import annotations

from verisim import OrderRecord, Verisim


def generate_example(seed: int = 123) -> OrderRecord:
    verisim = Verisim(locale="en_US", seed=seed)
    return verisim.generate(OrderRecord)
