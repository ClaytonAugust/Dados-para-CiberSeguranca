import pytest

from cti_graphrag.config import REQUIRED_VARS, ConfigError, load_settings

VALID = {
    "FALKORDB_HOST": "127.0.0.1",
    "FALKORDB_PORT": "6379",
    "GRAPH_NAME": "cti_gold",
    "LLM_MODEL": "test/model",
    "LLM_API_KEY": "secret-key",
    "EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
    "EMBEDDING_DIM": "384",
    "PROMPT_VERSION": "v1",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in REQUIRED_VARS:
        monkeypatch.delenv(name, raising=False)


def write_env(tmp_path, values):
    path = tmp_path / ".env"
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()), encoding="utf-8")
    return path


def test_loads_all_values_from_file(tmp_path):
    settings = load_settings(write_env(tmp_path, VALID))
    assert settings.falkordb_port == 6379
    assert settings.embedding_dim == 384
    assert settings.graph_name == "cti_gold"


def test_reports_every_missing_variable(tmp_path):
    values = {k: v for k, v in VALID.items() if k not in ("LLM_API_KEY", "PROMPT_VERSION")}
    with pytest.raises(ConfigError) as exc:
        load_settings(write_env(tmp_path, values))
    assert "LLM_API_KEY" in str(exc.value)
    assert "PROMPT_VERSION" in str(exc.value)


def test_empty_value_counts_as_missing(tmp_path):
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        load_settings(write_env(tmp_path, {**VALID, "LLM_API_KEY": "  "}))


def test_missing_file_reports_all_variables(tmp_path):
    with pytest.raises(ConfigError) as exc:
        load_settings(tmp_path / "does-not-exist.env")
    assert all(name in str(exc.value) for name in REQUIRED_VARS)


@pytest.mark.parametrize("name,bad", [("FALKORDB_PORT", "abc"), ("EMBEDDING_DIM", "0")])
def test_invalid_integers(tmp_path, name, bad):
    with pytest.raises(ConfigError, match=name):
        load_settings(write_env(tmp_path, {**VALID, name: bad}))


def test_process_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPH_NAME", "cti_extracted")
    assert load_settings(write_env(tmp_path, VALID)).graph_name == "cti_extracted"


def test_repr_hides_api_key(tmp_path):
    assert "secret-key" not in repr(load_settings(write_env(tmp_path, VALID)))
