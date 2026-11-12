import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from falkordb import FalkorDB

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = PROJECT_ROOT / "schema" / "schema.yaml"

def load_schema() -> dict:
    """Load and validate the project YAML schema."""

    if not SCHEMA_FILE.is_file():
        raise FileNotFoundError(
            f"Schema não encontrado: {SCHEMA_FILE}"
        )

    with SCHEMA_FILE.open("r", encoding="utf-8") as file:
        schema = yaml.safe_load(file)

    if not isinstance(schema, dict):
        raise ValueError("O schema.yaml não contém um objeto válido.")

    for key in ("graphs", "labels", "embedding"):
        if key not in schema:
            raise ValueError(f"Campo obrigatório ausente: {key}")

    return schema


def execute_step(description: str, action) -> None:
    """Execute an index operation and handle existing structures."""

    try:
        action()
        print(f"  [OK] {description}")

    except Exception as exc:
        error = str(exc).lower()

        if "already exists" in error or "already exist" in error:
            print(f"  [EXISTENTE] {description}")
        else:
            raise RuntimeError(
                f"Falha ao executar: {description}\n"
                f"Detalhes: {exc}"
            ) from exc


def create_graph_indexes(graph, schema: dict) -> None:
    """Create indexes and unique constraints from schema.yaml."""

    labels = schema["labels"]
    embedding_config = schema["embedding"]

    dimensions = int(embedding_config["dimensions"])
    similarity = embedding_config["similarity"]

    # 1. Range indexes
    print("\n[1] Criando Range Indexes...")

    for label, config in labels.items():
        indexes = config.get("indexes", {})

        # Unique properties also need a supporting range index.
        properties = set(indexes.get("range", []))
        properties.update(indexes.get("unique", []))

        for prop in sorted(properties):
            execute_step(
                f"Range Index: {label}.{prop}",
                lambda label=label, prop=prop:
                    graph.create_node_range_index(label, prop)
            )

    # 2. Full-text indexes
    print("\n[2] Criando Full-text Indexes...")

    for label, config in labels.items():
        properties = config.get("indexes", {}).get("fulltext", [])

        if properties:
            execute_step(
                f"Full-text: {label} ({', '.join(properties)})",
                lambda label=label, properties=properties:
                    graph.create_node_fulltext_index(
                        label, *properties
                    )
            )

    # 3. Vector indexes
    print("\n[3] Criando Vector Indexes...")

    for label, config in labels.items():
        vector_property = config.get("indexes", {}).get("vector")

        if vector_property:
            execute_step(
                f"Vector: {label}.{vector_property} "
                f"({dimensions} dimensões, {similarity})",
                lambda label=label, prop=vector_property:
                    graph.create_node_vector_index(
                        label,
                        prop,
                        dim=dimensions,
                        similarity_function=similarity
                    )
            )

    # 4. Unique constraints
    print("\n[4] Criando Unique Constraints...")

    for label, config in labels.items():
        properties = config.get("indexes", {}).get("unique", [])

        if properties:
            execute_step(
                f"Unique Constraint: {label} ({', '.join(properties)})",
                lambda label=label, properties=properties:
                    graph.create_node_unique_constraint(
                        label, *properties
                    )
            )


def show_graph_status(graph) -> None:
    """Display indexes and constraint status."""

    print("\n--- ÍNDICES REGISTRADOS ---")

    indices = graph.list_indices()

    for item in indices.result_set:
        print(item)

    print("\n--- CONSTRAINTS REGISTRADAS ---")

    constraints = graph.list_constraints()

    if not constraints:
        print("Nenhuma constraint retornada.")
    else:
        for constraint in constraints:
            print(constraint)


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    host = os.getenv("FALKORDB_HOST", "127.0.0.1")
    port = int(os.getenv("FALKORDB_PORT", "6379"))

    try:
        schema = load_schema()

        db = FalkorDB(host=host, port=port)

        print("=" * 55)
        print("CTI GraphRAG - CONFIGURAÇÃO DOS ÍNDICES")
        print("=" * 55)

        # Configure both graphs defined in schema.yaml.
        for graph_name in schema["graphs"].values():
            print(f"\n{'=' * 55}")
            print(f"GRAFO: {graph_name}")
            print("=" * 55)

            graph = db.select_graph(graph_name)

            create_graph_indexes(graph, schema)

            show_graph_status(graph)

        print("\nConfiguração dos índices finalizada.")
        return 0

    except Exception as exc:
        print(f"\nERRO: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
