
import os
from pathlib import Path
from collections import defaultdict

import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from falkordb import FalkorDB


# --------------------------------------------------
# CONFIGURAÇÕES
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

MODEL_NAME = "intfloat/multilingual-e5-small"
EXPECTED_DIMENSION = 384

WINDOW_SIZE = 450
OVERLAP = 50
BATCH_SIZE = 8
WRITE_BATCH_SIZE = 32


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
# DIVIDIR TEXTOS LONGOS
# --------------------------------------------------

def dividir_em_janelas(text, tokenizer):

    token_ids = tokenizer(
        text,
        add_special_tokens=False,
        truncation=False
    )["input_ids"]

    if not token_ids:
        return []

    stride = WINDOW_SIZE - OVERLAP
    windows = []

    for start in range(0, len(token_ids), stride):

        part = token_ids[start:start + WINDOW_SIZE]

        if not part:
            break

        passage = tokenizer.decode(
            part,
            skip_special_tokens=True
        )

        windows.append(passage)

        if start + WINDOW_SIZE >= len(token_ids):
            break

    return windows


# --------------------------------------------------
# RECUPERAR CHUNKS SEM EMBEDDINGS
# --------------------------------------------------

def carregar_chunks(graph):

    query = """
    MATCH (c:Chunk)
    WHERE c.embedding IS NULL
      AND c.text IS NOT NULL
    RETURN c.id, c.text
    ORDER BY c.id
    """

    rows = graph.ro_query(query).result_set

    return [
        {"id": row[0], "text": row[1]}
        for row in rows
        if row[1]
    ]


# --------------------------------------------------
# GERAR EMBEDDINGS
# --------------------------------------------------

def gerar_vetores(model, chunks):

    passages = []
    owners = []

    print("\nPreparando textos...")

    for chunk in chunks:

        windows = dividir_em_janelas(
            chunk["text"],
            model.tokenizer
        )

        for window in windows:

            passages.append(
                "passage: " + window
            )

            owners.append(chunk["id"])

    if not passages:
        raise ValueError("Nenhum texto válido para gerar embeddings.")

    print(f"Chunks: {len(chunks)}")
    print(f"Passagens geradas: {len(passages)}")

    print("\nGerando embeddings...")

    vectors = model.encode(
        passages,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    if vectors.shape[1] != EXPECTED_DIMENSION:
        raise ValueError(
            f"Dimensão inesperada: {vectors.shape[1]}"
        )

    # Agrupa as janelas de um mesmo chunk.
    acumulados = defaultdict(
        lambda: np.zeros(EXPECTED_DIMENSION, dtype=np.float32)
    )

    quantidades = defaultdict(int)

    for chunk_id, vector in zip(owners, vectors):

        acumulados[chunk_id] += vector
        quantidades[chunk_id] += 1

    resultado = []

    for chunk_id, vector in acumulados.items():

        media = vector / quantidades[chunk_id]

        norma = np.linalg.norm(media)

        if norma == 0:
            continue

        media = media / norma

        resultado.append({
            "chunk_id": chunk_id,
            "vector": media.astype(np.float32).tolist()
        })

    return resultado


# --------------------------------------------------
# PERSISTIR NO FALKORDB
# --------------------------------------------------

def salvar_embeddings(graph, embeddings):

    query = """
    UNWIND $batch AS item

    MATCH (c:Chunk {id: item.chunk_id})

    SET c.embedding = vecf32(item.vector)
    """

    total = 0

    for start in range(0, len(embeddings), WRITE_BATCH_SIZE):

        batch = embeddings[
            start:start + WRITE_BATCH_SIZE
        ]

        graph.query(
            query,
            params={"batch": batch}
        )

        total += len(batch)

        print(
            f"Vetores salvos: {total}/{len(embeddings)}"
        )

    return total


# --------------------------------------------------
# VERIFICAR PERSISTÊNCIA
# --------------------------------------------------

def verificar(graph):

    query = """
    MATCH (c:Chunk)
    RETURN
        count(c) AS total,
        count(c.embedding) AS com_embedding
    """

    row = graph.ro_query(query).result_set[0]

    print("\n=== RESULTADO FINAL ===")
    print("Total de chunks:", row[0])
    print("Chunks com embedding:", row[1])


# --------------------------------------------------
# EXECUÇÃO
# --------------------------------------------------

def main():

    print("Conectando ao FalkorDB...")

    graph = conectar()

    print("Carregando modelo:", MODEL_NAME)

    model = SentenceTransformer(
        MODEL_NAME,
        device="cpu"
    )

    print(
        "Dimensão do modelo:",
        model.get_embedding_dimension()
    )

    if model.get_embedding_dimension() != EXPECTED_DIMENSION:
        raise ValueError("Modelo incompatível com o índice vetorial.")

    chunks = carregar_chunks(graph)

    if not chunks:
        print("Todos os chunks já possuem embeddings.")
        verificar(graph)
        return

    print(f"\nChunks sem embedding: {len(chunks)}")

    embeddings = gerar_vetores(
        model,
        chunks
    )

    total = salvar_embeddings(
        graph,
        embeddings
    )

    print(f"\nEmbeddings persistidos: {total}")

    verificar(graph)


if __name__ == "__main__":
    main()
