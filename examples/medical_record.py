from __future__ import annotations

from verisim import MedicalRecord, Verisim


def generate_example(seed: int = 123) -> MedicalRecord:
    verisim = Verisim(locale="en_US", seed=seed)
    return verisim.generate(MedicalRecord)
