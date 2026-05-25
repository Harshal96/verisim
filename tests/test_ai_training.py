from __future__ import annotations

import pytest

from verisim import CompanyRecord, ProductRecord, Verisim
from verisim.ai import (
    AITrainingContext,
    ChatDatasetSpec,
    ChatMessage,
    ChatTranscript,
    ClassificationDatasetSpec,
    ClassificationExample,
    InstructionDataset,
    InstructionDatasetSpec,
    InstructionResponsePair,
    NerDatasetSpec,
    NerEntity,
    NerSequence,
    chat_dataset,
    classification_dataset,
    instruction_dataset,
    iter_chat_transcripts,
    iter_classification_examples,
    iter_instruction_pairs,
    iter_ner_sequences,
)
from verisim.models import PersonRecord, SupportTicketRecord


def test_instruction_pairs_are_seeded_from_existing_company_and_product_context():
    verisim = Verisim(locale="en_US", seed=401)
    company = verisim.generate(CompanyRecord, context={"size_band": "startup"})
    product = verisim.generate(ProductRecord, context={"company": company})

    dataset = instruction_dataset(
        verisim,
        InstructionDatasetSpec(count=2),
        context={"company": company, "product_record": product},
    )

    assert isinstance(dataset, InstructionDataset)
    assert len(dataset.examples) == 2
    assert all(
        isinstance(example, InstructionResponsePair) for example in dataset.examples
    )
    assert all(company.name in example.instruction for example in dataset.examples)
    assert all(product.name in example.response for example in dataset.examples)


def test_ai_adapter_can_override_instruction_pair_generation():
    class FixedAdapter:
        def instruction_response(
            self, context: AITrainingContext
        ) -> InstructionResponsePair:
            return InstructionResponsePair(
                instruction=f"Summarize {context.company.name}.",
                response="custom adapter response",
            )

    pairs = list(
        iter_instruction_pairs(
            Verisim(locale="en_US", seed=402),
            InstructionDatasetSpec(count=1),
            adapter=FixedAdapter(),
        )
    )

    assert len(pairs) == 1
    assert pairs[0].instruction.startswith("Summarize ")
    assert pairs[0].response == "custom adapter response"


def test_classification_examples_follow_weighted_distribution_and_label_noise():
    examples = list(
        iter_classification_examples(
            Verisim(locale="en_US", seed=403),
            ClassificationDatasetSpec(
                count=10,
                labels={"positive": 7, "critical": 3},
                label_noise=0.0,
            ),
        )
    )

    assert [example.label for example in examples].count("positive") == 7
    assert [example.label for example in examples].count("critical") == 3
    assert all(isinstance(example, ClassificationExample) for example in examples)
    assert all(example.label in example.text for example in examples)

    noisy = classification_dataset(
        Verisim(locale="en_US", seed=404),
        ClassificationDatasetSpec(
            count=4,
            labels={"positive": 1, "critical": 1},
            label_noise=1.0,
        ),
    )

    assert all(example.label not in example.text for example in noisy.examples)


def test_classification_label_noise_requires_at_least_two_labels():
    with pytest.raises(ValueError, match="label_noise requires at least two labels"):
        list(
            iter_classification_examples(
                Verisim(locale="en_US", seed=405),
                ClassificationDatasetSpec(
                    count=1,
                    labels={"positive": 1},
                    label_noise=0.5,
                ),
            )
        )


def test_ner_sequences_emit_exact_character_spans():
    sequence = next(
        iter_ner_sequences(
            Verisim(locale="en_US", seed=406),
            NerDatasetSpec(count=1),
        )
    )

    assert isinstance(sequence, NerSequence)
    assert {entity.label for entity in sequence.entities} == {
        "PERSON",
        "ORG",
        "LOC",
        "DATE",
    }
    for entity in sequence.entities:
        assert sequence.text[entity.start : entity.end] == entity.text


def test_chat_transcripts_use_model_roles_and_display_speakers():
    transcript = next(
        iter_chat_transcripts(
            Verisim(locale="en_US", seed=407),
            ChatDatasetSpec(count=1, min_turns=2, max_turns=2),
        )
    )

    assert isinstance(transcript, ChatTranscript)
    assert len(transcript.messages) == 4
    assert [message.role for message in transcript.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [message.speaker for message in transcript.messages] == [
        "customer",
        "support_agent",
        "customer",
        "support_agent",
    ]


def test_generators_accept_existing_context_records_and_count_overrides():
    verisim = Verisim(locale="en_US", seed=408)
    company = verisim.generate(CompanyRecord, context={"size_band": "SMB"})
    company_context = company.as_company()
    person = verisim.generate(PersonRecord, context={"company": company})
    product = verisim.generate(ProductRecord, context={"company": company})
    ticket = verisim.generate(
        SupportTicketRecord,
        context={"company": company, "person_record": person},
    )

    instructions = instruction_dataset(
        verisim,
        InstructionDatasetSpec(count=5),
        count=1,
        context=company_context,
    )
    classifications = classification_dataset(
        verisim,
        ClassificationDatasetSpec(count=5),
        count=1,
        labels={"positive": 1, "critical": 1},
        label_noise=0.0,
        context={"person_record": person},
    )
    ner_sequences = list(
        iter_ner_sequences(
            verisim,
            NerDatasetSpec(count=5),
            count=1,
            context=product,
        )
    )
    chat = chat_dataset(
        verisim,
        ChatDatasetSpec(count=5),
        count=1,
        min_turns=1,
        max_turns=1,
        context=ticket,
    )

    assert len(instructions.examples) == 1
    assert len(classifications.examples) == 1
    assert len(ner_sequences) == 1
    assert len(chat.transcripts) == 1
    assert company_context.name in instructions.examples[0].instruction
    assert product.name in ner_sequences[0].text
    assert person.person.name in classifications.examples[0].text
    assert len(chat.transcripts[0].messages) == 2


def test_ai_training_model_validators_reject_invalid_specs_and_spans():
    with pytest.raises(ValueError, match="entity end must be greater than start"):
        NerEntity(start=2, end=2, label="PERSON", text="Al")

    with pytest.raises(ValueError, match="entity span length must match entity text"):
        NerEntity(start=0, end=2, label="PERSON", text="A")

    with pytest.raises(ValueError, match="entity text must match sequence span"):
        NerSequence(
            text="Alice works here.",
            entities=[NerEntity(start=0, end=3, label="PERSON", text="Bob")],
        )

    with pytest.raises(ValueError, match="chat speaker must match role"):
        ChatMessage(role="user", speaker="support_agent", content="Help")

    with pytest.raises(ValueError, match="labels must not be empty"):
        ClassificationDatasetSpec(labels={})

    with pytest.raises(ValueError, match="labels must not contain blank names"):
        ClassificationDatasetSpec(labels={" ": 1})

    with pytest.raises(ValueError, match="label weights must be positive"):
        ClassificationDatasetSpec(labels={"positive": 0})

    with pytest.raises(
        ValueError,
        match="max_turns must be greater than or equal to min_turns",
    ):
        ChatDatasetSpec(min_turns=3, max_turns=2)
