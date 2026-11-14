"""Pydantic models for the four Brandefense JSON files.

Reading-level normalizations (applied while parsing, raw meaning preserved):
- aliases come as objects ``{name, source}`` (APT) or plain strings (ransomware,
  malware): both become a list of unique, non-empty strings;
- empty strings become ``None`` in optional text fields;
- combined tactics ("Persistence, Privilege Escalation") are split, and case is
  normalized to ATT&CK style ("Command And Control" -> "Command and Control");
- ``motivation`` comes as PHP-serialized arrays (``a:1:{i:0;s:9:"espionage";}``)
  or comma-separated text: both become a list of lowercase strings;
- article titles used as names ("Amadey Malware: How the Loader Works") are cut
  before the colon, without the "Malware"/"Ransomware"/"Threat Actor" suffix;
  the original goes to ``title_raw`` (groups and malware only).
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

_LOWERCASE_WORDS = {"and", "or", "of", "the", "to", "in", "for"}
_PHP_ARRAY = re.compile(r"^a:\d+:\{.*\}$", re.DOTALL)
# The declared length is ignored on purpose: the data has s:10:"espionage" (9 chars).
_PHP_STRING = re.compile(r's:\d+:"([^"]*)"')
_TITLE_SUFFIXES = ("Threat Actor", "Ransomware", "Malware")


def blank_to_none(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def normalize_aliases(value: Any) -> list[str]:
    """Accept strings or ``{"name": ...}`` objects; drop blanks and duplicates."""
    if value is None:
        return []
    names: list[str] = []
    for item in value:
        name = item.get("name") if isinstance(item, dict) else item
        name = blank_to_none(name) if isinstance(name, str) else None
        if name and name.casefold() not in {n.casefold() for n in names}:
            names.append(name)
    return names


def canonical_tactic(name: str) -> str:
    words = name.strip().split()
    return " ".join(
        w.lower() if i > 0 and w.lower() in _LOWERCASE_WORDS else w[:1].upper() + w[1:].lower()
        for i, w in enumerate(words)
    )


def split_tactics(value: Any) -> list[str]:
    """``"Stealth, Persistence"`` -> ``["Stealth", "Persistence"]`` (canonical case)."""
    if value is None:
        return []
    parts = value if isinstance(value, list) else str(value).split(",")
    tactics: list[str] = []
    for part in parts:
        if isinstance(part, str) and part.strip():
            tactic = canonical_tactic(part)
            if tactic not in tactics:
                tactics.append(tactic)
    return tactics


def parse_motivation(value: Any) -> list[str]:
    """PHP-serialized array or ``"espionage, financial"`` -> ``["espionage", "financial"]``."""
    if value is None:
        return []
    if isinstance(value, list):
        parts = value
    else:
        text = str(value).strip()
        parts = _PHP_STRING.findall(text) if _PHP_ARRAY.match(text) else text.split(",")
    motivations: list[str] = []
    for part in parts:
        word = part.strip().lower() if isinstance(part, str) else ""
        if word and word not in motivations:
            motivations.append(word)
    return motivations


def split_title(name: str) -> tuple[str, str | None]:
    """``"Nefilim Ransomware: Profile..."`` -> ``("Nefilim", original)``; no colon -> ``None``."""
    name = name.strip()
    if ":" not in name:
        return name, None
    head = name.split(":", 1)[0].strip()
    for suffix in _TITLE_SUFFIXES:
        if head.casefold().endswith(" " + suffix.casefold()):
            head = head[: -len(suffix)].strip()
            break
    return head, name


OptStr = Annotated[str | None, BeforeValidator(blank_to_none)]
Aliases = Annotated[list[str], BeforeValidator(normalize_aliases)]
Tactics = Annotated[list[str], BeforeValidator(split_tactics)]
Motivations = Annotated[list[str], BeforeValidator(parse_motivation)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Model):
    title: OptStr = None
    publisher: OptStr = None
    url: OptStr = None


class TechniqueRef(_Model):
    id: str
    name: OptStr = None
    tactics: Tactics = Field(default_factory=list, alias="tactic")

    @field_validator("id")
    @classmethod
    def _upper_id(cls, value: str) -> str:
        return value.strip().upper()


class ToolRef(_Model):
    name: str
    type: OptStr = None


class LinkRef(_Model):
    name: str
    url: OptStr = None


class _Item(_Model):
    name: str
    slug: str
    url: OptStr = None
    last_updated: OptStr = None
    summary: OptStr = None
    sources: list[Source] = Field(default_factory=list)


class _TitledItem(_Item):
    """Groups and malware: a page title used as name is cut, the original kept."""

    title_raw: OptStr = None

    @model_validator(mode="before")
    @classmethod
    def _split_title(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("name"), str) and "title_raw" not in data:
            name, raw = split_title(data["name"])
            if raw is not None:
                return {**data, "name": name, "title_raw": raw}
        return data


class AptGroup(_TitledItem):
    aliases: Aliases = Field(default_factory=list)
    status: OptStr = None
    motivation: Motivations = Field(default_factory=list)
    suspected_origin: OptStr = None
    attributed_by: OptStr = None
    mitre_attack_id: OptStr = None
    target_sectors: list[str] = Field(default_factory=list)
    target_regions: list[str] = Field(default_factory=list)
    attack_techniques: list[TechniqueRef] = Field(default_factory=list)
    tools: list[ToolRef] = Field(default_factory=list)


class RansomwareGroup(_TitledItem):
    aliases: Aliases = Field(default_factory=list)
    status: OptStr = None
    first_seen: OptStr = None
    model: OptStr = None
    extortion: OptStr = None
    target_sectors: list[str] = Field(default_factory=list)
    malware: list[LinkRef] = Field(default_factory=list)


class Malware(_TitledItem):
    aliases: Aliases = Field(default_factory=list)
    type: OptStr = None
    platforms: list[str] = Field(default_factory=list)
    first_seen: OptStr = None
    used_by: list[LinkRef] = Field(default_factory=list)
    attack_techniques: list[TechniqueRef] = Field(default_factory=list)


class AttackTechnique(_Item):
    mitre_attack_id: str
    tactics: Tactics = Field(default_factory=list, alias="tactic")
