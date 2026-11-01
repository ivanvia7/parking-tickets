import subprocess
from datetime import date

import pytest


def test_installed_script_prints_version():
    out = subprocess.run(
        ["parking-tickets", "--version"], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip()


def test_bad_input_fails_before_any_download(run_cli):
    base = ["fetch", "--since", "2025-06-03", "--until", "2025-06-03"]
    code, _, err = run_cli(*base, "--city", "atlantis")
    assert code == 2 and "unknown city atlantis" in err
    code, _, err = run_cli(*base, "--city", "la", "--out", "t.xlsx")
    assert code == 2 and "--out must end with" in err


def test_out_onto_cache_is_refused(run_cli, tmp_path):
    cache = str(tmp_path / "c.db")
    base = ["fetch", "--since", "2025-06-03", "--until", "2025-06-03", "--city", "la"]
    code, _, err = run_cli(*base, "--cache", cache, "--out", cache)
    assert code == 2 and "cache file" in err


def test_out_into_missing_folder_fails_before_download(run_cli, tmp_path):
    code, _, err = run_cli(
        "fetch", "--city", "la", "--since", "2025-06-03", "--until", "2025-06-03",
        "--cache", str(tmp_path / "c.db"), "--out", str(tmp_path / "nope" / "t.csv"),
    )  # fmt: skip
    assert code == 2 and "does not exist" in err


def test_portal_errors_become_one_line(run_cli, monkeypatch):
    from parking_tickets import cli

    def broken(*args):
        raise RuntimeError("nyc 2025-06-03: ReadTimeout from https://x after 3 tries")

    monkeypatch.setattr(cli.api, "fetch", broken)
    code, _, _ = run_cli(
        "fetch", "--city", "nyc", "--since", "2025-06-03", "--until", "2025-06-03"
    )
    assert code == "error: nyc 2025-06-03: ReadTimeout from https://x after 3 tries"


def test_code_bugs_keep_their_traceback(monkeypatch, tmp_path):
    from parking_tickets import api, cache

    def buggy(*args):
        raise KeyError("date_field")

    monkeypatch.setattr(api, "fetch_day", buggy)
    day = date(2025, 6, 3)
    with pytest.raises(KeyError):
        api.fetch(cache.open_cache(tmp_path / "c.db"), "la", day, day)
