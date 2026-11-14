"""Sanity check of cti_gold against counts taken from the raw JSON.

The expected values come from the JSON themselves (records, references and
distinct pairs), computed here without the loader's code, so the check is not the
loader checking itself. Two kinds of check:

- exact: must match (records, technique pairs, chunks...). Any difference fails;
- explained: a raw reference count that the normalization changes on purpose
  (composite tools, mapping, dedup). The difference is shown with its reason and
  never "fixed" to match.

    python -m cti_graphrag.ingest.sanity      # exit code 1 if an exact check fails
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from falkordb import Graph

from cti_graphrag.graph.client import get_graph, run_query
from cti_graphrag.graph.schema import load_schema
from cti_graphrag.ingest.read import Dataset, load_dataset


@dataclass(frozen=True)
class Check:
    name: str
    expected: int
    actual: int
    exact: bool
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.expected == self.actual

    @property
    def status(self) -> str:
        if self.ok:
            return "OK"
        return "FALHA" if self.exact else "DIFERENTE (explicado)"


def expected_counts(d: Dataset) -> dict[str, int]:
    """Everything here is read straight from the JSON fields."""
    apt_tech = {(g.slug, r.id) for g in d.apt_groups for r in g.attack_techniques}
    mal_tech = {(m.slug, r.id) for m in d.malware for r in m.attack_techniques}
    ref_ids = {r.id for g in [*d.apt_groups, *d.malware] for r in g.attack_techniques}
    page_ids = {p.mitre_attack_id for p in d.attack_techniques}
    tech_ids = ref_ids | page_ids
    subs = {t for t in tech_ids if "." in t}
    missing_parents = {t.split(".", 1)[0] for t in subs} - tech_ids
    tactic_pairs = {
        (r.id, tac)
        for g in [*d.apt_groups, *d.malware]
        for r in g.attack_techniques
        for tac in r.tactics
    } | {(p.mitre_attack_id, tac) for p in d.attack_techniques for tac in p.tactics}
    records = len(d.apt_groups) + len(d.ransomware_groups) + len(d.malware)
    records += len(d.attack_techniques)
    return {
        "records": records,
        "groups": len(d.apt_groups) + len(d.ransomware_groups),
        "apt": len(d.apt_groups),
        "ransomware": len(d.ransomware_groups),
        "malware_pages": len(d.malware),
        "technique_pages": len(page_ids),
        "techniques": len(tech_ids) + len(missing_parents),
        "derived_parents": len(missing_parents),
        "subtechniques": len(subs),
        "tactics": len({tac for _, tac in tactic_pairs}),
        "tactic_pairs": len(tactic_pairs),
        "group_technique_pairs": len(apt_tech),
        "software_technique_pairs": len(mal_tech),
        "group_software_refs": sum(len(g.tools) for g in d.apt_groups)
        + sum(len(g.malware) for g in d.ransomware_groups)
        + sum(len(m.used_by) for m in d.malware),
        "origins": sum(bool(g.suspected_origin) for g in d.apt_groups),
        "sector_refs": sum(len(g.target_sectors) for g in [*d.apt_groups, *d.ransomware_groups]),
        "region_refs": sum(len(g.target_regions) for g in d.apt_groups),
    }


def _count(graph: Graph, cypher: str) -> int:
    return int(run_query(cypher, graph=graph, read_only=True).result_set[0][0])


def run_checks(graph: Graph, dataset: Dataset) -> list[Check]:
    schema = load_schema()
    used = {"Group", "Software", "Technique", "Tactic", "Document", "Chunk"}
    missing = used - schema.labels
    if missing:
        raise RuntimeError(f"Labels usados na checagem não estão no schema: {missing}")
    e = expected_counts(dataset)
    c = lambda q: _count(graph, q)  # noqa: E731
    gold_edge = (
        "MATCH ()-[r:USES|TARGETS|ASSOCIATED_WITH|BELONGS_TO|SUBTECHNIQUE_OF]->() "
        "WHERE r.source <> 'gold' OR r.chunk_id <> '' OR r.confidence <> 1.0 "
        "OR NOT r.evidence STARTS WITH 'structured:' OR r.doc_id IS NULL RETURN count(r)"
    )
    return [
        Check("Group", e["groups"], c("MATCH (n:Group) RETURN count(n)"), True),
        Check("Group kind=apt", e["apt"], c("MATCH (n:Group {kind:'apt'}) RETURN count(n)"), True),
        Check(
            "Group kind=ransomware",
            e["ransomware"],
            c("MATCH (n:Group {kind:'ransomware'}) RETURN count(n)"),
            True,
        ),
        Check(
            "Software has_page=true",
            e["malware_pages"],
            c("MATCH (n:Software {has_page:true}) RETURN count(n)"),
            True,
        ),
        Check(
            "Technique",
            e["techniques"],
            c("MATCH (n:Technique) RETURN count(n)"),
            True,
            f"inclui {e['derived_parents']} técnicas-pai derivadas",
        ),
        Check(
            "Technique has_page=true",
            e["technique_pages"],
            c("MATCH (n:Technique {has_page:true}) RETURN count(n)"),
            True,
        ),
        Check("Tactic", e["tactics"], c("MATCH (n:Tactic) RETURN count(n)"), True),
        Check("Document", e["records"], c("MATCH (n:Document) RETURN count(n)"), True),
        Check("Chunk", e["records"], c("MATCH (n:Chunk) RETURN count(n)"), True),
        Check("PART_OF", e["records"], c("MATCH ()-[r:PART_OF]->() RETURN count(r)"), True),
        Check(
            "MENTIONED_IN", e["records"], c("MATCH ()-[r:MENTIONED_IN]->() RETURN count(r)"), True
        ),
        Check(
            "USES Group->Technique",
            e["group_technique_pairs"],
            c("MATCH (:Group)-[r:USES]->(:Technique) RETURN count(r)"),
            True,
        ),
        Check(
            "USES Software->Technique",
            e["software_technique_pairs"],
            c("MATCH (:Software)-[r:USES]->(:Technique) RETURN count(r)"),
            True,
        ),
        Check(
            "USES Group->Software",
            e["group_software_refs"],
            c("MATCH (:Group)-[r:USES]->(:Software) RETURN count(r)"),
            False,
            "esperado = referências brutas (tools + malware + used_by); "
            "tools compostas são divididas ou puladas e o mesmo par de 2 fontes vira 1 aresta",
        ),
        Check(
            "BELONGS_TO (da fonte)",
            e["tactic_pairs"],
            c("MATCH ()-[r:BELONGS_TO]->() WHERE r.derived IS NULL RETURN count(r)"),
            True,
        ),
        Check(
            "SUBTECHNIQUE_OF",
            e["subtechniques"],
            c("MATCH ()-[r:SUBTECHNIQUE_OF]->() RETURN count(r)"),
            True,
        ),
        Check(
            "ASSOCIATED_WITH",
            e["origins"],
            c("MATCH ()-[r:ASSOCIATED_WITH]->() RETURN count(r)"),
            False,
            "esperado = APT com origem preenchida; 'Not stated/Not attributed' não gera aresta "
            "e uma origem pode citar 2 países",
        ),
        Check(
            "TARGETS",
            e["sector_refs"] + e["region_refs"],
            c("MATCH ()-[r:TARGETS]->() RETURN count(r)"),
            False,
            "esperado = referências brutas de setor + região; valores sem mapeamento não geram "
            "aresta, um valor pode gerar vários setores/países e pares repetidos viram 1",
        ),
        Check("Arestas gold com propriedades fora do padrão", 0, c(gold_edge), True),
    ]


def main() -> None:
    schema = load_schema()
    graph = get_graph(schema.graphs.get("gold", "cti_gold"))
    checks = run_checks(graph, load_dataset())
    width = max(len(ch.name) for ch in checks)
    print(f"{'checagem':<{width}}  esperado  no banco  status")
    for ch in checks:
        print(f"{ch.name:<{width}}  {ch.expected:>8}  {ch.actual:>8}  {ch.status}")
        if ch.note and (not ch.ok or ch.exact):
            print(f"{'':<{width}}    -> {ch.note}")
    failures = [ch for ch in checks if ch.exact and not ch.ok]
    print(
        f"\nexatas: {sum(ch.exact for ch in checks) - len(failures)} OK, {len(failures)} falha(s)"
    )
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
