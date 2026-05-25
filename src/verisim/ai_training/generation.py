from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import floor

from verisim.ai_training.adapters import AIGenerationAdapter, OfflineAIGenerationAdapter
from verisim.ai_training.models import (
    AITrainingContext,
    ChatDataset,
    ChatDatasetSpec,
    ChatTranscript,
    ClassificationDataset,
    ClassificationDatasetSpec,
    ClassificationExample,
    InstructionDataset,
    InstructionDatasetSpec,
    InstructionResponsePair,
    NerDataset,
    NerDatasetSpec,
    NerSequence,
)
from verisim.api import Verisim
from verisim.models import (
    Company,
    CompanyRecord,
    PersonRecord,
    ProductRecord,
    SupportTicketRecord,
)

ContextInput = object | Mapping[str, object] | None


def iter_instruction_pairs(
    verisim: Verisim,
    spec: InstructionDatasetSpec | None = None,
    *,
    count: int | None = None,
    context: ContextInput = None,
    adapter: AIGenerationAdapter | None = None,
) -> Iterable[InstructionResponsePair]:
    active_spec = _instruction_spec(spec, count)
    active_adapter = adapter or OfflineAIGenerationAdapter()
    for _ in range(active_spec.count):
        yield active_adapter.instruction_response(_training_context(verisim, context))


def instruction_dataset(
    verisim: Verisim,
    spec: InstructionDatasetSpec | None = None,
    *,
    count: int | None = None,
    context: ContextInput = None,
    adapter: AIGenerationAdapter | None = None,
) -> InstructionDataset:
    return InstructionDataset(
        examples=list(
            iter_instruction_pairs(
                verisim,
                spec,
                count=count,
                context=context,
                adapter=adapter,
            )
        )
    )


def iter_classification_examples(
    verisim: Verisim,
    spec: ClassificationDatasetSpec | None = None,
    *,
    count: int | None = None,
    labels: Mapping[str, float] | None = None,
    label_noise: float | None = None,
    context: ContextInput = None,
    adapter: AIGenerationAdapter | None = None,
) -> Iterable[ClassificationExample]:
    active_spec = _classification_spec(spec, count, labels, label_noise)
    if active_spec.label_noise > 0 and len(active_spec.labels) < 2:
        raise ValueError("label_noise requires at least two labels")
    active_adapter = adapter or OfflineAIGenerationAdapter()
    label_names = list(active_spec.labels)
    for intended_label in _label_sequence(active_spec, verisim):
        ai_context = _training_context(verisim, context)
        text = active_adapter.classification_text(ai_context, intended_label)
        label = _noisy_label(verisim, label_names, intended_label, active_spec)
        yield ClassificationExample(text=text, label=label)


def classification_dataset(
    verisim: Verisim,
    spec: ClassificationDatasetSpec | None = None,
    *,
    count: int | None = None,
    labels: Mapping[str, float] | None = None,
    label_noise: float | None = None,
    context: ContextInput = None,
    adapter: AIGenerationAdapter | None = None,
) -> ClassificationDataset:
    return ClassificationDataset(
        examples=list(
            iter_classification_examples(
                verisim,
                spec,
                count=count,
                labels=labels,
                label_noise=label_noise,
                context=context,
                adapter=adapter,
            )
        )
    )


def iter_ner_sequences(
    verisim: Verisim,
    spec: NerDatasetSpec | None = None,
    *,
    count: int | None = None,
    context: ContextInput = None,
    adapter: AIGenerationAdapter | None = None,
) -> Iterable[NerSequence]:
    active_spec = _ner_spec(spec, count)
    active_adapter = adapter or OfflineAIGenerationAdapter()
    for _ in range(active_spec.count):
        yield active_adapter.ner_sequence(_training_context(verisim, context))


def ner_dataset(
    verisim: Verisim,
    spec: NerDatasetSpec | None = None,
    *,
    count: int | None = None,
    context: ContextInput = None,
    adapter: AIGenerationAdapter | None = None,
) -> NerDataset:
    return NerDataset(
        sequences=list(
            iter_ner_sequences(
                verisim,
                spec,
                count=count,
                context=context,
                adapter=adapter,
            )
        )
    )


def iter_chat_transcripts(
    verisim: Verisim,
    spec: ChatDatasetSpec | None = None,
    *,
    count: int | None = None,
    min_turns: int | None = None,
    max_turns: int | None = None,
    context: ContextInput = None,
    adapter: AIGenerationAdapter | None = None,
) -> Iterable[ChatTranscript]:
    active_spec = _chat_spec(spec, count, min_turns, max_turns)
    active_adapter = adapter or OfflineAIGenerationAdapter()
    for _ in range(active_spec.count):
        turns = verisim.random.randint(active_spec.min_turns, active_spec.max_turns)
        yield active_adapter.chat_transcript(_training_context(verisim, context), turns)


def chat_dataset(
    verisim: Verisim,
    spec: ChatDatasetSpec | None = None,
    *,
    count: int | None = None,
    min_turns: int | None = None,
    max_turns: int | None = None,
    context: ContextInput = None,
    adapter: AIGenerationAdapter | None = None,
) -> ChatDataset:
    return ChatDataset(
        transcripts=list(
            iter_chat_transcripts(
                verisim,
                spec,
                count=count,
                min_turns=min_turns,
                max_turns=max_turns,
                context=context,
                adapter=adapter,
            )
        )
    )


