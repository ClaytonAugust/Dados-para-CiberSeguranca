from falkordb import FalkorDB

# Conectar ao FalkorDB
db = FalkorDB(
    host="localhost",
    port=6379
)

# Selecionar o grafo
graph = db.select_graph("cti_gold")

# Criar um grupo de teste
graph.query("""
    MERGE (g:Group {id: 'G0016'})
    SET g.name = 'APT29'
    RETURN g
""")

# Consultar os registros
result = graph.query("""
    MATCH (g:Group)
    RETURN g.id, g.name
""")

for record in result.result_set:
    print(record)