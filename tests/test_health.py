import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "health.sh"
# Stands in for `uv run parking-tickets ...`: two cities, the one in BROKEN fails.
FAKE_UV = """#!/usr/bin/env bash
if [ "$3" = cities ]; then printf 'la\\nsf\\n'; exit 0; fi
if [ "$4" = "$BROKEN" ]; then echo "FAIL $4: column gone"; exit 1; fi
echo "ok $4"
"""


def run_health(tmp_path: Path, broken: str) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uv").write_text(FAKE_UV)
    (bin_dir / "uv").chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "BROKEN": broken}
    return subprocess.run(
        [str(SCRIPT), str(tmp_path / "out")],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_broken_city_fails_and_gets_its_own_file(tmp_path):
    result = run_health(tmp_path, "sf")
    assert result.returncode == 1 and "broken cities: sf" in result.stderr
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["sf.txt"]
    assert "column gone" in (tmp_path / "out" / "sf.txt").read_text()


def test_all_cities_ok_exits_zero_with_no_files(tmp_path):
    result = run_health(tmp_path, "none")
    assert result.returncode == 0 and "ok la" in result.stdout
    assert list((tmp_path / "out").iterdir()) == []
