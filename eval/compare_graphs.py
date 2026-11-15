"""Compara o grafo extraído (cti_extracted) com o gold (cti_gold).

Recorte: os textos cuja extração terminou (resposta no cache do extrator),
cada um mapeado para o seu Group no cti_gold pelo entity_name (resolve.py).
Para esses grupos e as 3 relações (ASSOCIATED_WITH, TARGETS, USES),
compara os conjuntos DISTINTOS de arestas (group_id, relação, tail_id):
  precisão = acertos / arestas extraídas
  recall   = acertos / arestas no gold
  F1       = média harmônica
Os dois grafos são lidos só com ro_query.

Saída: eval/results/<data>/extraction.csv
Uso: python eval/compare_graphs.py
"""

import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

RELATIONS = ["ASSOCIATED_WITH", "TARGETS", "USES"]
# mesmos pares do extrator; no gold, USES também liga Group -> Technique (fora do escopo)
ALLOWED = {("ASSOCIATED_WITH", "Country"), ("TARGETS", "Sector"), ("TARGETS", "Country"),
           ("USES", "Software")}
EDGE_QUERY = """
MATCH (g:Group)-[r]->(t)
WHERE g.id IN $ids AND type(r) IN $rels
RETURN DISTINCT g.id, type(r), t.id, labels(t)[0]
"""


def edges(graph, group_ids):
    rows = graph.ro_query(EDGE_QUERY, {"ids": sorted(group_ids), "rels": RELATIONS}).result_set
    return {(g, r, t, label) for g, r, t, label in rows if (r, label) in ALLOWED}


def prf(extracted, gold):
    hits = len(extracted & gold)
    p = hits / len(extracted) if extracted else None
    r = hits / len(gold) if gold else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return hits, p, r, f


# linhas da tabela: (nome, relação, label do tail); None = qualquer
TABLE_ROWS = [
    ("ASSOCIATED_WITH", "ASSOCIATED_WITH", None),
    ("TARGETS -> Country", "TARGETS", "Country"),
    ("TARGETS -> Sector", "TARGETS", "Sector"),
    ("USES", "USES", None),
    ("total", None, None),
]


def compare(extracted, gold):
    """Uma linha por TABLE_ROWS. Arestas são tuplas (group, relação, tail, label_do_tail);
    o acerto é decidido só por (group, relação, tail) — o label serve para separar linhas."""
    def pick(edge_set, rel, label):
        return {x[:3] for x in edge_set
                if (rel is None or x[1] == rel) and (label is None or x[3] == label)}

    rows = []
    for name, rel, label in TABLE_ROWS:
        e, g = pick(extracted, rel, label), pick(gold, rel, label)
        hits, p, r, f = prf(e, g)
        rows.append({"relation": name, "n_extracted": len(e), "n_gold": len(g), "hits": hits,
                     "precision": None if p is None else round(p, 4),
                     "recall": None if r is None else round(r, 4),
                     "f1": None if f is None else round(f, 4)})
    return rows


def main():
    sys.path.insert(0, "src")
    from dotenv import load_dotenv
    from falkordb import FalkorDB

    from cti_graphrag.extract.extractor import CACHE_DIR, PROMPT, TEXTS_FILE, cache_key
    from cti_graphrag.extract.resolve import build_index, resolve_name

    load_dotenv(".env")
    model = os.getenv("LLM_MODEL")
    db = FalkorDB(host=os.getenv("FALKORDB_HOST"), port=int(os.getenv("FALKORDB_PORT")))
    gold, extracted = db.select_graph("cti_gold"), db.select_graph("cti_extracted")

    texts = [json.loads(x) for x in TEXTS_FILE.read_text(encoding="utf-8").splitlines()]
    done = [t for t in texts if (CACHE_DIR / f"{cache_key(model, PROMPT + t['text'])}.json").exists()]
    index = build_index(gold)
    group_ids, skipped = set(), []
    for t in done:
        gid, ok = resolve_name(index, "Group", t["entity_name"])
        (group_ids.add(gid) if ok else skipped.append(t["doc_id"]))

    rows = compare(edges(extracted, group_ids), edges(gold, group_ids))
    out_dir = Path("eval/results") / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "extraction.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"textos extraídos: {len(done)}; grupos no recorte: {len(group_ids)}; "
          f"sem Group no gold: {skipped}")
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
