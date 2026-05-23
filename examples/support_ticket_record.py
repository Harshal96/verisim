from __future__ import annotations

from verisim import SupportTicketRecord, Verisim


def generate_example(seed: int = 123) -> SupportTicketRecord:
    verisim = Verisim(locale="en_US", seed=seed)
    return verisim.generate(SupportTicketRecord)
