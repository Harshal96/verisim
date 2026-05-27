from __future__ import annotations

from verisim import PersonRecord, Verisim
from verisim.packs import DataPackManager


def test_full_data_pack_is_registered():
    manager = DataPackManager()

    assert manager.available() == ("full", "lite")


def test_full_data_pack_supports_additional_spanish_locale():
    record = Verisim(
        locale="es_ES",
        output_language="es",
        script="latin",
        data_pack="full",
        seed=77,
    ).generate(PersonRecord)

    assert record.person.locale == "es_ES"
    assert record.address.country_code == "ES"
    assert record.contact.phone.country_code == "ES"
    assert record.contact.phone.e164.startswith("+34")


def test_full_data_pack_uses_regional_address_variant():
    record = Verisim(
        locale="es_ES",
        output_language="es",
        script="latin",
        data_pack="full",
        seed=78,
    ).generate(PersonRecord)

    assert any(
        token in record.address.line1
        for token in ("Calle", "Avenida", "Plaza", "Paseo")
    )
