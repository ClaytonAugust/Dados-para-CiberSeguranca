from falkordb import FalkorDB

db = FalkorDB(host="127.0.0.1", port=6379)
graph = db.select_graph("cti_gold")

consultas = {
    "Total de nós": "MATCH (n) RETURN count(n)",
    "Documentos": "MATCH (n:Document) RETURN count(n)",
    "Chunks": "MATCH (n:Chunk) RETURN count(n)",
    "Total de relacionamentos": "MATCH ()-[r]->() RETURN count(r)",
}

for nome, consulta in consultas.items():
    resultado = graph.query(consulta).result_set
    print(f"{nome}: {resultado[0][0]}")

print("\nTipos de relacionamentos:")

resultado = graph.query("""
    MATCH ()-[r]->()
    RETURN type(r), count(r)
    ORDER BY count(r) DESC
""").result_set

for relacao, quantidade in resultado:
    print(f"{relacao}: {quantidade}")