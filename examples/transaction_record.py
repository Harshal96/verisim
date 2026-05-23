from __future__ import annotations

from verisim import TransactionRecord, Verisim


def generate_example(seed: int = 123) -> TransactionRecord:
    verisim = Verisim(locale="en_US", seed=seed)
    return verisim.generate(TransactionRecord)
