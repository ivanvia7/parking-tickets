import subprocess


def test_version_prints():
    out = subprocess.run(
        ["parking-tickets", "--version"], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "0.1.0"
