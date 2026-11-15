
import os
import sys

from pathlib import Path
from dotenv import load_dotenv
from falkordb import FalkorDB

# Permite importar os módulos dentro de src/
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from cti_graphrag.retrieval import GraphRetriever


def main():

    load_dotenv(ROOT / ".env")

    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "127.0.0.1"),
        port=int(os.getenv("FALKORDB_PORT", "6379"))
    )

    graph = db.select_graph(
        os.getenv("GRAPH_NAME", "cti_gold")
    )

    retriever = GraphRetriever(graph)

    nome = input("\nEntidade para pesquisar: ").strip()

    if not nome:
        print("Informe uma entidade.")
        return

    matches = retriever.search_entities(nome)

    if not matches:
        print("Entidade não encontrada.")
        return

    if len(matches) > 1:

        print("\nEntidades encontradas:")

        for item in matches:
            print(
                f"{item['name']} | "
                f"{item['labels']} | "
                f"ID: {item['id']}"
            )

        entity_id = input("\nInforme o ID desejado: ").strip()

        selected = next(
            (item for item in matches if item["id"] == entity_id),
            None
        )

        if not selected:
            print("ID inválido.")
            return

    else:
        selected = matches[0]

    result = retriever.retrieve(selected["id"])

    if not result:
        print("Não foi possível recuperar a entidade.")
        return

    entity = result["entity"]

    print("\n" + "=" * 65)
    print("RECUPERAÇÃO GRAPH")
    print("=" * 65)

    print(f"\nEntidade: {entity['name']}")
    print(f"Tipo: {entity['labels']}")
    print(f"ID: {entity['id']}")

    print("\nRELACIONAMENTOS")
    print("-" * 65)

    for item in result["relationships"]:

        source = item["source"]["name"] or item["source"]["id"]
        target = item["target"]["name"] or item["target"]["id"]

        print(
            f"\n{source} "
            f"--[{item['relationship']}]--> "
            f"{target}"
        )

        print(
            f"Evidências associadas: "
            f"{len(item['evidences'])}"
        )

        for evidence in item["evidences"]:
            print(
                f"  Documento: {evidence['document']}"
            )
            print(
                f"  Fonte: {evidence['source_url']}"
            )

    print("\nEVIDÊNCIAS DIRETAS")
    print("-" * 65)

    for evidence in result["evidences"]:

        print(f"\nDocumento: {evidence['document']}")
        print(f"Fonte: {evidence['source_url']}")

        texto = evidence["text"] or ""

        print(f"Contexto: {texto[:350]}...")

    print("\n" + "=" * 65)
    print("FIM DA RECUPERAÇÃO")
    print("=" * 65)


if __name__ == "__main__":
    main()
