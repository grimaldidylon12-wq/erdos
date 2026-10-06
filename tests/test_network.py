"""Live-source tests (deselected by default; run with -m network)."""
import pytest

pytestmark = pytest.mark.network


def test_live_database_and_forum(monkeypatch, tmp_path):
    from erdos_engine import catalog as C
    from erdos_engine.literature import build_dossier
    cat = C.Catalog(refresh=True)
    assert len(cat.problems) > 1000
    assert cat.get(458).number == 458
    d = build_dossier(458, cat)
    assert d.comments and d.statement.startswith("Let")
