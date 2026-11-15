from falkordb import FalkorDB

db = FalkorDB(host="127.0.0.1", port=6379)
graph = db.select_graph("cti_gold")

query = """
MATCH (n:Technique)
WHERE n.name IN [
    'Data from Local System',
    'Encrypted Channel',
    'System Information Discovery'
]
RETURN n
"""

rows = graph.query(query).result_set

print("Técnicas encontradas:")
for row in rows:
    for node in row:
        print(node.properties)
        print("-" * 60)
