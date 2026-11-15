
from collections import OrderedDict

from sentence_transformers import SentenceTransformer

from .graph_retriever import GraphRetriever


class HybridRetriever:
    """
    Recuperador híbrido:
    busca vetorial + recuperação de entidades + expansão do grafo.
    """

    MODEL_NAME = "intfloat/multilingual-e5-small"

    # Tipos de entidades que interessam à investigação CTI.
    RELEVANT_LABELS = {
        "Group",
        "Software",
        "Technique",
        "Tactic",
        "Vulnerability",
        "Product",
        "Vendor",
    }

    def __init__(self, graph, model=None):

        self.graph = graph

        # Permite reutilizar um modelo já carregado.
        self.model = model or SentenceTransformer(
            self.MODEL_NAME,
            device="cpu"
        )

        self.graph_retriever = GraphRetriever(graph)

    # --------------------------------------------------
    # 1. BUSCA VETORIAL
    # --------------------------------------------------

    def semantic_search(self, question, top_k=5):

        query_vector = self.model.encode(
            "query: " + question,
            convert_to_numpy=True,
            normalize_embeddings=True
        ).tolist()

        query = """
        CALL db.idx.vector.queryNodes(
            'Chunk',
            'embedding',
            $k,
            vecf32($vector)
        )
        YIELD node, score

        OPTIONAL MATCH
            (node)-[:PART_OF]->(d:Document)

        RETURN
            node.id AS chunk_id,
            node.text AS text,
            d.title AS document,
            d.url AS source,
            (1 - score) AS similarity

        ORDER BY similarity DESC
        """

        rows = self.graph.ro_query(
            query,
            params={
                "k": top_k,
                "vector": query_vector
            }
        ).result_set

        return [
            {
                "chunk_id": row[0],
                "text": row[1],
                "document": row[2],
                "source": row[3],
                "similarity": float(row[4])
            }
            for row in rows
        ]

    # --------------------------------------------------
    # 2. IDENTIFICAR ENTIDADES NOS CHUNKS
    # --------------------------------------------------

    def find_entities(self, semantic_results, max_entities=20):

        chunk_ids = [
            item["chunk_id"]
            for item in semantic_results
        ]

        if not chunk_ids:
            return []

        scores = {
            item["chunk_id"]: item["similarity"]
            for item in semantic_results
        }

        query = """
        MATCH (e)-[:MENTIONED_IN]->(c:Chunk)

        WHERE c.id IN $chunk_ids

        RETURN DISTINCT
            e.id,
            e.name,
            labels(e),
            e.type,
            c.id
        """

        rows = self.graph.ro_query(
            query,
            params={"chunk_ids": chunk_ids}
        ).result_set

        entities = {}

        for row in rows:

            entity_id, name, labels, entity_type, chunk_id = row

            if not entity_id:
                continue

            if not self.RELEVANT_LABELS.intersection(labels or []):
                continue

            score = scores.get(chunk_id, 0.0)

            if entity_id not in entities:

                entities[entity_id] = {
                    "id": entity_id,
                    "name": name,
                    "labels": labels,
                    "type": entity_type,
                    "similarity": score
                }

            else:

                entities[entity_id]["similarity"] = max(
                    entities[entity_id]["similarity"],
                    score
                )

        ordered = sorted(
            entities.values(),
            key=lambda item: item["similarity"],
            reverse=True
        )

        return ordered[:max_entities]

    # --------------------------------------------------
    # 3. EXPANDIR RELACIONAMENTOS
    # --------------------------------------------------

    def expand_graph(self, entities):

        relationships = OrderedDict()

        for entity in entities:

            related = self.graph_retriever.get_relationships(
                entity["id"]
            )

            for item in related:

                key = (
                    item["relationship"],
                    item["source"]["id"],
                    item["target"]["id"]
                )

                if key not in relationships:

                    relationships[key] = {
                        "relationship": item["relationship"],
                        "source": item["source"],
                        "target": item["target"],
                        "seed_similarity": entity["similarity"],
                        "seed_entities": set(),
                        "evidences": []
                    }

                current = relationships[key]

                current["seed_similarity"] = max(
                    current["seed_similarity"],
                    entity["similarity"]
                )

                current["seed_entities"].add(
                    entity["name"]
                )

                existing_chunks = {
                    evidence["chunk_id"]
                    for evidence in current["evidences"]
                }

                for evidence in item["evidences"]:

                    if evidence["chunk_id"] not in existing_chunks:

                        current["evidences"].append(evidence)

                        existing_chunks.add(
                            evidence["chunk_id"]
                        )

        result = list(relationships.values())

        for item in result:
            item["seed_entities"] = sorted(
                item["seed_entities"]
            )

        return sorted(
            result,
            key=lambda item: item["seed_similarity"],
            reverse=True
        )

    # --------------------------------------------------
    # 4. EXECUTAR RECUPERAÇÃO HÍBRIDA
    # --------------------------------------------------

    def retrieve(self, question, top_k=5, max_entities=20):

        # Primeira etapa: recuperação semântica.
        semantic_results = self.semantic_search(
            question,
            top_k
        )

        if not semantic_results:
            return {
                "semantic_results": [],
                "entities": [],
                "relationships": []
            }

        # Segunda etapa: identificar entidades.
        entities = self.find_entities(
            semantic_results,
            max_entities
        )

        # Terceira etapa: expandir o grafo.
        relationships = self.expand_graph(
            entities
        )

        return {
            "semantic_results": semantic_results,
            "entities": entities,
            "relationships": relationships
        }
