"""Regression checks for free-server PDF resource boundaries."""

from pathlib import Path
import tomllib

from src.pdf_resource_policy import (
    GENERAL_OFFICIAL_PDF_MAX_BYTES,
    MANUAL_PDF_MAX_BYTES,
    ONBOARDING_PDF_MAX_BYTES,
    PDF_MAX_PAGES,
    PDF_MAX_TEXT_CHARACTERS,
    SNAPSHOT_PDF_MAX_BYTES,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_named_pdf_limits_preserve_the_four_workflow_boundaries() -> None:
    mebibyte = 1024 * 1024

    assert MANUAL_PDF_MAX_BYTES == 32 * mebibyte
    assert GENERAL_OFFICIAL_PDF_MAX_BYTES == 45 * mebibyte
    assert ONBOARDING_PDF_MAX_BYTES == 32 * mebibyte
    assert SNAPSHOT_PDF_MAX_BYTES == 45 * mebibyte
    assert PDF_MAX_PAGES == 1000
    assert PDF_MAX_TEXT_CHARACTERS == 8_000_000


def test_streamlit_rejects_large_uploads_before_application_code() -> None:
    config = tomllib.loads(
        (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(
            encoding="utf-8"
        )
    )

    assert config["server"]["maxUploadSize"] == 32


def test_each_production_pdf_path_uses_its_named_limit() -> None:
    app_source = (PROJECT_ROOT / "src" / "app.py").read_text(
        encoding="utf-8"
    )

    assert "max_bytes=GENERAL_OFFICIAL_PDF_MAX_BYTES" in app_source
    assert app_source.count("max_bytes=ONBOARDING_PDF_MAX_BYTES") == 2
    assert app_source.count("max_bytes=SNAPSHOT_PDF_MAX_BYTES") == 2
    assert "report_max_bytes = MANUAL_PDF_MAX_BYTES" in app_source
