from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from verisim.api import Verisim
from verisim.masking.detection import detect_pii_columns
from verisim.masking.types import MaskingConfig, MaskingResult, PIIColumn, _MaskedRows
from verisim.models import PersonRecord

PANDAS_INSTALL_HINT = "Install optional masking dependencies with `verisim[masking]`."


class MaskingSession:
    def __init__(self, config: MaskingConfig | None = None) -> None:
        self.config = config or MaskingConfig()
        self._verisim = Verisim(
            locale=self.config.locale,
            output_language=self.config.output_language,
            script=self.config.script,
            seed=self.config.seed,
        )
        self._records_by_identity: dict[str, PersonRecord] = {}

    def detect_columns(
        self, rows: Iterable[Mapping[str, object]]
    ) -> tuple[PIIColumn, ...]:
        return detect_pii_columns(rows, self.config)

    def mask_dataframe(self, dataframe) -> MaskingResult:
        pd = _require_pandas()
        if not isinstance(dataframe, pd.DataFrame):
            raise TypeError("mask_dataframe expects a pandas DataFrame")

        rows = dataframe.to_dict(orient="records")
        masked = self.mask_rows(rows)
        masked_frame = pd.DataFrame(
            masked.rows,
            index=dataframe.index.copy(),
            columns=list(dataframe.columns),
        )
        return MaskingResult(
            data=masked_frame,
            columns=masked.columns,
            row_count=len(masked.rows),
            masked_cell_count=masked.masked_cell_count,
        )

    def mask_rows(self, rows: Iterable[Mapping[str, object]]) -> _MaskedRows:
        row_list = [dict(row) for row in rows]
        columns = self.detect_columns(row_list)
        masked_rows: list[dict[str, object]] = []
        masked_cell_count = 0

        for row_index, row in enumerate(row_list):
            record = self._record_for_row(row, columns, row_index)
            masked_row = dict(row)
            for column in columns:
                value = row.get(column.name)
                if _is_blank(value):
                    continue
                replacement = _replacement_for(record, column, value)
                if replacement != value:
                    masked_cell_count += 1
                masked_row[column.name] = replacement
            masked_rows.append(masked_row)

        return _MaskedRows(
            rows=masked_rows,
            columns=columns,
            masked_cell_count=masked_cell_count,
        )

    def mask_sql_table(
        self,
        connection,
        source_table: str,
        destination_table: str,
    ) -> MaskingResult:
        from verisim.masking.sql import mask_sql_table_with_session

        return mask_sql_table_with_session(
            self, connection, source_table, destination_table
        )

    def _record_for_row(
        self,
        row: Mapping[str, object],
        columns: tuple[PIIColumn, ...],
        row_index: int,
    ) -> PersonRecord:
        identity = self._identity_key(row, columns, row_index)
        record = self._records_by_identity.get(identity)
        if record is None:
            generated = self._verisim.generate(PersonRecord)
            assert isinstance(generated, PersonRecord)
            self._records_by_identity[identity] = generated
            return generated
        return record

    def _identity_key(
        self,
        row: Mapping[str, object],
        columns: tuple[PIIColumn, ...],
        row_index: int,
    ) -> str:
        if self.config.identity_columns is not None:
            missing = [
                column for column in self.config.identity_columns if column not in row
            ]
            if missing:
                raise ValueError(f"identity columns are missing: {', '.join(missing)}")
            return "explicit:" + "|".join(
                _normalize_value(row.get(column))
                for column in self.config.identity_columns
            )

        values_by_kind = _values_by_kind(row, columns)
        if values_by_kind.get("email"):
            return f"email:{values_by_kind['email'].lower()}"
        if values_by_kind.get("phone"):
            return f"phone:{_digits(values_by_kind['phone'])}"

        name = _name_value(values_by_kind)
        address = _address_value(values_by_kind)
        if name and address:
            return f"name-address:{name}|{address}"
        if name:
            return f"name:{name}"
        return f"row:{row_index}"


def mask_dataframe(
    dataframe,
    *,
    session: MaskingSession | None = None,
    config: MaskingConfig | None = None,
) -> MaskingResult:
    active_session = session or MaskingSession(config)
    return active_session.mask_dataframe(dataframe)


def _require_pandas():
    try:
        import pandas as pd
    except ImportError as error:  # pragma: no cover - covered in base installs
        raise ImportError(PANDAS_INSTALL_HINT) from error
    return pd


def _values_by_kind(
    row: Mapping[str, object], columns: tuple[PIIColumn, ...]
) -> dict[str, str]:
    values: dict[str, str] = {}
    for column in columns:
        value = row.get(column.name)
        if _is_blank(value):
            continue
        values.setdefault(column.kind, _normalize_value(value))
    return values


def _name_value(values_by_kind: Mapping[str, str]) -> str:
    if values_by_kind.get("name"):
        return values_by_kind["name"]
    parts = [
        values_by_kind.get("given_name", ""),
        values_by_kind.get("family_name", ""),
    ]
    return " ".join(part for part in parts if part)


def _address_value(values_by_kind: Mapping[str, str]) -> str:
    parts = [
        values_by_kind.get("address", ""),
        values_by_kind.get("address_line1", ""),
        values_by_kind.get("city", ""),
        values_by_kind.get("region", ""),
        values_by_kind.get("region_code", ""),
        values_by_kind.get("postal_code", ""),
        values_by_kind.get("country", ""),
        values_by_kind.get("country_code", ""),
    ]
    return "|".join(part for part in parts if part)


def _replacement_for(record: PersonRecord, column: PIIColumn, original: object) -> str:
    address = record.address
    if column.kind == "name":
        return record.person.name
    if column.kind == "given_name":
        return record.person.given_name
    if column.kind == "family_name":
        return record.person.family_name
    if column.kind == "email":
        return record.contact.email
    if column.kind == "phone":
        return _format_phone(record, original)
    if column.kind == "address":
        return (
            f"{address.line1}, {address.city}, {address.region_code} "
            f"{address.postal_code}, {address.country}"
        )
    if column.kind == "address_line1":
        return address.line1
    if column.kind == "city":
        return address.city
    if column.kind == "region":
        return address.region_code if _looks_like_code(original) else address.region
    if column.kind == "region_code":
        return address.region_code
    if column.kind == "postal_code":
        return address.postal_code
    if column.kind == "country":
        return address.country_code if _looks_like_code(original) else address.country
    if column.kind == "country_code":
        return address.country_code
    raise ValueError(f"unsupported PII kind {column.kind!r}")


def _format_phone(record: PersonRecord, original: object) -> str:
    text = str(original).strip()
    if text.startswith("+") or re.fullmatch(r"\d{10,}", text):
        return record.contact.phone.e164
    return record.contact.phone.national


def _looks_like_code(value: object) -> bool:
    text = str(value).strip()
    return 1 < len(text) <= 3 and text.upper() == text


def _normalize_value(value: object) -> str:
    return " ".join(str(value).strip().split())


def _digits(value: object) -> str:
    return "".join(character for character in str(value) if character.isdigit())


def _is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""
