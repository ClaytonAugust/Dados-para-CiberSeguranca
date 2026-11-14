"""Read and validate the raw Brandefense JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from cti_graphrag.config import PROJECT_ROOT
from cti_graphrag.ingest.models import AptGroup, AttackTechnique, Malware, RansomwareGroup

RAW_DIR = PROJECT_ROOT / "data" / "raw"

FILES: dict[str, type[BaseModel]] = {
    "apt-groups": AptGroup,
    "ransomware-groups": RansomwareGroup,
    "malware": Malware,
    "attack-techniques": AttackTechnique,
}


class DatasetError(ValueError):
    """Raised when a raw file is missing, malformed or inconsistent with its meta."""


@dataclass(frozen=True)
class Dataset:
    apt_groups: list[AptGroup]
    ransomware_groups: list[RansomwareGroup]
    malware: list[Malware]
    attack_techniques: list[AttackTechnique]

    def counts(self) -> dict[str, int]:
        return {
            "apt-groups": len(self.apt_groups),
            "ransomware-groups": len(self.ransomware_groups),
            "malware": len(self.malware),
            "attack-techniques": len(self.attack_techniques),
        }


def read_file(path: Path, model: type[BaseModel]) -> list[BaseModel]:
    if not path.is_file():
        raise DatasetError(f"Arquivo não encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise DatasetError(f"Formato inesperado (falta 'items'): {path.name}")
    items = [model.model_validate(item) for item in data["items"]]
    expected = data.get("meta", {}).get("count")
    if expected is not None and expected != len(items):
        raise DatasetError(f"{path.name}: meta.count={expected}, mas há {len(items)} itens")
    slugs = [item.slug for item in items]
    if len(slugs) != len(set(slugs)):
        raise DatasetError(f"{path.name}: slugs duplicados")
    return items


def load_dataset(raw_dir: Path = RAW_DIR) -> Dataset:
    loaded = {name: read_file(raw_dir / f"{name}.json", model) for name, model in FILES.items()}
    return Dataset(
        apt_groups=loaded["apt-groups"],
        ransomware_groups=loaded["ransomware-groups"],
        malware=loaded["malware"],
        attack_techniques=loaded["attack-techniques"],
    )
