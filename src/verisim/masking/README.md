# Mask Existing PII

[Verisim overview](../../../README.md) · [Package guide](../README.md)

The `verisim[masking]` extra can mask direct identifiers in existing tabular
data. It detects likely person, email, phone, and address columns, then replaces
each real identity with a coherent synthetic `PersonRecord`. Reusing a
`MaskingSession` preserves mappings across multiple DataFrames or SQL tables
within the same run, so repeated emails and related rows keep joining.

```python
import pandas as pd

from verisim import MaskingConfig, MaskingSession, mask_dataframe

df = pd.DataFrame(
    [
        {"name": "Alice Adams", "email": "alice@company.com", "city": "Chicago"},
        {"name": "Alice Adams", "email": "alice@company.com", "city": "Chicago"},
    ]
)

session = MaskingSession(MaskingConfig(seed=42))
masked = mask_dataframe(df, session=session).data
```

For DB-API connections, `mask_sql_table()` creates a masked destination table
and leaves the source table untouched. The v1 write path is SQLite-tested and
uses simple validated table identifiers.

Install the pandas dependency with:

```bash
uv add "verisim[masking]"
```

Implementation: [DataFrame masking and sessions](core.py),
[column detection](detection.py), [SQL table masking](sql.py), and
[configuration and result types](types.py).
