from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from verisim.models import (
    Company,
    PersonRecord,
    ProductRecord,
    SupportTicketRecord,
    VerisimModel,
)

EntityLabel = Literal["PERSON", "ORG", "LOC", "DATE"]
ChatRole = Literal["user", "assistant"]
ChatSpeaker = Literal["customer", "support_agent"]


class InstructionResponsePair(VerisimModel):
    instruction: str = Field(min_length=1)
    response: str = Field(min_length=1)


class ClassificationExample(VerisimModel):
    text: str = Field(min_length=1)
    label: str = Field(min_length=1)


class NerEntity(VerisimModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    label: EntityLabel
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_span(self) -> "NerEntity":
        if self.end <= self.start:
            raise ValueError("entity end must be greater than start")
        if self.end - self.start != len(self.text):
            raise ValueError("entity span length must match entity text")
        return self


class NerSequence(VerisimModel):
    text: str = Field(min_length=1)
    entities: list[NerEntity] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_entity_text(self) -> "NerSequence":
        for entity in self.entities:
            if self.text[entity.start : entity.end] != entity.text:
                raise ValueError("entity text must match sequence span")
        return self


class ChatMessage(VerisimModel):
    role: ChatRole
    speaker: ChatSpeaker
    content: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_role_speaker_pair(self) -> "ChatMessage":
        expected = "customer" if self.role == "user" else "support_agent"
        if self.speaker != expected:
            raise ValueError("chat speaker must match role")
        return self


class ChatTranscript(VerisimModel):
    messages: list[ChatMessage] = Field(min_length=1)


class InstructionDataset(VerisimModel):
    examples: list[InstructionResponsePair]


class ClassificationDataset(VerisimModel):
    examples: list[ClassificationExample]


class NerDataset(VerisimModel):
    sequences: list[NerSequence]


class ChatDataset(VerisimModel):
    transcripts: list[ChatTranscript]


class InstructionDatasetSpec(VerisimModel):
    count: int = Field(default=10, ge=0)


class ClassificationDatasetSpec(VerisimModel):
    count: int = Field(default=10, ge=0)
    labels: dict[str, float] = Field(
        default_factory=lambda: {"positive": 4, "neutral": 3, "critical": 3}
    )
    label_noise: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, labels: dict[str, float]) -> dict[str, float]:
        if not labels:
            raise ValueError("labels must not be empty")
        if any(not label.strip() for label in labels):
            raise ValueError("labels must not contain blank names")
        if any(weight <= 0 for weight in labels.values()):
            raise ValueError("label weights must be positive")
        return labels


class NerDatasetSpec(VerisimModel):
    count: int = Field(default=10, ge=0)


class ChatDatasetSpec(VerisimModel):
    count: int = Field(default=10, ge=0)
    min_turns: int = Field(default=2, ge=1)
    max_turns: int = Field(default=4, ge=1)

    @model_validator(mode="after")
    def validate_turn_bounds(self) -> "ChatDatasetSpec":
        if self.max_turns < self.min_turns:
            raise ValueError("max_turns must be greater than or equal to min_turns")
        return self


class AITrainingContext(VerisimModel):
    person: PersonRecord
    company: Company
    product: ProductRecord
    ticket: SupportTicketRecord


__all__ = [
    "AITrainingContext",
    "ChatDataset",
    "ChatDatasetSpec",
    "ChatMessage",
    "ChatRole",
    "ChatSpeaker",
    "ChatTranscript",
    "ClassificationDataset",
    "ClassificationDatasetSpec",
    "ClassificationExample",
    "EntityLabel",
    "InstructionDataset",
    "InstructionDatasetSpec",
    "InstructionResponsePair",
    "NerDataset",
    "NerDatasetSpec",
    "NerEntity",
    "NerSequence",
]
