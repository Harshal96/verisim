from pathlib import Path

import pytest

from scripts import build_country_datasets


def test_geonames_source_urls_use_https():
    assert build_country_datasets.source_url("US").startswith("https://")


def test_downloaded_geonames_archives_are_sha256_verified(tmp_path, monkeypatch):
    def fake_urlretrieve(url: str, filename: str | Path) -> tuple[str | Path, None]:
        Path(filename).write_bytes(b"tampered postal data")
        return filename, None

    monkeypatch.setattr(
        build_country_datasets.urllib.request, "urlretrieve", fake_urlretrieve
    )
    monkeypatch.setattr(
        build_country_datasets,
        "GEONAMES_ARCHIVE_SHA256",
        {"US": "0" * 64},
        raising=False,
    )

    with pytest.raises(ValueError, match="SHA-256"):
        build_country_datasets.download_country_archives(tmp_path, ("US",))


def test_local_geonames_archives_are_sha256_verified(tmp_path, monkeypatch):
    (tmp_path / "US.zip").write_bytes(b"tampered postal data")
    monkeypatch.setattr(
        build_country_datasets,
        "GEONAMES_ARCHIVE_SHA256",
        {"US": "0" * 64},
        raising=False,
    )

    with pytest.raises(ValueError, match="SHA-256"):
        build_country_datasets.local_country_archives(tmp_path, ("US",))
