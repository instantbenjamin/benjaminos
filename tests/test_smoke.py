"""Smoke test — proves CI is wired and packages import."""

import pytest


def test_packages_importable():
    """All four packages should import without error."""
    import ingest  # noqa: F401
    import pharoah  # noqa: F401
    import hermes  # noqa: F401
    import shared  # noqa: F401


def test_ingest_version():
    import ingest

    assert ingest.__version__ == "0.1.0"


def test_pharoah_version():
    import pharoah

    assert pharoah.__version__ == "0.1.0"


@pytest.mark.integration
def test_supabase_reachable():
    """Integration: Supabase DATABASE_URL works (skipped by default — run with -m integration)."""
    pytest.skip("Implement once packages/shared/supabase.py exists")
