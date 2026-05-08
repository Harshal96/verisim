from __future__ import annotations

from verisim import Dataset, DatasetSpec, Verisim


def generate_example(seed: int = 123, people: int = 12, companies: int = 3) -> Dataset:
    """Generate a small related dataset with people assigned to companies."""
    verisim = Verisim(locale="en_US", output_language="en", seed=seed)
    return verisim.dataset(DatasetSpec(people=people, companies=companies))


def main() -> None:
    dataset = generate_example()
    print(dataset.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
