"""Local .env support: convenience only, and never overrides a real exported variable."""

from medikiosk_ocr.env import huggingface_token_configured, load_env


def test_reads_key_value_lines_and_reports_names_only(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\n\nHF_TOKEN="secret-value"\nexport OTHER=plain\nnot a pair\n')
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("OTHER", raising=False)

    applied = load_env(env)

    assert applied == ["HF_TOKEN", "OTHER"]          # names, not values
    assert "secret-value" not in " ".join(applied)
    import os
    assert os.environ["HF_TOKEN"] == "secret-value"  # quotes stripped
    assert os.environ["OTHER"] == "plain"            # "export " prefix ignored


def test_an_exported_variable_always_wins(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("HF_TOKEN=from-file\n")
    monkeypatch.setenv("HF_TOKEN", "from-environment")

    assert load_env(env) == []
    import os
    assert os.environ["HF_TOKEN"] == "from-environment"


def test_missing_env_file_is_fine(tmp_path):
    assert load_env(tmp_path / "does-not-exist") == []


def test_token_configured_is_a_boolean_not_the_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACEHUB_API_TOKEN", raising=False)
    assert huggingface_token_configured() is False
    monkeypatch.setenv("HF_TOKEN", "hf_exampletoken")
    assert huggingface_token_configured() is True
