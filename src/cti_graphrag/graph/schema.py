"""Read ``schema/schema.yaml``: the only source of labels and relationships."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from cti_graphrag.config import PROJECT_ROOT

SCHEMA_PATH = PROJECT_ROOT / "schema" / "schema.yaml"
_LABEL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_REL_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class SchemaError(ValueError):
    """Raised when schema.yaml is missing or malformed."""


@dataclass(frozen=True)
class GraphSchema:
    version: str
    graphs: dict[str, str]
    labels: frozenset[str]
    relationships: dict[str, frozenset[tuple[str, str]]]

    def allows_label(self, label: str) -> bool:
        return label in self.labels

    def allows_edge(self, rel_type: str, from_label: str, to_label: str) -> bool:
        return (from_label, to_label) in self.relationships.get(rel_type, frozenset())


def load_schema(path: Path = SCHEMA_PATH) -> GraphSchema:
    """Labels and relationships, skipping anything with ``enabled: false``."""
    if not path.is_file():
        raise SchemaError(f"Schema não encontrado: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    labels = {
        name
        for name, spec in (data.get("labels") or {}).items()
        if (spec or {}).get("enabled", True)
    }
    relationships: dict[str, frozenset[tuple[str, str]]] = {}
    for name, spec in (data.get("relationships") or {}).items():
        spec = spec or {}
        if not spec.get("enabled", True):
            continue
        endpoints = {
            (e["from"], e["to"])
            for e in spec.get("allowed_endpoints", [])
            if e["from"] in labels and e["to"] in labels
        }
        if endpoints:
            relationships[name] = frozenset(endpoints)
    bad = [x for x in labels if not _LABEL_RE.match(x)] + [
        x for x in relationships if not _REL_RE.match(x)
    ]
    if bad:
        raise SchemaError(f"Nomes fora do padrão no schema: {bad}")
    return GraphSchema(
        version=str(data.get("schema_version", "")),
        graphs=dict(data.get("graphs") or {}),
        labels=frozenset(labels),
        relationships=relationships,
    )
