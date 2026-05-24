from __future__ import annotations

from typing import Literal

import pytest as _pytest

from verisim.integrations._core import stable_seed

AdapterName = Literal["sqlalchemy", "django"]
FixtureScope = Literal["function", "class", "module", "package", "session"]


def verisim_fixture(
    model: type[object],
    *,
    adapter: AdapterName,
    scope: FixtureScope = "function",
    seed: int | None = None,
    persist: bool | None = None,
    session_fixture: str = "db_session",
    name: str | None = None,
    **factory_kwargs: object,
):
    @_pytest.fixture(scope=scope, name=name)
    def fixture(request):
        fixture_seed = stable_seed(
            seed,
            request.fixturename,
            scope,
            getattr(request.node, "nodeid", ""),
        )
        factory = _factory_for(
            model, adapter=adapter, seed=fixture_seed, **factory_kwargs
        )
        should_persist = adapter == "django" if persist is None else persist
        if adapter == "sqlalchemy":
            if should_persist:
                session = request.getfixturevalue(session_fixture)
                return factory.create(session)
            return factory.build()
        if should_persist:
            return factory.create()
        return factory.build()

    return fixture


def _factory_for(
    model: type[object],
    *,
    adapter: AdapterName,
    seed: int | None,
    **factory_kwargs: object,
):
    if adapter == "sqlalchemy":
        from verisim.integrations.sqlalchemy import verisim_factory

        return verisim_factory(model, seed=seed, **factory_kwargs)
    if adapter == "django":
        from verisim.integrations.django import verisim_factory

        return verisim_factory(model, seed=seed, **factory_kwargs)
    raise ValueError(f"unsupported verisim fixture adapter {adapter!r}")


__all__ = ["verisim_fixture"]
