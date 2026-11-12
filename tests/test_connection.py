import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from falkordb import FalkorDB

def main() -> int:
    # Localiza o .env na raiz do projeto
    project_root = Path(__file__).resolve().parents[1]
    env_file = project_root / ".env"

    # Carrega as variáveis de ambiente
    load_dotenv(dotenv_path=env_file)

    host = os.getenv("FALKORDB_HOST", "127.0.0.1")
    port_raw = os.getenv("FALKORDB_PORT", "6379")
    graph_name = os.getenv("GRAPH_NAME", "cti_gold")

    try:
        port = int(port_raw)
    except ValueError:
        print(f"FALKORDB_PORT inválida: {port_raw!r}")
        return 2

    try:
        # Conecta ao FalkorDB
        db = FalkorDB(host=host, port=port)

        # Seleciona o grafo
        graph = db.select_graph(graph_name)

        # Executa consulta de teste
        result = graph.query("RETURN 1 AS status")

    except Exception as exc:
        print("Não foi possível conectar ao FalkorDB.")
        print(f"Destino: {host}:{port}")
        print(f"Grafo: {graph_name}")
        print(f"Erro: {exc}")
        print("Verifique: docker compose ps")

        return 1

    if not result.result_set or result.result_set[0][0] != 1:
        print("A consulta retornou um resultado inesperado.")
        return 1

    print("\nConexão com FalkorDB: OK")
    print(f"Servidor: {host}:{port}")
    print(f"Grafo selecionado: {graph_name}")
    print("Consulta Cypher: RETURN 1 AS status -> OK")

    return 0


if __name__ == "__main__":
    sys.exit(main())