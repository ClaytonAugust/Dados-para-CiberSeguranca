
import os
import sys

from pathlib import Path
from dotenv import load_dotenv
from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT / "src"))

from cti_graphrag.retrieval import HybridRetriever


def main():

    load_dotenv(ROOT / ".env")

    print("Conectando ao FalkorDB...")

    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "127.0.0.1"),
        port=int(os.getenv("FALKORDB_PORT", "6379"))
    )

    graph = db.select_graph(
        os.getenv("GRAPH_NAME", "cti_gold")
    )

    retriever = HybridRetriever(graph)

    question = input(
        "\nDigite sua pergunta de investigação CTI: "
    ).strip()

    if not question:
        print("Pergunta não informada.")
        return

    print("\nExecutando recuperação híbrida...")

    result = retriever.retrieve(
        question,
        top_k=5,
        max_entities=20
    )

    # ----------------------------------------------
    # RESULTADOS VETORIAIS
    # ----------------------------------------------

    print("\n" + "=" * 75)
    print("1. RESULTADOS DA BUSCA SEMÂNTICA")
    print("=" * 75)

    for index, item in enumerate(
        result["semantic_results"], start=1
    ):

        print(f"\n#{index} - {item['document']}")
        print(f"Similaridade: {item['similarity']:.4f}")
        print(f"Chunk: {item['chunk_id']}")
        print(f"Fonte: {item['source']}")

    # ----------------------------------------------
    # ENTIDADES IDENTIFICADAS
    # ----------------------------------------------

    print("\n" + "=" * 75)
    print("2. ENTIDADES IDENTIFICADAS NO GRAFO")
    print("=" * 75)

    for entity in result["entities"]:

        print(
            f"\n{entity['name']} "
            f"| {entity['labels']} "
            f"| ID: {entity['id']}"
        )

        print(
            f"Similaridade do chunk: "
            f"{entity['similarity']:.4f}"
        )

    # ----------------------------------------------
    # RELACIONAMENTOS EXPANDIDOS
    # ----------------------------------------------

    print("\n" + "=" * 75)
    print("3. RELACIONAMENTOS RECUPERADOS")
    print("=" * 75)

    if not result["relationships"]:
        print("Nenhum relacionamento encontrado.")

    for item in result["relationships"]:

        source = (
            item["source"]["name"]
            or item["source"]["id"]
        )

        target = (
            item["target"]["name"]
            or item["target"]["id"]
        )

        print(
            f"\n{source} "
            f"--[{item['relationship']}]--> "
            f"{target}"
        )

        print(
            "Entidade(s) que originaram a expansão: "
            + ", ".join(item["seed_entities"])
        )

        print(
            f"Evidências: {len(item['evidences'])}"
        )

        for evidence in item["evidences"]:

            print(
                f"  Documento: {evidence['document']}"
            )

            print(
                f"  Fonte: {evidence['source_url']}"
            )

    print("\n" + "=" * 75)
    print("RECUPERAÇÃO HÍBRIDA CONCLUÍDA")
    print("=" * 75)


if __name__ == "__main__":
    main()
