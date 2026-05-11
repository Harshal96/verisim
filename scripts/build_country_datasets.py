from __future__ import annotations

import argparse
import hashlib
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

GEONAMES_BASE_URL = "https://download.geonames.org/export/zip"
DEFAULT_SOURCE_DIR = ROOT / ".cache" / "address-sources"
DEFAULT_OUTPUT_DIR = ROOT / "src" / "verisim" / "datasets" / "countries"
GEONAMES_ARCHIVE_FILENAMES = {
    "AU": "AU.zip",
    "CA": "CA_full.csv.zip",
    "DE": "DE.zip",
    "MX": "MX.zip",
    "JP": "JP.zip",
    "FR": "FR.zip",
    "BR": "BR.zip",
    "CN": "CN.zip",
    "GB": "GB_full.csv.zip",
    "IN": "IN.zip",
    "US": "US.zip",
}
GEONAMES_ARCHIVE_SHA256 = {
    "AU": "d5078e140f97cc7339eba3f15246b68971772a63cc71ca4c8b83d7aa499c08b5",
    "CA": "98bb3c317101a223bd2b8bf59ca612188875dc9ff50181bba86a2155067461d3",
    "DE": "46c4a9949278ad88be1b5876bff962b1e5dacce22bf8dec677e4e7d5d40b7c21",
    "MX": "9c7d88e2d845c73de89ccf28a3ca588d2684163a03243061398e34192f71bb09",
    "JP": "acd5df95f752910acaa665d1c5fa300162cfb737ad461e81ea22f8c4a19f4d34",
    "FR": "5418357f4098f37ee2cc2226999af2e111f1bc07fa012177c69811ab51fa83f4",
    "BR": "62c3b56cc05b0564180c0915dec8159ce2f82579b88f0d0e021e38a2ba1ad93c",
    "CN": "57a09b5243cb861f9b29e780b8f29aba8dea84e819ebd44f41852941bb976884",
    "GB": "196bd53e020143c984c07ade27bda0220bb03270600d9df496fa5403a318913b",
    "IN": "085ac1030cd8a8807a48134a7f34f7b99ec3e7aad3dd16ea997cff809fdeecb4",
    "US": "fc0b98364dddd6b3f28633154c2b09845fa7f6d37540893bec78b58a58a24f9e",
}


def source_url(country_code: str) -> str:
    return f"{GEONAMES_BASE_URL}/{GEONAMES_ARCHIVE_FILENAMES[country_code]}"


def archive_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_country_archive(country_code: str, archive_path: Path) -> None:
    expected = GEONAMES_ARCHIVE_SHA256[country_code]
    actual = archive_sha256(archive_path)
    if actual != expected:
        raise ValueError(
            f"GeoNames archive {archive_path.name} failed SHA-256 verification "
            f"for {country_code}: expected {expected}, got {actual}"
        )


def download_country_archives(
    source_dir: Path, country_codes: tuple[str, ...]
) -> dict[str, Path]:
    source_dir.mkdir(parents=True, exist_ok=True)
    archives = {}
    for country_code in country_codes:
        archive_path = source_dir / GEONAMES_ARCHIVE_FILENAMES[country_code]
        urllib.request.urlretrieve(source_url(country_code), archive_path)
        verify_country_archive(country_code, archive_path)
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
        verify_country_archive(country_code, archive_path)
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
