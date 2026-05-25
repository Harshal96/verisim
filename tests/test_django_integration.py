from __future__ import annotations

from datetime import date

import django
import pytest
from django.conf import settings
from django.db import connection, models

from verisim.integrations import UnsupportedIntegrationFieldError
from verisim.integrations.django import verisim_factory

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[],
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        },
        DEFAULT_AUTO_FIELD="django.db.models.AutoField",
        SECRET_KEY="verisim-tests",
        USE_TZ=True,
    )
    django.setup()


class DjangoOrganization(models.Model):
    name = models.CharField(max_length=80, unique=True)
    domain = models.CharField(max_length=120, unique=True)

    class Meta:
        app_label = "verisim_tests"


class DjangoUser(models.Model):
    organization = models.ForeignKey(DjangoOrganization, on_delete=models.CASCADE)
    email = models.EmailField(max_length=120, unique=True)
    username = models.CharField(max_length=40, unique=True)
    first_name = models.CharField(max_length=40)
    last_name = models.CharField(max_length=40)
    birthday = models.DateField()
    status = models.CharField(
        max_length=12,
        choices=(("active", "Active"), ("paused", "Paused")),
    )
    nickname = models.CharField(max_length=40, null=True, blank=True)

    class Meta:
        app_label = "verisim_tests"


class DjangoUnsupportedRequired(models.Model):
    payload = models.BinaryField()

    class Meta:
        app_label = "verisim_tests"


@pytest.fixture(scope="module", autouse=True)
def django_tables():
    models_to_create = (DjangoOrganization, DjangoUser, DjangoUnsupportedRequired)
    with connection.schema_editor() as schema:
        for model in models_to_create:
            schema.create_model(model)
    yield
    with connection.schema_editor() as schema:
        for model in reversed(models_to_create):
            schema.delete_model(model)


def test_django_factory_builds_unsaved_instance_with_required_parent(django_tables):
    factory = verisim_factory(DjangoUser, seed=123)

    user = factory.build()

    assert isinstance(user, DjangoUser)
    assert user.pk is None
    assert isinstance(user.organization, DjangoOrganization)
    assert user.organization.pk is None
    assert user.organization.name
    assert user.organization.domain.endswith(".example.invalid")
    assert user.email.endswith(".example.invalid")
    assert user.username
    assert user.first_name
    assert user.last_name
    assert isinstance(user.birthday, date)
    assert user.status == "active"
    assert user.nickname is None


def test_django_factory_create_persists_parent_and_child(django_tables):
    factory = verisim_factory(DjangoUser, seed=456)

    user = factory.create(overrides={"email": "created@example.invalid"})

    assert user.pk is not None
    assert user.organization.pk is not None
    assert user.email == "created@example.invalid"
    assert DjangoUser.objects.filter(pk=user.pk).exists()
    assert DjangoOrganization.objects.filter(pk=user.organization.pk).exists()


def test_django_factory_rejects_required_fields_without_safe_generator(django_tables):
    factory = verisim_factory(DjangoUnsupportedRequired, seed=9)

    with pytest.raises(UnsupportedIntegrationFieldError, match="payload"):
        factory.build()
