from __future__ import annotations

pytest_plugins = ("pytester",)


def test_verisim_fixture_decorator_builds_seeded_sqlalchemy_records(pytester):
    pytester.makepyfile(test_seeded_records="""
        from __future__ import annotations

        from sqlalchemy import Integer, String
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

        from verisim.integrations.pytest import verisim_fixture


        class Base(DeclarativeBase):
            pass


        class User(Base):
            __tablename__ = "fixture_users"

            id: Mapped[int] = mapped_column(
                Integer, primary_key=True, autoincrement=True
            )
            email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
            username: Mapped[str] = mapped_column(
                String(40), nullable=False, unique=True
            )


        seeded_user = verisim_fixture(User, adapter="sqlalchemy", seed=77)


        def test_seeded_user_has_semantic_values(seeded_user):
            assert seeded_user.email.endswith(".example.invalid")
            assert seeded_user.username
            assert seeded_user.id is None
        """)

    result = pytester.runpytest("-q")

    result.assert_outcomes(passed=1)


def test_verisim_fixture_supports_scope_and_explicit_sqlalchemy_persistence(pytester):
    pytester.makepyfile(test_persisted_records="""
        from __future__ import annotations

        import pytest
        from sqlalchemy import Integer, String, create_engine
        from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

        from verisim.integrations.pytest import verisim_fixture


        class Base(DeclarativeBase):
            pass


        class User(Base):
            __tablename__ = "persisted_fixture_users"

            id: Mapped[int] = mapped_column(
                Integer, primary_key=True, autoincrement=True
            )
            email: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
            username: Mapped[str] = mapped_column(
                String(40), nullable=False, unique=True
            )


        @pytest.fixture(scope="module")
        def db_session():
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)
            with Session(engine) as session:
                yield session


        persisted_user = verisim_fixture(
            User,
            adapter="sqlalchemy",
            scope="module",
            seed=88,
            persist=True,
            session_fixture="db_session",
        )


        def test_first_use_gets_persisted_user(persisted_user):
            assert persisted_user.id is not None


        def test_module_scope_reuses_the_same_persisted_user(persisted_user):
            assert persisted_user.id == 1
        """)

    result = pytester.runpytest("-q")

    result.assert_outcomes(passed=2)
