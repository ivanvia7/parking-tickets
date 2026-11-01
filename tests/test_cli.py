import subprocess


def test_version_prints():
    out = subprocess.run(
        ["parking-tickets", "--version"], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "0.1.0"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["parking-tickets", *args], capture_output=True, text=True, check=False
    )


def test_bad_input_fails_before_any_download():
    base = ["fetch", "--since", "2025-06-03", "--until", "2025-06-03"]
    city = run_cli(*base, "--city", "atlantis")
    out = run_cli(*base, "--city", "la", "--out", "t.xlsx")
    assert city.returncode == 2 and "unknown city atlantis" in city.stderr
    assert out.returncode == 2 and "--out must end with" in out.stderr
