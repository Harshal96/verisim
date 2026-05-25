from __future__ import annotations

from verisim import Verisim
from verisim.ai import (
    ChatDataset,
    ClassificationDataset,
    InstructionDataset,
    NerDataset,
    chat_dataset,
    classification_dataset,
    instruction_dataset,
    ner_dataset,
)

AITrainingDatasets = dict[
    str, InstructionDataset | ClassificationDataset | NerDataset | ChatDataset
]


def generate_example(seed: int = 123, count: int = 2) -> AITrainingDatasets:
    """Generate all offline AI-training dataset shapes."""
    verisim = Verisim(locale="en_US", output_language="en", seed=seed)
    return {
        "instructions": instruction_dataset(verisim, count=count),
        "classification": classification_dataset(verisim, count=count),
        "ner": ner_dataset(verisim, count=count),
        "chat": chat_dataset(verisim, count=count),
    }


def main() -> None:
    datasets = generate_example()
    for name, dataset in datasets.items():
        print(f"## {name}")
        print(dataset.model_dump_json(indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
