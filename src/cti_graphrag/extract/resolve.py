"""Casa os nomes das triplas extraídas com nós do cti_gold (só ro_query).

- Group e Software: por nome ou alias, sem diferenciar maiúsculas.
- Country: pelo nome do nó Country (id country:<ISO>).
- Sector: pelo nome do nó Sector.
O que não casar recebe new:<Label>:<slug> e vai para unresolved.csv.

Head: o prompt pede que o head seja o grupo descrito no texto. Se o head
extraído não casar (ex.: "this group") e o texto é de um grupo (apt ou
ransomware), tenta-se o entity_name do registro. Se ainda não casar,
tenta-se Software (head_type="Software"); o loader rejeita esses casos.

Uso: python -m cti_graphrag.extract.resolve
"""

import csv
import json
import os
import re
from pathlib import Path

RAW_FILE = Path("eval/extraction/triples_raw.jsonl")
TEXTS_FILE = Path("eval/extraction/texts.jsonl")
OUT_FILE = Path("eval/extraction/triples.jsonl")
UNRESOLVED_FILE = Path("eval/extraction/unresolved.csv")


def norm(name):
    """Minúsculas, sem espaços nas pontas e sem anotação entre parênteses."""
    name = re.sub(r"\(.*?\)", "", str(name))
    return " ".join(name.lower().split())


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def build_index(graph):
    """Monta {label: {nome_normalizado: id}} a partir do grafo (só leitura).

    Nomes têm prioridade sobre aliases quando há conflito.
    """
    index = {}
    for label in ["Group", "Software"]:
        rows = graph.ro_query(f"MATCH (n:{label}) RETURN n.id, n.name, n.aliases").result_set
        names, aliases = {}, {}
        for node_id, name, alias_list in rows:
            names.setdefault(norm(name), node_id)
            for a in alias_list or []:
                aliases.setdefault(norm(a), node_id)
        index[label] = {**aliases, **names}
    for label in ["Country", "Sector"]:
        rows = graph.ro_query(f"MATCH (n:{label}) RETURN n.id, n.name").result_set
        index[label] = {norm(name): node_id for node_id, name in rows}
    return index


def resolve_name(index, label, name):
    """Devolve (id, resolvido?)."""
    node_id = index.get(label, {}).get(norm(name))
    if node_id:
        return node_id, True
    return f"new:{label}:{slug(name)}", False


def resolve_triples(triples, texts, index):
    """Devolve (triplas resolvidas, linhas para unresolved.csv)."""
    out, unresolved = [], []
    for t in triples:
        doc = texts[t["doc_id"]]
        kind = t["doc_id"].split(":")[0]

        head_type, head_source = "Group", "head"
        head_id, head_ok = resolve_name(index, "Group", t["head"])
        if not head_ok and kind in ("apt", "ransomware"):
            alt_id, alt_ok = resolve_name(index, "Group", doc["entity_name"])
            if alt_ok:
                head_id, head_ok, head_source = alt_id, True, "entity_name"
        if not head_ok:
            # ex.: num texto de malware o LLM pôs o próprio malware como head
            sw_id, sw_ok = resolve_name(index, "Software", t["head"])
            if sw_ok:
                head_id, head_ok, head_type = sw_id, True, "Software"

        tail_id, tail_ok = resolve_name(index, t["tail_type"], t["tail"])

        for role, label, name, node_id, ok in [
            ("head", head_type, t["head"], head_id, head_ok),
            ("tail", t["tail_type"], t["tail"], tail_id, tail_ok),
        ]:
            if not ok:
                unresolved.append({"doc_id": t["doc_id"], "role": role, "label": label,
                                   "name": name, "new_id": node_id})

        out.append({**t, "head_id": head_id, "head_type": head_type, "head_resolved": head_ok,
                    "head_source": head_source, "tail_id": tail_id, "tail_resolved": tail_ok})
    return out, unresolved


def main():
    from dotenv import load_dotenv
    from falkordb import FalkorDB

    load_dotenv(".env")
    graph = FalkorDB(host=os.getenv("FALKORDB_HOST"),
                     port=int(os.getenv("FALKORDB_PORT"))).select_graph("cti_gold")
    index = build_index(graph)

    read = lambda p: [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    texts = {r["doc_id"]: r for r in read(TEXTS_FILE)}
    triples, unresolved = resolve_triples(read(RAW_FILE), texts, index)

    with OUT_FILE.open("w", encoding="utf-8") as f:
        for t in triples:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    with UNRESOLVED_FILE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["doc_id", "role", "label", "name", "new_id"])
        w.writeheader()
        w.writerows(unresolved)

    total = 2 * len(triples)
    ok = sum(t["head_resolved"] + t["tail_resolved"] for t in triples)
    print(f"{len(triples)} triplas; entidades resolvidas {ok}/{total}; "
          f"não resolvidas em {UNRESOLVED_FILE}: {len(unresolved)}")


if __name__ == "__main__":
    main()
