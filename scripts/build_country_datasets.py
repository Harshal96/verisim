from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from verisim.data import (  # noqa: E402
    LITE_COUNTRY_CODES,
    CountryData,
    load_geonames_postal_countries,
)

GEONAMES_BASE_URL = "http://download.geonames.org/export/zip"
DEFAULT_SOURCE_DIR = ROOT / ".cache" / "address-sources"
DEFAULT_OUTPUT_DIR = ROOT / "src" / "verisim" / "datasets" / "countries"
GEONAMES_ARCHIVE_FILENAMES = {
    "AU": "AU.zip",
    "CA": "CA_full.csv.zip",
    "DE": "DE.zip",
    "GB": "GB_full.csv.zip",
    "IN": "IN.zip",
    "US": "US.zip",
}


def source_url(country_code: str) -> str:
    return f"{GEONAMES_BASE_URL}/{GEONAMES_ARCHIVE_FILENAMES[country_code]}"


def download_country_archives(
    source_dir: Path, country_codes: tuple[str, ...]
) -> dict[str, Path]:
    source_dir.mkdir(parents=True, exist_ok=True)
    archives = {}
    for country_code in country_codes:
        archive_path = source_dir / GEONAMES_ARCHIVE_FILENAMES[country_code]
        urllib.request.urlretrieve(source_url(country_code), archive_path)
        archives[country_code] = archive_path
    return archives


def local_country_archives(
    source_dir: Path, country_codes: tuple[str, ...]
) -> dict[str, Path]:
    archives = {}
    for country_code in country_codes:
        archive_path = source_dir / GEONAMES_ARCHIVE_FILENAMES[country_code]
        if not archive_path.exists():
            raise FileNotFoundError(
                f"Missing {archive_path}. Re-run with --download or add the archive."
            )
        archives[country_code] = archive_path
    return archives


def existing_country(country_code: str, output_dir: Path) -> CountryData | None:
    path = output_dir / f"{country_code}.json"
    if not path.exists():
        return None
    from verisim.data import _country_from_payload

    return _country_from_payload(json.loads(path.read_text(encoding="utf-8")))


def with_existing_streets(country: CountryData, output_dir: Path) -> CountryData:
    current = existing_country(country.code, output_dir)
    if current is None:
        return country
    return replace(
        country,
        street_names=current.street_names,
        street_suffixes=current.street_suffixes,
    )


def write_country(country: CountryData, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{country.code}.json"
    path.write_text(
        json.dumps(asdict(country), ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return path


def build_country_datasets(
    archives: dict[str, Path], output_dir: Path
) -> dict[str, CountryData]:
    countries = {}
    for country_code, archive_path in sorted(archives.items()):
        loaded = load_geonames_postal_countries(
            archive_path, country_codes={country_code}
        )[country_code]
        country = with_existing_streets(loaded, output_dir)
        write_country(country, output_dir)
        countries[country_code] = country
    return countries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Verisim country address JSON from open GeoNames postal data."
    )
    parser.add_argument(
        "--country",
        action="append",
        choices=LITE_COUNTRY_CODES,
        dest="countries",
        help="Country code to build. Repeat to build multiple countries.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download GeoNames source archives before building.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=(
            "Directory containing GeoNames country ZIP files. "
            f"Default: {DEFAULT_SOURCE_DIR}"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Directory for generated country JSON files. "
            f"Default: {DEFAULT_OUTPUT_DIR}"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    country_codes = tuple(args.countries or LITE_COUNTRY_CODES)
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    archives = (
        download_country_archives(source_dir, country_codes)
        if args.download
        else local_country_archives(source_dir, country_codes)
    )
    countries = build_country_datasets(archives, output_dir)
    for country_code, country in countries.items():
        city_count = sum(len(region.cities) for region in country.regions)
        postal_code_count = sum(
            len(city.postal_codes)
            for region in country.regions
            for city in region.cities
        )
        print(
            f"{country_code}: {len(country.regions)} regions, "
            f"{city_count} cities, {postal_code_count} postal codes"
        )


if __name__ == "__main__":
    main()
