"""Demonstrações complementares de travessia multi-hop e PageRank.

A travessia executa caminhos dirigidos de exatamente dois relacionamentos.
O PageRank é calculado localmente com NetworkX sobre até 50 mil arestas
lidas do FalkorDB; nenhuma informação é gravada ou alterada no banco.
"""

from __future__ import annotations


def two_hop_paths(graph, start_id: str, limit: int = 50) -> list[dict]:
    """Retorna caminhos start -> intermediário -> destino (dois saltos)."""
    if not start_id or not start_id.strip():
        raise ValueError("Informe o ID da entidade inicial.")

    safe_limit = max(1, min(int(limit), 200))
    query = f"""
    MATCH (a)-[r1]->(b)-[r2]->(c)
    WHERE a.id = $start_id
      AND a.id IS NOT NULL AND b.id IS NOT NULL AND c.id IS NOT NULL
      AND a.id <> b.id AND b.id <> c.id
    RETURN DISTINCT
        a.id AS start_id, coalesce(a.name, a.id) AS start_name,
        type(r1) AS relation_1,
        b.id AS middle_id, coalesce(b.name, b.id) AS middle_name,
        type(r2) AS relation_2,
        c.id AS end_id, coalesce(c.name, c.id) AS end_name,
        labels(c) AS end_labels
    ORDER BY end_name
    LIMIT {safe_limit}
    """
    rows = graph.ro_query(query, params={"start_id": start_id.strip()}).result_set
    results = []
    for row in rows:
        results.append({
            "origem": row[1],
            "relacionamento_1": row[2],
            "intermediario": row[4],
            "relacionamento_2": row[5],
            "destino": row[7],
            "id_destino": row[6],
            "tipo_destino": ", ".join(row[8] or []),
        })
    return results


def pagerank_top_nodes(graph, top_k: int = 10, max_edges: int = 50000) -> dict:
    """Calcula PageRank nos relacionamentos exportados do FalkorDB.

    O limite existe para evitar consumir memória excessiva em bases grandes.
    A saída informa se a consulta atingiu esse limite.
    """
    try:
        import networkx as nx
    except ImportError as exc:
        raise RuntimeError("Instale NetworkX: pip install networkx") from exc

    safe_edges = max(1, min(int(max_edges), 50000))
    safe_top = max(1, min(int(top_k), 50))
    query = f"""
    MATCH (a)-[r]->(b)
    WHERE a.id IS NOT NULL AND b.id IS NOT NULL
    RETURN a.id, coalesce(a.name, a.id), labels(a),
           type(r), b.id, coalesce(b.name, b.id), labels(b)
    LIMIT {safe_edges}
    """
    rows = graph.ro_query(query).result_set
    network = nx.DiGraph()

    for row in rows:
        source_id, source_name, source_labels, _, target_id, target_name, target_labels = row
        if not source_id or not target_id:
            continue
        network.add_node(
            str(source_id),
            name=str(source_name or source_id),
            label=", ".join(source_labels or []),
        )
        network.add_node(
            str(target_id),
            name=str(target_name or target_id),
            label=", ".join(target_labels or []),
        )
        if network.has_edge(str(source_id), str(target_id)):
            network[str(source_id)][str(target_id)]["weight"] += 1.0
        else:
            network.add_edge(str(source_id), str(target_id), weight=1.0)

    if network.number_of_edges() == 0:
        return {
            "items": [], "nodes": network.number_of_nodes(),
            "edges": 0, "truncated": False,
        }

    scores = nx.pagerank(network, alpha=0.85, weight="weight", max_iter=200)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:safe_top]
    items = [
        {
            "nome": network.nodes[node_id].get("name", node_id),
            "id": node_id,
            "tipo": network.nodes[node_id].get("label", ""),
            "PageRank": round(float(score), 8),
        }
        for node_id, score in ranked
    ]
    return {
        "items": items,
        "nodes": network.number_of_nodes(),
        "edges": network.number_of_edges(),
        "truncated": len(rows) >= safe_edges,
    }
