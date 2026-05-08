from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from random import Random
from typing import Protocol

from verisim.data import LiteDataPack
from verisim.errors import UnsupportedModelError
from verisim.registry import UniquenessRegistry


@dataclass
class GenerationState:
    random: Random
    data: LiteDataPack
    registry: UniquenessRegistry
    locale: str
    output_language: str
    script: str
    facts: dict[str, object]


class Provider(Protocol):
    provides: tuple[str, ...]
    requires: tuple[str, ...]

    def generate(self, state: GenerationState) -> Mapping[str, object]:
        ...


class ContextGraph:
    def __init__(self, providers: Iterable[Provider], targets: Mapping[type, str]) -> None:
        self._providers_by_fact: dict[str, Provider] = {}
        for provider in providers:
            for fact in provider.provides:
                self._providers_by_fact[fact] = provider
        self._targets = dict(targets)

    def generate(self, model: type, state: GenerationState) -> object:
        target_fact = self._targets.get(model)
        if target_fact is None:
            raise UnsupportedModelError(f"Verisim does not know how to generate {model!r}")
        self.resolve(target_fact, state)
        return state.facts[target_fact]

    def resolve(self, fact: str, state: GenerationState) -> None:
        if fact in state.facts:
            return
        provider = self._providers_by_fact.get(fact)
        if provider is None:
            raise UnsupportedModelError(f"No provider can produce fact {fact!r}")
        for requirement in provider.requires:
            self.resolve(requirement, state)
        generated = provider.generate(state)
        state.facts.update(generated)
