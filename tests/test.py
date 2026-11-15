from falkordb import FalkorDB

db = FalkorDB(host="127.0.0.1", port=6379)
graph = db.select_graph("cti_gold")

query = """
MATCH (n)-[:MENTIONED_IN]->(c:Chunk)-[:PART_OF]->(d:Document)
RETURN
    labels(n) AS entidade_tipo,
    n.name AS entidade,
    c.text AS evidencia,
    d.title AS documento,
    d.url AS fonte
LIMIT 10
"""

results = graph.query(query).result_set

for row in results:
    print("-" * 80)
    print("Tipo:", row[0])
    print("Entidade:", row[1])
    print("Evidência:", row[2])
    print("Documento:", row[3])
    print("Fonte:", row[4])