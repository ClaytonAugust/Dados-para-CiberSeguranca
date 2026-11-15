"""Preenche expected_ids em eval/questions.csv rodando cada gold_cypher.

Só leitura no banco (ro_query). A gold_cypher deve devolver uma coluna "id".
Pergunta sem gold_cypher ou sem resultado fica com expected_ids vazio.

Uso: python eval/fill_expected.py
"""

import csv
import os
from pathlib import Path

QUESTIONS = Path("eval/questions.csv")


def fill(rows, graph):
    for row in rows:
        ids = []
        if row["gold_cypher"].strip():
            result = graph.ro_query(row["gold_cypher"])
            col = [h[1] for h in result.header].index("id")
            ids = sorted({str(r[col]) for r in result.result_set})
        row["expected_ids"] = ";".join(ids)
    return rows


def main():
    from dotenv import load_dotenv
    from falkordb import FalkorDB

    load_dotenv(".env")
    graph = FalkorDB(host=os.getenv("FALKORDB_HOST"),
                     port=int(os.getenv("FALKORDB_PORT"))).select_graph(os.getenv("GRAPH_NAME"))
    with QUESTIONS.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    fill(rows, graph)
    with QUESTIONS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    empty = [r["id"] for r in rows if not r["expected_ids"]]
    print(f"{len(rows)} perguntas; vazias: {empty}")


if __name__ == "__main__":
    main()
