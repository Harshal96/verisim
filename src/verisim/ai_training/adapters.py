from __future__ import annotations

from typing import Protocol

from verisim.ai_training.models import (
    AITrainingContext,
    ChatMessage,
    ChatTranscript,
    InstructionResponsePair,
    NerEntity,
    NerSequence,
)


class AIGenerationAdapter(Protocol):
    def instruction_response(
        self, context: AITrainingContext
    ) -> InstructionResponsePair: ...

    def classification_text(self, context: AITrainingContext, label: str) -> str: ...

    def ner_sequence(self, context: AITrainingContext) -> NerSequence: ...

    def chat_transcript(
        self, context: AITrainingContext, turns: int
    ) -> ChatTranscript: ...


class OfflineAIGenerationAdapter:
    """Deterministic, no-network training text generator."""

    def instruction_response(
        self, context: AITrainingContext
    ) -> InstructionResponsePair:
        return InstructionResponsePair(
            instruction=(
                f"Write a concise onboarding note for {context.person.person.name}, "
                f"a {context.person.job.title} at {context.company.name}, about "
                f"using {context.product.name}."
            ),
            response=(
                f"{context.person.person.name} can use {context.product.name} to "
                f"support {context.person.job.department.lower()} work at "
                f"{context.company.name}. Start with {context.product.features[0]} "
                f"and route questions through the {context.ticket.category} support "
                "workflow."
            ),
        )

    def classification_text(self, context: AITrainingContext, label: str) -> str:
        return (
            f"{context.person.person.name} described {context.product.name} for "
            f"{context.company.name} as {label} after a {context.ticket.category} "
            f"support interaction."
        )

    def ner_sequence(self, context: AITrainingContext) -> NerSequence:
        person = context.person.person.name
        company = context.company.name
        location = context.person.address.city
        date = context.ticket.opened_at[:10]
        text = (
            f"{person} from {company} opened a support request in {location} on "
            f"{date} about {context.product.name}."
        )
        return NerSequence(
            text=text,
            entities=[
                _entity(text, person, "PERSON"),
                _entity(text, company, "ORG"),
                _entity(text, location, "LOC"),
                _entity(text, date, "DATE"),
            ],
        )

    def chat_transcript(self, context: AITrainingContext, turns: int) -> ChatTranscript:
        customer_templates = (
            (
                f"Hi, I'm {context.person.person.name} from {context.company.name}. "
                f"We need help with {context.product.name} because "
                f"{context.ticket.description}"
            ),
            (
                f"Our {context.person.job.department} team is seeing "
                f"{context.ticket.subject.lower()}."
            ),
            (
                f"Can you keep the guidance specific to "
                f"{context.product.features[0]}?"
            ),
            "That helps. What should we check next?",
        )
        agent_templates = (
            (
                f"Thanks {context.person.person.given_name}. I can help with the "
                f"{context.ticket.category} request for {context.product.name}."
            ),
            (
                f"Please confirm the affected workspace at {context.company.domain} "
                "and share the last successful sync time."
            ),
            (
                f"For {context.product.features[0]}, review the current plan and "
                "retry the workflow after refreshing permissions."
            ),
            (
                f"I'll document this on ticket {context.ticket.id} and keep the "
                "support summary tied to your account."
            ),
        )
        messages: list[ChatMessage] = []
        for index in range(turns):
            messages.append(
                ChatMessage(
                    role="user",
                    speaker="customer",
                    content=customer_templates[index % len(customer_templates)],
                )
            )
            messages.append(
                ChatMessage(
                    role="assistant",
                    speaker="support_agent",
                    content=agent_templates[index % len(agent_templates)],
                )
            )
        return ChatTranscript(messages=messages)


def _entity(text: str, value: str, label: str) -> NerEntity:
    start = text.index(value)
    return NerEntity(start=start, end=start + len(value), label=label, text=value)


__all__ = ["AIGenerationAdapter", "OfflineAIGenerationAdapter"]
