"""Cross-file normalization of the Brandefense dataset (no database access).

Run ``python -m cti_graphrag.ingest.normalize`` for the counts of mapped and
unmapped values; it also writes ``data/processed/unmapped_sectors.csv``.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from cti_graphrag.config import PROJECT_ROOT
from cti_graphrag.ingest.models import Malware
from cti_graphrag.ingest.read import Dataset, load_dataset
from cti_graphrag.ingest.vocab import (
    ABBREVIATION_RE,
    COUNTRY_ABBREVIATIONS,
    COUNTRY_BY_LOWER,
    COUNTRY_RE,
    SECTOR_RES,
)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CURATED_DIR = PROJECT_ROOT / "data" / "curated"
_NO_ORIGIN = ("not stated", "not attributed")
_LIST_SEPARATOR = re.compile(r",\s*|\s+and\s+")
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)")
_SOURCE_CLAUSE = re.compile(r",?\s+per\s+.*$", re.IGNORECASE)


# --- techniques ------------------------------------------------------------------
def technique_names(dataset: Dataset) -> dict[str, str]:
    """ATT&CK ID -> name.

    The name from the ``attack_techniques`` lists of groups and malware wins (it
    is the ATT&CK name, e.g. "Server Software Component: Web Shell"); the page in
    attack-techniques.json is used only for IDs no list mentions.
    """
    names: dict[str, str] = {}
    for item in [*dataset.apt_groups, *dataset.malware]:
        for ref in item.attack_techniques:
            if ref.name and ref.id not in names:
                names[ref.id] = ref.name
    for page in dataset.attack_techniques:
        names.setdefault(page.mitre_attack_id, page.name)
    return names


# --- countries --------------------------------------------------------------------
def find_countries(text: str | None) -> list[str]:
    """ISO alpha-2 codes of the country names in ``text``, in order, no repeats."""
    if not text:
        return []
    found: list[tuple[int, str]] = [
        (m.start(), COUNTRY_BY_LOWER[m.group(1).casefold()]) for m in COUNTRY_RE.finditer(text)
    ]
    found += [
        (m.start(), COUNTRY_ABBREVIATIONS[m.group(1)]) for m in ABBREVIATION_RE.finditer(text)
    ]
    codes: list[str] = []
    for _, code in sorted(found):
        if code not in codes:
            codes.append(code)
    return codes


@dataclass(frozen=True)
class Origin:
    countries: tuple[str, ...]
    attribution: str | None  # "suspected" | "attributed" | None (no edge)
    raw: str | None


def parse_origin(raw: str | None) -> Origin:
    """``suspected_origin`` -> ASSOCIATED_WITH countries and their ``attribution``.

    Empty, "Not stated..." and "Not attributed to a state" give no edge. A trailing
    source clause (", per the US Cyber Safety Review Board") is not an origin.
    """
    if not raw:
        return Origin((), None, None)
    if raw.casefold().startswith(_NO_ORIGIN):
        return Origin((), None, raw)
    countries = tuple(find_countries(_SOURCE_CLAUSE.sub("", raw)))
    if not countries:
        return Origin((), None, raw)
    attribution = "suspected" if "(suspected)" in raw.casefold() else "attributed"
    return Origin(countries, attribution, raw)


# --- sectors and regions -----------------------------------------------------------
@dataclass(frozen=True)
class SectorMapping:
    sectors: tuple[str, ...]
    countries: tuple[str, ...]

    @property
    def mapped(self) -> bool:
        return bool(self.sectors or self.countries)


def map_sector(raw: str) -> SectorMapping:
    """Free-text sector -> slugs of the closed list, plus any country it names."""
    sectors = tuple(
        slug for slug, patterns in SECTOR_RES.items() if any(p.search(raw) for p in patterns)
    )
    return SectorMapping(sectors, tuple(find_countries(raw)))


@dataclass(frozen=True)
class RegionMapping:
    countries: tuple[str, ...]
    unmapped: tuple[str, ...]  # fragments that are not exactly one country (-> regions_raw)


def map_region(raw: str) -> RegionMapping:
    """``"Germany, Czechia and France"`` -> DE, CZ, FR; ``"Europe"`` stays raw.

    Each list item becomes a Country only if it is exactly a country name.
    """
    countries: list[str] = []
    unmapped: list[str] = []
    for fragment in _LIST_SEPARATOR.split(raw):
        fragment = fragment.strip()
        if not fragment:
            continue
        code = COUNTRY_BY_LOWER.get(_PARENTHETICAL.sub("", fragment).casefold())
        code = code or COUNTRY_ABBREVIATIONS.get(fragment)
        if code and code not in countries:
            countries.append(code)
        elif not code:
            unmapped.append(fragment)
    return RegionMapping(tuple(countries), tuple(unmapped))


# --- software -----------------------------------------------------------------------
def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")


def url_slug(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1] or None


@dataclass(frozen=True)
class SoftwareMatch:
    software_id: str
    method: str  # "url_slug" | "name" | "alias" | "name_slug" | "new"


@dataclass(frozen=True)
class CompositeTool:
    """A reviewed tool entry that names several tools or one tool with aliases."""

    action: str  # "split" | "alias" | "skip"
    items: tuple[tuple[str, tuple[str, ...]], ...]  # (name, aliases)


@dataclass(frozen=True)
class ToolTarget:
    match: SoftwareMatch
    name: str
    aliases: tuple[str, ...] = ()


_ITEM_ALIASES = re.compile(r"^(.*?)\s*\[(.*)\]$")


def load_composite_tools(path: Path | None = None) -> dict[str, CompositeTool]:
    """Read ``data/curated/composite_tools.csv`` (``original|action|result``), reviewed by hand."""
    path = path or CURATED_DIR / "composite_tools.csv"
    composites: dict[str, CompositeTool] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="|"):
            action = row["action"].strip()
            if action not in {"split", "alias", "skip"}:
                raise ValueError(f"Ação desconhecida em {path.name}: {action!r}")
            items = []
            for item in filter(None, (p.strip() for p in (row["result"] or "").split(";"))):
                found = _ITEM_ALIASES.match(item)
                if found:
                    aliases = tuple(a.strip() for a in found.group(2).split(",") if a.strip())
                    items.append((found.group(1).strip(), aliases))
                else:
                    items.append((item, ()))
            composites[row["original"].strip()] = CompositeTool(action, tuple(items))
    return composites


class SoftwareIndex:
    """Matches tool/malware references to malware.json before creating a new Software.

    Order: slug of the URL (when the reference has one), exact name, alias, and the
    slugified name against the malware slugs. Case is ignored. Entries listed in
    ``composites`` are split, aliased or skipped as reviewed in the curated file.
    """

    def __init__(
        self, malware: list[Malware], composites: dict[str, CompositeTool] | None = None
    ) -> None:
        self._composites = composites or {}
        self._slugs = {m.slug for m in malware}
        self._names = {m.name.casefold(): m.slug for m in malware}
        self._aliases: dict[str, str] = {}
        for m in malware:
            for alias in m.aliases:
                self._aliases.setdefault(alias.casefold(), m.slug)

    def match(self, name: str, url: str | None = None) -> SoftwareMatch:
        slug = url_slug(url)
        if slug in self._slugs:
            return SoftwareMatch(f"software:{slug}", "url_slug")
        key = name.strip().casefold()
        if key in self._names:
            return SoftwareMatch(f"software:{self._names[key]}", "name")
        if key in self._aliases:
            return SoftwareMatch(f"software:{self._aliases[key]}", "alias")
        if slugify(name) in self._slugs:
            return SoftwareMatch(f"software:{slugify(name)}", "name_slug")
        return SoftwareMatch(f"software:{slugify(name)}", "new")

    def resolve(self, name: str, url: str | None = None) -> list[ToolTarget]:
        """All Software a reference points to: [] if skipped, several if split."""
        composite = self._composites.get(name.strip())
        if composite is None:
            return [ToolTarget(self.match(name, url), name.strip())]
        return [ToolTarget(self.match(n), n, aliases) for n, aliases in composite.items]


# --- report -------------------------------------------------------------------------
def build_report(dataset: Dataset) -> dict:
    groups = [*dataset.apt_groups, *dataset.ransomware_groups]

    sector_refs = [(g.slug, raw) for g in groups for raw in g.target_sectors]
    sector_maps = {raw: map_sector(raw) for _, raw in sector_refs}
    unmapped_sectors: dict[str, list[str]] = defaultdict(list)
    for slug, raw in sector_refs:
        if not sector_maps[raw].mapped:
            unmapped_sectors[raw].append(slug)

    region_refs = [raw for g in dataset.apt_groups for raw in g.target_regions]
    region_maps = [map_region(raw) for raw in region_refs]

    origins = [parse_origin(g.suspected_origin) for g in dataset.apt_groups]

    composites = load_composite_tools()
    index = SoftwareIndex(dataset.malware, composites)
    tool_refs = [(t.name, None) for g in dataset.apt_groups for t in g.tools]
    tool_refs += [(m.name, m.url) for g in dataset.ransomware_groups for m in g.malware]
    matches = [t.match for name, url in tool_refs for t in index.resolve(name, url)]
    malware_ids = {f"software:{m.slug}" for m in dataset.malware}
    composite_refs = [name for name, _ in tool_refs if name.strip() in composites]

    return {
        "sectors": {
            "refs": len(sector_refs),
            "distinct": len(sector_maps),
            "with_sector": sum(sector_maps[r].sectors != () for _, r in sector_refs),
            "country_only": sum(
                not sector_maps[r].sectors and bool(sector_maps[r].countries)
                for _, r in sector_refs
            ),
            "unmapped_refs": sum(len(v) for v in unmapped_sectors.values()),
            "unmapped_distinct": len(unmapped_sectors),
            "slugs_used": len({s for m in sector_maps.values() for s in m.sectors}),
        },
        "unmapped_sectors": dict(unmapped_sectors),
        "regions": {
            "refs": len(region_refs),
            "fully_mapped": sum(not m.unmapped for m in region_maps),
            "partly_mapped": sum(bool(m.countries and m.unmapped) for m in region_maps),
            "unmapped": sum(not m.countries for m in region_maps),
            "countries": len({c for m in region_maps for c in m.countries}),
        },
        "origin": dict(Counter(o.attribution or "no_edge" for o in origins)),
        "origin_no_edge_raw": sorted({o.raw or "<vazio>" for o in origins if not o.attribution}),
        "tools": {
            "refs": len(tool_refs),
            "composite_refs": len(composite_refs),
            "skipped_refs": sum(composites[n.strip()].action == "skip" for n in composite_refs),
            "targets": len(matches),
            "by_method": dict(Counter(m.method for m in matches)),
            "malware_reached": len({m.software_id for m in matches} & malware_ids),
            "new_software_nodes": len({m.software_id for m in matches if m.method == "new"}),
        },
    }


def write_unmapped_sectors(unmapped: dict[str, list[str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["raw_value", "count", "groups"])
        for raw, slugs in sorted(unmapped.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            writer.writerow([raw, len(slugs), ";".join(sorted(set(slugs)))])


def write_sector_review(dataset: Dataset, path: Path) -> None:
    """Every sector spelling with its mapping, most sectors first (for manual review)."""
    counts = Counter(
        raw for g in [*dataset.apt_groups, *dataset.ransomware_groups] for raw in g.target_sectors
    )
    rows = [(raw, map_sector(raw), n) for raw, n in counts.items()]
    rows.sort(key=lambda r: (-len(r[1].sectors), -r[2], r[0].casefold()))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="|")
        writer.writerow(["grafia", "setores", "pais", "contagem"])
        for raw, mapping, n in rows:
            writer.writerow([raw, ";".join(mapping.sectors), ";".join(mapping.countries), n])


def main() -> None:
    dataset = load_dataset()
    report = build_report(dataset)
    write_unmapped_sectors(report.pop("unmapped_sectors"), PROCESSED_DIR / "unmapped_sectors.csv")
    write_sector_review(dataset, CURATED_DIR / "sector_mapping_review.csv")
    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
