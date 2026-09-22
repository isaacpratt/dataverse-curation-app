"""Secret scan (format.secrets) via hush-scan."""

from pathlib import Path

from engine.checks.secret_check import SecretCheck


def _run(tmp_path: Path, content: str, name: str = "sample.py"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return SecretCheck().run([p])


def test_clean_file_passes(tmp_path):
    results = _run(tmp_path, "x = 1\nprint('hello')\n")
    assert len(results) == 1
    r = results[0]
    assert r.check_id == "format.secrets"
    assert r.passed is True
    assert r.level == "info"
    assert r.details["count"] == 0


def test_github_pat_detected(tmp_path):
    secret = "ghp_" + "a" * 36
    results = _run(tmp_path, f'token = "{secret}"\n')
    r = results[0]
    assert r.passed is False
    assert r.level == "warning"
    assert r.details["count"] >= 1
    secrets = [f["secret"] for f in r.details["findings"]]
    assert any(secret in s or "ghp_" in s for s in secrets)


def test_aws_key_detected(tmp_path):
    results = _run(tmp_path, 'aws_key = "AKIAIOSFODNN7EXAMPLE"\n')
    r = results[0]
    assert r.passed is False


def test_private_key_detected(tmp_path):
    results = _run(
        tmp_path,
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQ...\n-----END RSA PRIVATE KEY-----\n",
        name="key.pem.txt",
    )
    assert results[0].check_id == "format.secrets"
    assert results[0].passed is False


def test_md_config_extensions(tmp_path):
    for name in ("README.md", "settings.yml", "app.env", "notes.log"):
        results = _run(tmp_path, "api_key = 1\n", name=name)
        assert results[0].check_id == "format.secrets"


def test_truncation_message_when_over_cap(tmp_path, monkeypatch):
    import engine.checks.secret_check as sc

    monkeypatch.setattr(sc, "_MAX_LISTED", 2)
    lines = [
        f"key{i} = '{i}AbCdEfGhIjKlMnOpQrStUvWxYz0123456789'" for i in range(10)
    ]
    results = _run(tmp_path, "\n".join(lines) + "\n")
    r = results[0]
    assert r.passed is False
    assert r.details["count"] > 2
    assert r.details["findings_listed"] == 2
    assert len(r.details["findings"]) == 2
    assert "showing first 2 of" in r.message
