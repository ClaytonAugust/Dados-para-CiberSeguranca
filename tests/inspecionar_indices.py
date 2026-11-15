
import os
from pathlib import Path

from dotenv import load_dotenv
from falkordb import FalkorDB


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

db = FalkorDB(
    host=os.getenv("FALKORDB_HOST", "127.0.0.1"),
    port=int(os.getenv("FALKORDB_PORT", "6379"))
)

graph = db.select_graph(
    os.getenv("GRAPH_NAME", "cti_gold")
)


print("\n=== ÍNDICES DO FALKORDB ===\n")

indexes = graph.query("CALL db.indexes()").result_set

for index in indexes:
    print(index)


print("\n=== EMBEDDINGS NOS CHUNKS ===\n")

query = """
MATCH (c:Chunk)
RETURN
    count(c) AS total_chunks,
    count(c.embedding) AS chunks_with_embedding
"""

for row in graph.query(query).result_set:
    print("Total de chunks:", row[0])
    print("Chunks com embedding:", row[1])


print("\n=== PROPRIEDADES DOS CHUNKS ===\n")

query = """
MATCH (c:Chunk)
RETURN keys(c)
LIMIT 3
"""

for row in graph.query(query).result_set:
    print(row[0])


print("\n=== FIM DO DIAGNÓSTICO ===")
