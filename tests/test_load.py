import json
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest
import respx

from parking_tickets import api, load

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "la.json").read_text())
URL = "https://data.lacity.org/resource/4f5p-udkv.json"


@respx.mock
def test_load_returns_dataframe_of_the_day(tmp_path):
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    df = load(
        "la", since="2025-06-03", until="2025-06-03", cache_path=tmp_path / "c.db"
    )
    assert df.shape == (len(FIXTURE), 11)
    assert df["fine_usd"].dtype == "float64"
    assert set(df["city"]) == {"la"}


@respx.mock
def test_load_warns_on_skipped_rows(tmp_path):
    bad = {**FIXTURE[0], "ticket_number": ""}
    respx.get(URL).mock(return_value=httpx.Response(200, json=[*FIXTURE, bad]))
    with pytest.warns(UserWarning, match="1 unreadable rows skipped"):
        df = load("la", "2025-06-03", "2025-06-03", cache_path=tmp_path / "c.db")
    assert len(df) == len(FIXTURE)


def test_load_without_pandas_gives_install_hint(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "pandas", None)
    with pytest.raises(ImportError, match=r"parking-tickets\[pandas\]"):
        load("la", "2025-06-03", "2025-06-03", cache_path=tmp_path / "c.db")


def test_load_rejects_reversed_dates_and_unknown_city(tmp_path):
    path = tmp_path / "c.db"
    with pytest.raises(ValueError, match="after until"):
        load("la", "2025-06-04", "2025-06-03", cache_path=path)
    with pytest.raises(ValueError, match="unknown city"):
        load("atlantis", "2025-06-03", "2025-06-03", cache_path=path)
    with pytest.raises(ValueError):
        load("la", "June 3", "2025-06-03", cache_path=path)


@respx.mock
def test_load_closes_its_cache(tmp_path, monkeypatch):
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    opened: list[sqlite3.Connection] = []
    real_open = api.cache.open_cache
    monkeypatch.setattr(
        api.cache,
        "open_cache",
        lambda path: opened.append(real_open(path)) or opened[-1],
    )
    api.load("la", "2025-06-03", "2025-06-03", cache_path=tmp_path / "c.db")
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")
