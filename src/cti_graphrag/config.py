"""Project settings loaded from the .env file at the repository root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

REQUIRED_VARS = (
    "FALKORDB_HOST",
    "FALKORDB_PORT",
    "GRAPH_NAME",
    "LLM_MODEL",
    "LLM_API_KEY",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIM",
    "PROMPT_VERSION",
)


class ConfigError(RuntimeError):
    """Raised when the environment is missing or has invalid settings."""


@dataclass(frozen=True)
class Settings:
    falkordb_host: str
    falkordb_port: int
    graph_name: str
    llm_model: str
    llm_api_key: str
    embedding_model: str
    embedding_dim: int
    prompt_version: str

    def __repr__(self) -> str:  # never print the API key
        return (
            f"Settings(falkordb={self.falkordb_host}:{self.falkordb_port}, "
            f"graph={self.graph_name!r}, llm_model={self.llm_model!r}, "
            f"embedding_model={self.embedding_model!r}, "
            f"embedding_dim={self.embedding_dim}, "
            f"prompt_version={self.prompt_version!r})"
        )


def _positive_int(name: str, raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} deve ser um número inteiro, recebido: {raw!r}") from None
    if value <= 0:
        raise ConfigError(f"{name} deve ser maior que zero, recebido: {value}")
    return value


def load_settings(env_file: Path | str | None = None) -> Settings:
    """Read settings from the process environment, falling back to the .env file.

    Process environment variables take precedence over the file. Empty values
    count as missing. All missing variables are reported in a single error.
    """
    path = Path(env_file) if env_file is not None else DEFAULT_ENV_FILE
    file_values = dotenv_values(path) if path.is_file() else {}

    values: dict[str, str] = {}
    for name in REQUIRED_VARS:
        raw = os.environ.get(name, file_values.get(name))
        if raw is not None and raw.strip():
            values[name] = raw.strip()

    missing = [name for name in REQUIRED_VARS if name not in values]
    if missing:
        raise ConfigError(
            "Variáveis ausentes ou vazias no .env: "
            + ", ".join(missing)
            + f". Arquivo lido: {path}. Use o .env.example como modelo."
        )

    return Settings(
        falkordb_host=values["FALKORDB_HOST"],
        falkordb_port=_positive_int("FALKORDB_PORT", values["FALKORDB_PORT"]),
        graph_name=values["GRAPH_NAME"],
        llm_model=values["LLM_MODEL"],
        llm_api_key=values["LLM_API_KEY"],
        embedding_model=values["EMBEDDING_MODEL"],
        embedding_dim=_positive_int("EMBEDDING_DIM", values["EMBEDDING_DIM"]),
        prompt_version=values["PROMPT_VERSION"],
    )
