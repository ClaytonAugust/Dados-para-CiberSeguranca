"""Build the gold graph in memory from the structured fields only (no text, no LLM).

IDs follow docs/proposta-schema-v2.md. Every semantic edge carries ``source="gold"``,
``doc_id``, ``chunk_id=""``, ``evidence="structured:<arquivo>.<campo>"`` and
``confidence=1.0``. One edge per (type, from, to): when several documents state the
same fact, ``doc_id``/``evidence`` keep the first and ``doc_ids`` lists all of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cti_graphrag.ingest.chunks import SOURCE, build_chunks, doc_id
from cti_graphrag.ingest.models import TechniqueRef
from cti_graphrag.ingest.normalize import (
    CompositeTool,
    SoftwareIndex,
    map_region,
    map_sector,
    parse_origin,
    technique_names,
    url_slug,
)
from cti_graphrag.ingest.read import Dataset
from cti_graphrag.ingest.vocab import COUNTRY_BY_CODE, SECTOR_NAMES


@dataclass
class Edge:
    type: str
    from_label: str
    from_id: str
    to_label: str
    to_id: str
    props: dict[str, Any]


@dataclass
class GoldGraph:
    nodes: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    edges: dict[tuple[str, str, str], Edge] = field(default_factory=dict)

    def add_node(self, label: str, node_id: str, **props: Any) -> None:
        """First values win; ``aliases`` are merged."""
        clean = {k: v for k, v in props.items() if v is not None}
        current = self.nodes.setdefault(label, {}).get(node_id)
        if current is None:
            self.nodes[label][node_id] = {"source": "gold", **clean}
            return
        for key, value in clean.items():
            if key == "aliases":
                seen = {a.casefold() for a in current.get("aliases", [])}
                merged = current.get("aliases", []) + [a for a in value if a.casefold() not in seen]
                current["aliases"] = merged
            else:
                current.setdefault(key, value)

    def add_edge(
        self,
        rel_type: str,
        from_node: tuple[str, str],
        to_node: tuple[str, str],
        doc_id: str,
        evidence: str,
        **extra: Any,
    ) -> None:
        key = (rel_type, from_node[1], to_node[1])
        edge = self.edges.get(key)
        if edge is None:
            props = {
                "source": "gold",
                "doc_id": doc_id,
                "doc_ids": [doc_id],
                "chunk_id": "",
                "evidence": evidence,
                "confidence": 1.0,
                **{k: v for k, v in extra.items() if v is not None},
            }
            self.edges[key] = Edge(rel_type, *from_node, *to_node, props)
        elif doc_id not in edge.props["doc_ids"]:
            edge.props["doc_ids"].append(doc_id)

    def add_structural_edge(
        self, rel_type: str, from_node: tuple[str, str], to_node: tuple[str, str], doc_id: str
    ) -> None:
        """PART_OF / MENTIONED_IN: no evidence or confidence, just provenance."""
        key = (rel_type, from_node[1], to_node[1])
        props = {"source": "gold", "doc_id": doc_id}
        self.edges.setdefault(key, Edge(rel_type, *from_node, *to_node, props))

    def has(self, label: str, node_id: str) -> bool:
        return node_id in self.nodes.get(label, {})


def tactic_id(name: str) -> str:
    return "tactic:" + name.casefold().replace(" ", "_")


def build_gold(dataset: Dataset, composites: dict[str, CompositeTool] | None = None) -> GoldGraph:
    gold = GoldGraph()
    index = SoftwareIndex(dataset.malware, composites)
    names = technique_names(dataset)
    page_ids = {p.mitre_attack_id for p in dataset.attack_techniques}
    first_seen_in: dict[str, tuple[str, str]] = {}  # technique id -> (doc_id, evidence)

    def document(file: str, item: Any) -> str:
        did = doc_id(file, item.slug)
        gold.add_node(
            "Document",
            did,
            title=item.title_raw or item.name,
            url=item.url,
            source=SOURCE,
            last_updated=item.last_updated,
        )
        return did

    def technique(ref_id: str, did: str, evidence: str, tactics: list[str]) -> tuple[str, str]:
        node = ("Technique", ref_id)
        gold.add_node(
            "Technique",
            ref_id,
            name=names.get(ref_id, ref_id),
            mitre_id=ref_id,
            is_subtechnique="." in ref_id,
            has_page=ref_id in page_ids,
        )
        first_seen_in.setdefault(ref_id, (did, evidence))
        for tactic in tactics:
            gold.add_node("Tactic", tactic_id(tactic), name=tactic)
            gold.add_edge("BELONGS_TO", node, ("Tactic", tactic_id(tactic)), did, evidence)
        return node

    def uses_techniques(owner: tuple[str, str], refs: list[TechniqueRef], did: str, file: str):
        evidence = f"structured:{file}.attack_techniques"
        for ref in refs:
            target = technique(ref.id, did, evidence, ref.tactics)
            gold.add_edge("USES", owner, target, did, evidence)

    def uses_tool(group: tuple[str, str], name: str, url: str | None, tool_type, did, evidence):
        for target in index.resolve(name, url):
            sid = target.match.software_id
            if target.match.method == "new":
                gold.add_node(
                    "Software",
                    sid,
                    name=target.name,
                    type_raw=tool_type,
                    aliases=list(target.aliases),
                    has_page=False,
                )
            gold.add_edge("USES", group, ("Software", sid), did, evidence)

    def targets(group: tuple[str, str], raws: list[str], did: str, file: str) -> list[str]:
        unmapped = []
        evidence = f"structured:{file}.target_sectors"
        for raw in raws:
            mapping = map_sector(raw)
            for slug in mapping.sectors:
                gold.add_node("Sector", f"sector:{slug}", name=SECTOR_NAMES[slug])
                gold.add_edge("TARGETS", group, ("Sector", f"sector:{slug}"), did, evidence)
            for code in mapping.countries:
                country(code)
                gold.add_edge("TARGETS", group, ("Country", f"country:{code}"), did, evidence)
            if not mapping.mapped:
                unmapped.append(raw)
        return unmapped

    def country(code: str) -> None:
        gold.add_node("Country", f"country:{code}", name=COUNTRY_BY_CODE[code], iso2=code)

    # Software pages first, so their properties win over tool references.
    for m in dataset.malware:
        did = document("malware", m)
        node = ("Software", f"software:{m.slug}")
        gold.add_node(
            *node,
            name=m.name,
            type_raw=m.type,
            aliases=m.aliases,
            platforms=m.platforms,
            first_seen=m.first_seen,
            has_page=True,
            title_raw=m.title_raw,
            description=m.summary,
            url=m.url,
        )
        gold.add_edge("DESCRIBES", ("Document", did), node, did, "structured:malware")

    for g in dataset.apt_groups:
        did = document("apt-groups", g)
        node = ("Group", f"group:{g.slug}")
        sectors_raw = targets(node, g.target_sectors, did, "apt-groups")
        regions_raw: list[str] = []
        for raw in g.target_regions:
            mapping = map_region(raw)
            for code in mapping.countries:
                country(code)
                gold.add_edge(
                    "TARGETS",
                    node,
                    ("Country", f"country:{code}"),
                    did,
                    "structured:apt-groups.target_regions",
                )
            regions_raw += list(mapping.unmapped)
        origin = parse_origin(g.suspected_origin)
        for code in origin.countries:
            country(code)
            gold.add_edge(
                "ASSOCIATED_WITH",
                node,
                ("Country", f"country:{code}"),
                did,
                "structured:apt-groups.suspected_origin",
                attribution=origin.attribution,
            )
        gold.add_node(
            *node,
            name=g.name,
            kind="apt",
            aliases=g.aliases,
            description=g.summary,
            status=g.status,
            motivation=g.motivation,
            attributed_by=g.attributed_by,
            mitre_id=g.mitre_attack_id,
            sectors_raw=sectors_raw,
            regions_raw=regions_raw,
            origin_raw=origin.raw,
            title_raw=g.title_raw,
            url=g.url,
        )
        gold.add_edge("DESCRIBES", ("Document", did), node, did, "structured:apt-groups")
        for tool in g.tools:
            uses_tool(node, tool.name, None, tool.type, did, "structured:apt-groups.tools")
        uses_techniques(node, g.attack_techniques, did, "apt-groups")

    for g in dataset.ransomware_groups:
        did = document("ransomware-groups", g)
        node = ("Group", f"group:{g.slug}")
        sectors_raw = targets(node, g.target_sectors, did, "ransomware-groups")
        gold.add_node(
            *node,
            name=g.name,
            kind="ransomware",
            aliases=g.aliases,
            description=g.summary,
            status=g.status,
            first_seen=g.first_seen,
            model=g.model,
            extortion=g.extortion,
            sectors_raw=sectors_raw,
            title_raw=g.title_raw,
            url=g.url,
        )
        gold.add_edge("DESCRIBES", ("Document", did), node, did, "structured:ransomware-groups")
        for m in g.malware:
            uses_tool(node, m.name, m.url, None, did, "structured:ransomware-groups.malware")

    for m in dataset.malware:
        did = doc_id("malware", m.slug)
        node = ("Software", f"software:{m.slug}")
        for ref in m.used_by:
            group = ("Group", f"group:{url_slug(ref.url)}")
            gold.add_edge("USES", group, node, did, "structured:malware.used_by")
        uses_techniques(node, m.attack_techniques, did, "malware")

    for page in dataset.attack_techniques:
        did = document("attack-techniques", page)
        node = technique(
            page.mitre_attack_id, did, "structured:attack-techniques.tactic", page.tactics
        )
        gold.add_node(*node, description=page.summary, title_raw=page.title_raw, url=page.url)
        gold.add_edge("DESCRIBES", ("Document", did), node, did, "structured:attack-techniques")

    # Sub-technique -> parent, derived from the ATT&CK ID (T1592.002 -> T1592).
    for sub_id in [t for t in list(gold.nodes.get("Technique", {})) if "." in t]:
        parent_id = sub_id.split(".", 1)[0]
        if not gold.has("Technique", parent_id):
            sub_name = gold.nodes["Technique"][sub_id]["name"]
            gold.add_node(
                "Technique",
                parent_id,
                name=sub_name.split(":", 1)[0].strip() if ":" in sub_name else parent_id,
                mitre_id=parent_id,
                is_subtechnique=False,
                has_page=parent_id in page_ids,
                derived_from_subtechnique=True,
            )
        did, evidence = first_seen_in[sub_id]
        gold.add_edge(
            "SUBTECHNIQUE_OF", ("Technique", sub_id), ("Technique", parent_id), did, evidence
        )

    # Derived parents have no tactic in any source: they get the union of their
    # sub-techniques' tactics, marked derived=true (provenance copied from the sub).
    techniques = gold.nodes.get("Technique", {})
    for (rel_type, sub_id, tactic), edge in list(gold.edges.items()):
        if rel_type != "BELONGS_TO" or "." not in sub_id:
            continue
        parent_id = sub_id.split(".", 1)[0]
        if techniques.get(parent_id, {}).get("derived_from_subtechnique"):
            gold.add_edge(
                "BELONGS_TO",
                ("Technique", parent_id),
                ("Tactic", tactic),
                edge.props["doc_id"],
                edge.props["evidence"],
                derived=True,
            )

    # Chunks: PART_OF to their Document; MENTIONED_IN only from the document's own
    # subject (no name search in the text, which would be extraction, not gold).
    for chunk in build_chunks(dataset):
        node = ("Chunk", chunk.id)
        gold.add_node(*node, text=chunk.text, doc_id=chunk.doc_id, n=chunk.n)
        gold.add_structural_edge("PART_OF", node, ("Document", chunk.doc_id), chunk.doc_id)
        gold.add_structural_edge(
            "MENTIONED_IN", (chunk.subject_label, chunk.subject_id), node, chunk.doc_id
        )

    for label in ("Group", "Software"):
        for props in gold.nodes.get(label, {}).values():
            props["aliases_text"] = " | ".join(props.get("aliases", []))
    return gold
