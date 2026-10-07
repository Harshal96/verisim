# Locale and data packs

[Project overview](../../../README.md) · [Core generation](../README.md)

This folder contains packaged country and locale resources. The loaders live
in [data.py](../data.py), [full_data.py](../full_data.py), and
[packs.py](../packs.py).

## Locale And Script

Locale describes the cultural/data origin. Output language and script are
separate knobs.

```python
from verisim import PersonRecord, Verisim

v = Verisim(locale="en_IN", output_language="en", script="latin", seed=13)
record = v.generate(PersonRecord)

print(record.person.name)
print(record.address.country_code)
print(record.contact.phone.e164)
```

This supports Indian names in Latin script, such as `Rakesh`, `Om`, or
`Prakash`, while keeping address and phone fields country-aware.

The lite pack includes US, UK, Canadian, Australian, Indian, German, Mexican,
Japanese, French, Brazilian, and Chinese coverage. The packaged locale codes
are `en_US`, `en_GB`, `en_CA`, `en_AU`, `en_IN`, `hi_IN`, `de_DE`, `es_MX`,
`ja_JP`, `fr_FR`, `pt_BR`, and `zh_CN`; each includes 1,000 given names and
1,000 family names.

Country address data for `US`, `GB`, `CA`, `AU`, `IN`, `DE`, `MX`, `JP`, `FR`,
`BR`, and `CN` is generated from open
[GeoNames postal-code archives](https://download.geonames.org/export/zip/) with
Verisim-authored synthetic street names and suffixes. The packaged data
currently contains 53 US regions, 6 UK regions, 13 Canadian regions, 8
Australian regions, 35 Indian regions, 33 German regions, 32 Mexican regions,
47 Japanese regions, 14 French regions, 27 Brazilian regions, and 35 Chinese
regions, covering more than 3.3 million postal-code-to-city relationships.
Canada and the UK use the GeoNames full-code archives; the standard GeoNames
country ZIPs are used for the other supported countries. The source data is
useful for coherent synthetic generation, not postal authority validation.

To refresh the packaged country JSON files from GeoNames:

```bash
uv run python scripts/build_country_datasets.py --download
```

The refresh script downloads archives over HTTPS and verifies each source
archive against the pinned SHA-256 manifest before rebuilding packaged JSON.

Run the refresh command from the repository root. The script is
[build_country_datasets.py](../../../scripts/build_country_datasets.py).

## Lite and Full Packs

`lite` is the default built-in pack. The `lite` and `full` extras add no Python
dependencies; select the expanded pack explicitly with `data_pack="full"`.
The current full pack extends lite coverage with Spanish names and addresses
for Spain (`es_ES` / `ES`). Larger global packs remain future work.

Use the full data tier when you want broader locale coverage:

```bash
uv add "verisim[full]"
```

```python
from verisim import PersonRecord, Verisim

record = Verisim(
    locale="es_ES",
    script="latin",
    data_pack="full",
    seed=7,
).generate(PersonRecord)
```
