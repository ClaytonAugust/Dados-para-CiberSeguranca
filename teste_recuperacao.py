
import os
from pathlib import Path

from dotenv import load_dotenv
from falkordb import FalkorDB


# --------------------------------------------------
# 1. CONFIGURAÇÃO
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

HOST = os.getenv("FALKORDB_HOST", "127.0.0.1")
PORT = int(os.getenv("FALKORDB_PORT", "6379"))
GRAPH_NAME = os.getenv("GRAPH_NAME", "cti_gold")


def conectar():
    """Estabelece conexão com o FalkorDB."""
    db = FalkorDB(host=HOST, port=PORT)
    return db.select_graph(GRAPH_NAME)


# --------------------------------------------------
# 2. LOCALIZAÇÃO DE ENTIDADES
# --------------------------------------------------

def localizar_entidade(graph, nome):
    """Procura uma entidade pelo nome exato ou parcialmente."""

    query_exata = """
    MATCH (e)
    WHERE e.name IS NOT NULL
      AND toLower(e.name) = toLower($nome)
    RETURN
        labels(e) AS labels,
        e.id AS id,
        e.name AS name,
        e.type AS type
    LIMIT 20
    """

    resultado = graph.ro_query(
        query_exata,
        params={"nome": nome}
    ).result_set

    if resultado:
        return resultado

    query_parcial = """
    MATCH (e)
    WHERE e.name IS NOT NULL
      AND toLower(e.name) CONTAINS toLower($nome)
    RETURN
        labels(e) AS labels,
        e.id AS id,
        e.name AS name,
        e.type AS type
    LIMIT 20
    """

    return graph.ro_query(
        query_parcial,
        params={"nome": nome}
    ).result_set


# --------------------------------------------------
# 3. RECUPERAÇÃO DOS RELACIONAMENTOS E EVIDÊNCIAS
# --------------------------------------------------

def recuperar_relacionamentos(graph, entity_id):

    query = """
    MATCH (e {id: $entity_id})-[r]-(related)

    WHERE type(r) IN [
        'USES',
        'BELONGS_TO',
        'TARGETS',
        'ASSOCIATED_WITH'
    ]

    OPTIONAL MATCH
        (c:Chunk {id: r.chunk_id})-[:PART_OF]->(d:Document)

    RETURN
        type(r) AS relationship,
        labels(related) AS related_labels,
        related.id AS related_id,
        related.name AS related_name,
        r.evidence AS relationship_evidence,
        c.text AS context,
        d.title AS document,
        d.url AS source

    LIMIT 50
    """

    return graph.ro_query(
        query,
        params={"entity_id": entity_id}
    ).result_set


# --------------------------------------------------
# 4. RECUPERAÇÃO DOS CHUNKS DIRETAMENTE ASSOCIADOS
# --------------------------------------------------

def recuperar_evidencias(graph, entity_id):

    query = """
    MATCH
        (e {id: $entity_id})
        -[:MENTIONED_IN]->
        (c:Chunk)
        -[:PART_OF]->
        (d:Document)

    RETURN
        d.title AS document,
        d.url AS source,
        c.text AS evidence

    LIMIT 10
    """

    return graph.ro_query(
        query,
        params={"entity_id": entity_id}
    ).result_set


# --------------------------------------------------
# 5. EXIBIÇÃO DOS RESULTADOS
# --------------------------------------------------

def exibir_resultados(entidade, relacionamentos, evidencias):

    print("\n" + "=" * 70)
    print("RESULTADO DA RECUPERAÇÃO")
    print("=" * 70)

    print(f"\nEntidade: {entidade[2]}")
    print(f"Tipo: {', '.join(entidade[0])}")
    print(f"ID: {entidade[1]}")

    print("\nRELACIONAMENTOS ENCONTRADOS")
    print("-" * 70)

    if not relacionamentos:
        print("Nenhum relacionamento semântico encontrado.")

    for item in relacionamentos:
        (
            relacao,
            labels,
            related_id,
            related_name,
            rel_evidence,
            contexto,
            documento,
            fonte
        ) = item

        nome = related_name or related_id or "Sem nome"
        tipo = ", ".join(labels or [])

        print(f"\n[{relacao}] -> {nome}")
        print(f"Tipo da entidade relacionada: {tipo}")

        if rel_evidence:
            print(f"Justificativa: {rel_evidence}")

        if contexto:
            print(f"Contexto: {contexto[:500]}...")

        if documento:
            print(f"Documento: {documento}")

        if fonte:
            print(f"Fonte: {fonte}")

    print("\nEVIDÊNCIAS DIRETAS")
    print("-" * 70)

    if not evidencias:
        print("Nenhuma evidência direta encontrada.")

    for documento, fonte, texto in evidencias:
        print(f"\nDocumento: {documento}")
        print(f"Fonte: {fonte}")
        print(f"Evidência: {(texto or '')[:700]}...")

    print("\n" + "=" * 70)
    print("FIM DA RECUPERAÇÃO")
    print("=" * 70)


# --------------------------------------------------
# 6. EXECUÇÃO
# --------------------------------------------------

def main():

    print("Conectando ao FalkorDB...")

    try:
        graph = conectar()

        print(f"Grafo selecionado: {GRAPH_NAME}")

        nome = input(
            "\nDigite o nome da entidade que deseja pesquisar: "
        ).strip()

        if not nome:
            print("Nome não informado.")
            return

        entidades = localizar_entidade(graph, nome)

        if not entidades:
            print("Nenhuma entidade encontrada.")
            return

        if len(entidades) > 1:
            print("\nMais de uma entidade encontrada:")

            for item in entidades:
                labels = ", ".join(item[0] or [])
                print(
                    f"ID: {item[1]} | "
                    f"Nome: {item[2]} | "
                    f"Tipo: {labels}"
                )

            entity_id = input(
                "\nDigite o ID da entidade desejada: "
            ).strip()

            selecionada = next(
                (item for item in entidades if item[1] == entity_id),
                None
            )

            if selecionada is None:
                print("ID não encontrado.")
                return

        else:
            selecionada = entidades[0]

        entity_id = selecionada[1]

        print("\nRecuperando relacionamentos...")

        relacionamentos = recuperar_relacionamentos(
            graph,
            entity_id
        )

        print("Recuperando evidências...")

        evidencias = recuperar_evidencias(
            graph,
            entity_id
        )

        exibir_resultados(
            selecionada,
            relacionamentos,
            evidencias
        )

    except Exception as erro:
        print(f"\nErro durante a recuperação: {erro}")


if __name__ == "__main__":
    main()
