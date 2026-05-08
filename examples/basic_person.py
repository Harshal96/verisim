from __future__ import annotations

from verisim import PersonRecord, Verisim


def generate_example(seed: int = 123) -> PersonRecord:
    """Generate one coherent synthetic person record."""
    verisim = Verisim(locale="en_US", output_language="en", seed=seed)
    return verisim.generate(PersonRecord)


def main() -> None:
    record = generate_example()
    print(record.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
