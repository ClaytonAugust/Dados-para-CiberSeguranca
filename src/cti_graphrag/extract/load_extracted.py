"""Grava as triplas resolvidas no grafo cti_extracted (nunca no cti_gold).

Nós: MERGE por id. Arestas: MERGE por (head, relação, tail, doc_id), com
source="extracted", evidence e confidence. Rodar 2 vezes não duplica.
Labels e relações vêm de listas fixas (Cypher não aceita label como
parâmetro); os valores vão sempre como parâmetros.

Uso: python -m cti_graphrag.extract.load_extracted
"""

import json
import os
from pathlib import Path

TRIPLES_FILE = Path("eval/extraction/triples.jsonl")
TARGET_GRAPH = "cti_extracted"
LABELS = {"Group", "Software", "Country", "Sector"}
RELATIONS = {"ASSOCIATED_WITH", "TARGETS", "USES"}

NODE_CYPHER = """
MERGE (n:{label} {{id: $id}})
ON CREATE SET n.name = $name
SET n.source = 'extracted', n.resolved = $resolved
"""

EDGE_CYPHER = """
MATCH (h:{head_label} {{id: $head_id}}), (t:{tail_label} {{id: $tail_id}})
MERGE (h)-[r:{relation} {{doc_id: $doc_id}}]->(t)
SET r.source = 'extracted', r.evidence = $evidence, r.confidence = $confidence
"""


def head_name(t, texts):
    if t.get("head_source") == "entity_name":
        return texts[t["doc_id"]]["entity_name"]
    return t["head"]


def load(graph, triples, texts):
    """Grava as triplas; devolve {"carregadas": n, "rejeitadas_head": n}.

    Todas as relações permitidas saem de Group, então tripla cujo head
    resolvido não é Group (ex.: o próprio malware) é rejeitada e contada.
    """
    if graph.name != TARGET_GRAPH:
        raise RuntimeError(f"load_extracted só escreve em {TARGET_GRAPH}, não em {graph.name!r}")
    counts = {"carregadas": 0, "rejeitadas_head": 0}
    for t in triples:
        head_label = t.get("head_type", "Group")
        if head_label != "Group":
            counts["rejeitadas_head"] += 1
            continue
        if t["tail_type"] not in LABELS or t["relation"] not in RELATIONS:
            raise ValueError(f"label ou relação fora da lista: {t}")
        graph.query(NODE_CYPHER.format(label=head_label),
                    {"id": t["head_id"], "name": head_name(t, texts), "resolved": t["head_resolved"]})
        graph.query(NODE_CYPHER.format(label=t["tail_type"]),
                    {"id": t["tail_id"], "name": t["tail"], "resolved": t["tail_resolved"]})
        graph.query(EDGE_CYPHER.format(head_label=head_label, tail_label=t["tail_type"],
                                       relation=t["relation"]),
                    {"head_id": t["head_id"], "tail_id": t["tail_id"], "doc_id": t["doc_id"],
                     "evidence": t["evidence"], "confidence": t["confidence"]})
        counts["carregadas"] += 1
    return counts


def main():
    from dotenv import load_dotenv
    from falkordb import FalkorDB

    load_dotenv(".env")
    db = FalkorDB(host=os.getenv("FALKORDB_HOST"), port=int(os.getenv("FALKORDB_PORT")))
    read = lambda p: [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines()]
    texts = {r["doc_id"]: r for r in read("eval/extraction/texts.jsonl")}
    counts = load(db.select_graph(TARGET_GRAPH), read(TRIPLES_FILE), texts)
    print(f"{TARGET_GRAPH}: {counts}")


if __name__ == "__main__":
    main()
