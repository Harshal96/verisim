from __future__ import annotations

import re

from verisim.masking.core import MaskingSession
from verisim.masking.types import MaskingConfig, MaskingResult

SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def mask_sql_table(
    connection,
    source_table: str,
    destination_table: str,
    *,
    session: MaskingSession | None = None,
    config: MaskingConfig | None = None,
) -> MaskingResult:
    active_session = session or MaskingSession(config)
    return mask_sql_table_with_session(
        active_session, connection, source_table, destination_table
    )


def mask_sql_table_with_session(
    session: MaskingSession,
    connection,
    source_table: str,
    destination_table: str,
) -> MaskingResult:
    _validate_identifier(source_table)
    _validate_identifier(destination_table)

    source = _quote_identifier(source_table)
    destination = _quote_identifier(destination_table)
    cursor = _execute(connection, f"SELECT * FROM {source}")
    columns = tuple(description[0] for description in cursor.description)
    rows = [_row_to_mapping(row, columns) for row in cursor.fetchall()]
    masked = session.mask_rows(rows)

    _execute(
        connection, f"CREATE TABLE {destination} AS SELECT * FROM {source} WHERE 1=0"
    )
    if columns and masked.rows:
        column_list = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {destination} ({column_list}) VALUES ({placeholders})"
        for row in masked.rows:
            _execute(connection, sql, [row.get(column) for column in columns])
    if hasattr(connection, "commit"):
        connection.commit()

    return MaskingResult(
        data=None,
        columns=masked.columns,
        row_count=len(masked.rows),
        masked_cell_count=masked.masked_cell_count,
        destination_table=destination_table,
    )


def _execute(connection, sql: str, parameters=None):
    if hasattr(connection, "execute"):
        if parameters is None:
            return connection.execute(sql)
        return connection.execute(sql, parameters)
    cursor = connection.cursor()
    if parameters is None:
        cursor.execute(sql)
    else:
        cursor.execute(sql, parameters)
    return cursor


def _row_to_mapping(row, columns: tuple[str, ...]) -> dict[str, object]:
    if hasattr(row, "keys"):
        return {column: row[column] for column in columns}
    return dict(zip(columns, row))


def _validate_identifier(identifier: str) -> None:
    if SAFE_IDENTIFIER_RE.fullmatch(identifier) is None:
        raise ValueError(f"unsafe SQL identifier {identifier!r}")


def _quote_identifier(identifier: str) -> str:
    _validate_identifier(identifier)
    return f'"{identifier}"'
