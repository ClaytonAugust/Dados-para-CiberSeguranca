"""Idempotent load of the gold graph into FalkorDB.

Only labels and relationships present (and enabled) in ``schema/schema.yaml`` are
written; anything else is skipped with a warning and a count. Writes use MERGE on
``id`` (nodes) and on (from, type, to) (edges), so running twice changes nothing.

    python -m cti_graphrag.ingest.load_gold
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from falkordb import Graph
from redis.exceptions import ResponseError

from cti_graphrag.graph.client import get_graph, run_query
from cti_graphrag.graph.schema import GraphSchema, load_schema
from cti_graphrag.ingest.build_gold import Edge, GoldGraph, build_gold
from cti_graphrag.ingest.normalize import load_composite_tools
from cti_graphrag.ingest.read import load_dataset

log = logging.getLogger(__name__)
BATCH_SIZE = 500
WRITE_TIMEOUT_MS = 60_000


@dataclass
class LoadPlan:
    nodes: dict[str, list[dict]] = field(default_factory=dict)  # label -> [{id, props}]
    edges: dict[tuple[str, str, str], list[dict]] = field(default_factory=dict)
    skipped_labels: Counter = field(default_factory=Counter)
    skipped_edges: Counter = field(default_factory=Counter)  # "TYPE (From->To)" -> n


def plan_load(gold: GoldGraph, schema: GraphSchema) -> LoadPlan:
    plan = LoadPlan()
    for label, nodes in gold.nodes.items():
        if not schema.allows_label(label):
            plan.skipped_labels[label] += len(nodes)
            continue
        plan.nodes[label] = [{"id": nid, "props": props} for nid, props in sorted(nodes.items())]
    grouped: dict[tuple[str, str, str], list[Edge]] = defaultdict(list)
    for edge in gold.edges.values():
        if schema.allows_edge(edge.type, edge.from_label, edge.to_label):
            grouped[(edge.type, edge.from_label, edge.to_label)].append(edge)
        else:
            plan.skipped_edges[f"{edge.type} ({edge.from_label}->{edge.to_label})"] += 1
    for key, edges in grouped.items():
        plan.edges[key] = [
            {"from": e.from_id, "to": e.to_id, "props": e.props}
            for e in sorted(edges, key=lambda e: (e.from_id, e.to_id))
        ]
    return plan


def _batches(rows: list[dict]):
    for start in range(0, len(rows), BATCH_SIZE):
        yield rows[start : start + BATCH_SIZE]


def write_plan(plan: LoadPlan, graph: Graph) -> dict[str, float]:
    """Labels and types come from the schema (never from data or users)."""
    stats: Counter = Counter()
    for label, rows in plan.nodes.items():
        query = f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) SET n += row.props"
        for batch in _batches(rows):
            result = run_query(query, {"rows": batch}, graph=graph, timeout_ms=WRITE_TIMEOUT_MS)
            stats["nodes_created"] += result.nodes_created
            stats["properties_set"] += result.properties_set
    for (rel_type, from_label, to_label), rows in plan.edges.items():
        query = (
            f"UNWIND $rows AS row "
            f"MATCH (a:{from_label} {{id: row.from}}) MATCH (b:{to_label} {{id: row.to}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) SET r += row.props"
        )
        for batch in _batches(rows):
            result = run_query(query, {"rows": batch}, graph=graph, timeout_ms=WRITE_TIMEOUT_MS)
            stats["relationships_created"] += result.relationships_created
            stats["properties_set"] += result.properties_set
    return dict(stats)


def graph_counts(graph: Graph) -> tuple[dict[str, int], dict[str, int]]:
    labels = run_query(
        "MATCH (n) RETURN labels(n)[0] AS label, count(n) ORDER BY label",
        graph=graph,
        read_only=True,
    )
    rels = run_query(
        "MATCH ()-[r]->() RETURN type(r) AS t, count(r) ORDER BY t", graph=graph, read_only=True
    )
    return dict(labels.result_set), dict(rels.result_set)


def reset_graph(graph: Graph) -> bool:
    """Delete the whole graph. Returns False when it did not exist yet."""
    try:
        graph.delete()
    except ResponseError as exc:
        if "empty key" not in str(exc).lower() and "invalid graph" not in str(exc).lower():
            raise
        return False
    return True


def load_gold(graph: Graph | None = None, *, reset: bool = False) -> dict:
    """Load the gold graph. ``reset=True`` deletes it first (use after changing
    mappings or the schema, so nodes that no longer exist do not linger)."""
    schema = load_schema()
    gold = build_gold(load_dataset(), load_composite_tools())
    plan = plan_load(gold, schema)
    for label, n in plan.skipped_labels.items():
        log.warning("Label fora do schema %s, pulado: %d nós", label, n)
    for name, n in plan.skipped_edges.items():
        log.warning("Relação fora do schema %s, pulada: %d arestas", name, n)
    graph = graph if graph is not None else get_graph(schema.graphs.get("gold", "cti_gold"))
    deleted = reset_graph(graph) if reset else False
    write_stats = write_plan(plan, graph)
    labels, rels = graph_counts(graph)
    return {
        "schema_version": schema.version,
        "graph": graph.name,
        "reset": deleted,
        "write": write_stats,
        "skipped_labels": dict(plan.skipped_labels),
        "skipped_edges": dict(plan.skipped_edges),
        "nodes_by_label": labels,
        "edges_by_type": rels,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Carga idempotente do cti_gold.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="apaga o grafo antes de carregar (use ao mudar mapeamento ou schema)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="AVISO: %(message)s")
    for key, value in load_gold(reset=args.reset).items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
