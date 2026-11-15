
import os
from pathlib import Path

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from falkordb import FalkorDB


# --------------------------------------------------
# CONFIGURAÇÕES
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

MODEL_NAME = "intfloat/multilingual-e5-small"
TOP_K = 5


# --------------------------------------------------
# CONEXÃO
# --------------------------------------------------

def conectar():

    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "127.0.0.1"),
        port=int(os.getenv("FALKORDB_PORT", "6379"))
    )

    return db.select_graph(
        os.getenv("GRAPH_NAME", "cti_gold")
    )


# --------------------------------------------------
# CARREGAR MODELO
# --------------------------------------------------

def carregar_modelo():

    print("Carregando modelo de embeddings...")

    return SentenceTransformer(
        MODEL_NAME,
        device="cpu"
    )


# --------------------------------------------------
# GERAR EMBEDDING DA PERGUNTA
# --------------------------------------------------

def gerar_embedding(model, pergunta):

    texto = "query: " + pergunta

    vetor = model.encode(
        texto,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    if len(vetor) != 384:
        raise ValueError(
            f"Dimensão incompatível: {len(vetor)}"
        )

    return vetor.tolist()


# --------------------------------------------------
# BUSCA VETORIAL
# --------------------------------------------------

def buscar_chunks(graph, vetor, top_k=TOP_K):

    query = """
    CALL db.idx.vector.queryNodes(
        'Chunk',
        'embedding',
        $k,
        vecf32($vector)
    )
    YIELD node, score

    OPTIONAL MATCH
        (node)-[:PART_OF]->(d:Document)

    RETURN
        node.id AS chunk_id,
        d.title AS document,
        d.url AS source,
        node.text AS text,
        (1 - score) AS similarity

    ORDER BY similarity DESC
    """

    result = graph.ro_query(
        query,
        params={
            "k": top_k,
            "vector": vetor
        }
    )

    return result.result_set


# --------------------------------------------------
# EXIBIR RESULTADOS
# --------------------------------------------------

def exibir_resultados(results):

    print("\n" + "=" * 75)
    print("RESULTADOS DA BUSCA SEMÂNTICA")
    print("=" * 75)

    if not results:
        print("Nenhum resultado encontrado.")
        return

    for index, row in enumerate(results, start=1):

        chunk_id, document, source, text, similarity = row

        print(f"\nRESULTADO #{index}")
        print("-" * 75)

        print(f"Chunk: {chunk_id}")
        print(f"Documento: {document}")
        print(f"Similaridade: {similarity:.4f}")
        print(f"Fonte: {source}")

        print("\nConteúdo:")
        print((text or "")[:900])

    print("\n" + "=" * 75)
    print("FIM DA BUSCA")
    print("=" * 75)


# --------------------------------------------------
# EXECUÇÃO
# --------------------------------------------------

def main():

    try:

        graph = conectar()
        model = carregar_modelo()

        pergunta = input(
            "\nDigite sua pergunta: "
        ).strip()

        if not pergunta:
            print("Pergunta não informada.")
            return

        print("\nGerando embedding da pergunta...")

        vetor = gerar_embedding(
            model,
            pergunta
        )

        print("Consultando índice vetorial...")

        results = buscar_chunks(
            graph,
            vetor
        )

        exibir_resultados(results)

    except Exception as erro:

        print(f"\nErro na busca semântica: {erro}")


if __name__ == "__main__":
    main()
