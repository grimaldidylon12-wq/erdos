import re
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Every test gets its own catalogue cache; the compiled kernel cache is shared."""
    import os
    shared = Path(os.environ.get("ERDOS_ENGINE_TEST_SHARED", Path.home() / ".cache" / "erdos_engine"))
    monkeypatch.setenv("ERDOS_ENGINE_CACHE", str(shared))
    import erdos_engine.catalog as cat
    monkeypatch.setattr(cat, "cache_dir", lambda: _mk(tmp_path / "catalog"))
    yield


def _mk(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def fake_fetch(url: str) -> str:
    if url.endswith("problems.yaml"):
        return (FIX / "problems_subset.yaml").read_text()
    m = re.search(r"forum/thread/(\d+)", url)
    if m:
        return (FIX / f"forum_{m.group(1)}.html").read_text()
    m = re.search(r"erdosproblems\.com/(\d+)$", url)
    if m:
        return (FIX / f"page_{m.group(1)}.html").read_text()
    raise AssertionError(f"unexpected network access in test: {url}")


@pytest.fixture
def fetch():
    return fake_fetch


@pytest.fixture
def catalog(fetch):
    from erdos_engine.catalog import Catalog
    return Catalog(fetch=fetch)