def _training_context(verisim: Verisim, context: ContextInput) -> AITrainingContext:
    facts = verisim._facts_from_context(context, target=object)  # noqa: SLF001
    company_record, company = _company_from_facts(facts)
    if company is None:
        company_record = verisim.generate(CompanyRecord, context=facts)
        company = company_record.as_company()

    seed_context: dict[str, object] = dict(facts)
    if company_record is not None:
        seed_context["company"] = company_record
        seed_context["company_record"] = company_record
    else:
        seed_context["company"] = company

    person = seed_context.get("person_record")
    if not isinstance(person, PersonRecord):
        person = verisim.generate(PersonRecord, context=seed_context, mode="repair")
        seed_context["person_record"] = person

    product = seed_context.get("product_record")
    if not isinstance(product, ProductRecord):
        product = verisim.generate(ProductRecord, context=seed_context)
        seed_context["product_record"] = product

    ticket = seed_context.get("support_ticket_record")
    if not isinstance(ticket, SupportTicketRecord):
        ticket = verisim.generate(SupportTicketRecord, context=seed_context)

    return AITrainingContext(
        person=person,
        company=company,
        product=product,
        ticket=ticket,
    )


def _company_from_facts(
    facts: Mapping[str, object],
) -> tuple[CompanyRecord | None, Company | None]:
    company_record = facts.get("company_record")
    if isinstance(company_record, CompanyRecord):
        return company_record, company_record.as_company()
    product = facts.get("product_record")
    if isinstance(product, ProductRecord):
        return None, product.company
    person = facts.get("person_record")
    if isinstance(person, PersonRecord):
        return None, person.company
    ticket = facts.get("support_ticket_record")
    if isinstance(ticket, SupportTicketRecord):
        return None, ticket.company
    company = facts.get("company")
    if isinstance(company, Company):
        return None, company
    return None, None


def _instruction_spec(
    spec: InstructionDatasetSpec | None, count: int | None
) -> InstructionDatasetSpec:
    if spec is None:
        return InstructionDatasetSpec(count=10 if count is None else count)
    if count is None:
        return spec
    return spec.model_copy(update={"count": count})


def _classification_spec(
    spec: ClassificationDatasetSpec | None,
    count: int | None,
    labels: Mapping[str, float] | None,
    label_noise: float | None,
) -> ClassificationDatasetSpec:
    updates: dict[str, object] = {}
    if count is not None:
        updates["count"] = count
    if labels is not None:
        updates["labels"] = dict(labels)
    if label_noise is not None:
        updates["label_noise"] = label_noise
    if spec is None:
        return ClassificationDatasetSpec(**updates)
    return spec.model_copy(update=updates) if updates else spec


def _ner_spec(spec: NerDatasetSpec | None, count: int | None) -> NerDatasetSpec:
    if spec is None:
        return NerDatasetSpec(count=10 if count is None else count)
    if count is None:
        return spec
    return spec.model_copy(update={"count": count})


def _chat_spec(
    spec: ChatDatasetSpec | None,
    count: int | None,
    min_turns: int | None,
    max_turns: int | None,
) -> ChatDatasetSpec:
    updates: dict[str, object] = {}
    if count is not None:
        updates["count"] = count
    if min_turns is not None:
        updates["min_turns"] = min_turns
    if max_turns is not None:
        updates["max_turns"] = max_turns
    if spec is None:
        return ChatDatasetSpec(**updates)
    return spec.model_copy(update=updates) if updates else spec


def _label_sequence(spec: ClassificationDatasetSpec, verisim: Verisim) -> list[str]:
    total = sum(spec.labels.values())
    allocations: list[tuple[str, int, float]] = []
    for label, weight in spec.labels.items():
        exact = spec.count * weight / total
        base = floor(exact)
        allocations.append((label, base, exact - base))

    remaining = spec.count - sum(base for _, base, _ in allocations)
    by_remainder = sorted(
        enumerate(allocations),
        key=lambda item: (-item[1][2], item[0]),
    )
    counts = {label: base for label, base, _ in allocations}
    for index, _ in by_remainder[:remaining]:
        label = allocations[index][0]
        counts[label] += 1

    labels = [label for label in spec.labels for _ in range(counts[label])]
    verisim.random.shuffle(labels)
    return labels


def _noisy_label(
    verisim: Verisim,
    label_names: list[str],
    intended_label: str,
    spec: ClassificationDatasetSpec,
) -> str:
    if spec.label_noise == 0 or verisim.random.random() >= spec.label_noise:
        return intended_label
    alternatives = [label for label in label_names if label != intended_label]
    return verisim.random.choice(alternatives)


__all__ = [
    "chat_dataset",
    "classification_dataset",
    "instruction_dataset",
    "iter_chat_transcripts",
    "iter_classification_examples",
    "iter_instruction_pairs",
    "iter_ner_sequences",
    "ner_dataset",
]
