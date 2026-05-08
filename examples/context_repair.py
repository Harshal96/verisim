from __future__ import annotations

from verisim import Address, Contact, GenerationDiagnostics, PersonRecord, Verisim


def generate_example(seed: int = 123) -> tuple[GenerationDiagnostics, PersonRecord]:
    """Explain and repair context where a US address is paired with an Indian phone."""
    verisim = Verisim(locale="en_US", output_language="en", seed=seed)
    address = Address(
        line1="19 Birch Street",
        city="Austin",
        region="Texas",
        region_code="TX",
        postal_code="78701",
        country="United States",
        country_code="US",
    )
    contact = Contact.synthetic(
        email="rakesh.patel@example.invalid", phone="+91 98765 43210"
    )
    context = {"address": address, "contact": contact}
    diagnostics = verisim.generate(PersonRecord, context=context, mode="explain")
    repaired = verisim.generate(PersonRecord, context=context, mode="repair")
    assert isinstance(diagnostics, GenerationDiagnostics)
    assert isinstance(repaired, PersonRecord)
    return diagnostics, repaired


def main() -> None:
    diagnostics, repaired = generate_example()
    print(diagnostics.model_dump_json(indent=2))
    print(repaired.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
