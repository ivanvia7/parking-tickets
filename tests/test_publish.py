import importlib.util
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location(
    "publish", ROOT / "scripts" / "publish.py"
)
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)

FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "la.json").read_text())
URL = "https://data.lacity.org/resource/4f5p-udkv.json"


def test_year_spans_clip_first_and_last_year():
    spans = publish.year_spans(date(2013, 7, 1), date(2015, 3, 4))
    assert spans == [
        ("2013-07-01", "2013-12-31"),
        ("2014-01-01", "2014-12-31"),
        ("2015-01-01", "2015-03-04"),
    ]
    assert publish.year_spans(date(2015, 3, 4), date(2015, 3, 4)) == [
        ("2015-03-04", "2015-03-04")
    ]


def test_plan_respects_first_and_last_day():
    jobs = publish.plan()
    phl = [j for j in jobs if j["city"] == "philadelphia"]
    assert phl[0]["since"] == "2012-01-01" and phl[-1]["until"] == "2017-12-31"
    nyc = [j for j in jobs if j["city"] == "nyc"]
    assert nyc[0]["since"] == "2013-07-01"
    assert all(j["since"] <= j["until"] for j in jobs)


@respx.mock
def test_build_and_manifest_rows_match(tmp_path, monkeypatch):
    monkeypatch.setattr("parking_tickets.portals.http.MIN_GAP_SECONDS", 0)
    respx.get(URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    publish.build("la", "2025-06-03", "2025-06-03", tmp_path)
    body = json.loads(publish.manifest(tmp_path).read_text())
    assert {f["file"] for f in body["files"]} == {"la-2025.parquet", "la-2025.csv.gz"}
    assert all(
        f["rows"] == len(FIXTURE) and len(f["sha256"]) == 64 for f in body["files"]
    )
    assert not (tmp_path / "la-2025.csv").exists()


def test_manifest_of_empty_or_missing_dir_fails(tmp_path):
    with pytest.raises(SystemExit, match=r"no \.parquet"):
        publish.manifest(tmp_path)
    with pytest.raises(FileNotFoundError):
        publish.manifest(tmp_path / "none")


def test_manifest_refuses_a_file_too_big_for_github(tmp_path, monkeypatch):
    (tmp_path / "la-2025.parquet").write_bytes(b"x" * 10)
    monkeypatch.setattr(publish, "MAX_FILE_BYTES", 10)
    with pytest.raises(SystemExit, match="under 2 GiB"):
        publish.manifest(tmp_path)


def test_build_of_unknown_city_fails(tmp_path):
    with pytest.raises(ValueError, match="unknown city"):
        publish.build("atlantis", "2025-06-03", "2025-06-03", tmp_path)
