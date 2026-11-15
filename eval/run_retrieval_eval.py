"""Avaliação da recuperação, SEM LLM.

Para cada pergunta chama só HybridRetriever.retrieve (parâmetros padrão do
pipeline: top_k=5, max_entities=20) e mede, contra expected_ids:
  - recall e precisão sobre TODOS os nós recuperados
    (entidades + pontas de todas as relações);
  - recall e precisão sobre os nós das 12 primeiras relações, que é o que
    GraphRAGPipeline manda ao LLM (max_relationships=12);
  - nº de caminhos (relações) e tempo de cada etapa.
O tempo por etapa é medido embrulhando os métodos da instância
(semantic_search, find_entities, expand_graph); o código do retriever
não é alterado.

lista_longa: perguntas com mais de 20 expected_ids (= max_entities) ficam
fora da média principal e têm média própria. Sem resposta: recall e
precisão não se aplicam; registra-se quantos nós vieram mesmo assim.

Saída: eval/results/<data>/retrieval.csv e resumo.json.
Uso: python eval/run_retrieval_eval.py
"""

import csv
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from statistics import mean

QUESTIONS = Path("eval/questions.csv")
LONG_LIST = 20
PIPELINE_RELATIONSHIPS = 12


def group_of(row):
    if row["category"] == "no_answer":
        return "sem_resposta"
    if row["category"] == "aggregation":
        return "agregacao"
    return f"{row['hops']}_salto" + ("s" if row["hops"] != "1" else "")


def node_ids(result, max_relationships=None):
    rels = result["relationships"]
    if max_relationships is not None:
        rels = rels[:max_relationships]
        ids = set()
    else:
        ids = {e["id"] for e in result["entities"]}
    for r in rels:
        ids.add(r["source"]["id"])
        ids.add(r["target"]["id"])
    return ids


def recall_precision(expected, retrieved):
    if not expected:
        return None, None
    hit = len(expected & retrieved)
    return hit / len(expected), (hit / len(retrieved) if retrieved else 0.0)


def timed(obj, method, times):
    original = getattr(obj, method)

    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            times[method] = int((time.perf_counter() - start) * 1000)

    setattr(obj, method, wrapper)


def evaluate(rows, retriever):
    times = {}
    for m in ["semantic_search", "find_entities", "expand_graph"]:
        timed(retriever, m, times)
    out = []
    for row in rows:
        times.clear()
        start = time.perf_counter()
        result = retriever.retrieve(row["question"])
        total_ms = int((time.perf_counter() - start) * 1000)
        expected = set(filter(None, row["expected_ids"].split(";")))
        all_ids = node_ids(result)
        top_ids = node_ids(result, PIPELINE_RELATIONSHIPS)
        rec, prec = recall_precision(expected, all_ids)
        rec12, prec12 = recall_precision(expected, top_ids)
        out.append({
            "id": row["id"], "grupo": group_of(row), "category": row["category"],
            "n_expected": len(expected), "lista_longa": len(expected) > LONG_LIST,
            "n_entities": len(result["entities"]), "n_paths": len(result["relationships"]),
            "n_nodes": len(all_ids), "hits": len(expected & all_ids),
            "recall": rec, "precision": prec,
            "n_nodes_top12": len(top_ids), "hits_top12": len(expected & top_ids),
            "recall_top12": rec12, "precision_top12": prec12,
            "ms_vetorial": times.get("semantic_search"), "ms_entidades": times.get("find_entities"),
            "ms_expansao": times.get("expand_graph"), "ms_total": total_ms,
            "missing": ";".join(sorted(expected - all_ids)),
        })
    return out


def avg(values):
    values = [v for v in values if v is not None]
    return round(mean(values), 4) if values else None


def summarize(results):
    metrics = ["recall", "precision", "recall_top12", "precision_top12"]
    main_rows = [r for r in results if not r["lista_longa"] and r["n_expected"]]
    long_rows = [r for r in results if r["lista_longa"]]
    by_group = {}
    for g in sorted({r["grupo"] for r in results}):
        rows = [r for r in results if r["grupo"] == g and not r["lista_longa"]]
        by_group[g] = {"n": len(rows), **{m: avg(r[m] for r in rows) for m in metrics},
                       "paths": avg(r["n_paths"] for r in rows),
                       "nodes": avg(r["n_nodes"] for r in rows)}
    return {
        "n_perguntas": len(results),
        "regra_lista_longa": f"n_expected > {LONG_LIST}",
        "media_principal": {"n": len(main_rows), **{m: avg(r[m] for r in main_rows) for m in metrics}},
        "lista_longa": {"n": len(long_rows), "ids": [r["id"] for r in long_rows],
                        **{m: avg(r[m] for r in long_rows) for m in metrics}},
        "por_grupo_sem_lista_longa": by_group,
        "tempo_ms_medio": {k: avg(r[k] for r in results)
                           for k in ["ms_vetorial", "ms_entidades", "ms_expansao", "ms_total"]},
        "sem_resposta_nos_recuperados": {r["id"]: r["n_nodes"] for r in results
                                         if r["grupo"] == "sem_resposta"},
    }


def main():
    sys.path.insert(0, "src")
    from dotenv import load_dotenv
    from falkordb import FalkorDB

    from cti_graphrag.retrieval import HybridRetriever

    load_dotenv(".env")
    graph = FalkorDB(host=os.getenv("FALKORDB_HOST"),
                     port=int(os.getenv("FALKORDB_PORT"))).select_graph(os.getenv("GRAPH_NAME"))
    rows = list(csv.DictReader(QUESTIONS.open(encoding="utf-8")))
    results = evaluate(rows, HybridRetriever(graph))

    out_dir = Path("eval/results") / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "retrieval.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    summary = summarize(results)
    summary["graph"] = os.getenv("GRAPH_NAME")
    (out_dir / "resumo.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(f"gravado em {out_dir}")


if __name__ == "__main__":
    main()
