
from collections import OrderedDict


class GraphRetriever:
    """
    Recuperador de informações do grafo CTI.

    Responsável por localizar entidades, percorrer
    relacionamentos e recuperar evidências documentais.
    """

    def __init__(self, graph):
        self.graph = graph
        self.last_queries = []

    # --------------------------------------------------
    # 1. BUSCAR ENTIDADES
    # --------------------------------------------------

    def search_entities(self, term):
        """Busca entidades por nome ou alias."""

        exact_query = """
        MATCH (e)
        WHERE e.name IS NOT NULL
          AND (
            toLower(e.name) = toLower($term)
            OR ANY(
                alias IN coalesce(e.aliases, [])
                WHERE toLower(alias) = toLower($term)
            )
          )
        RETURN
            labels(e),
            e.id,
            e.name,
            e.type
        LIMIT 20
        """

        rows = self.graph.ro_query(
            exact_query,
            params={"term": term}
        ).result_set

        if not rows:
            partial_query = """
            MATCH (e)
            WHERE e.name IS NOT NULL
              AND (
                toLower(e.name) CONTAINS toLower($term)
                OR ANY(
                    alias IN coalesce(e.aliases, [])
                    WHERE toLower(alias) CONTAINS toLower($term)
                )
              )
            RETURN
                labels(e),
                e.id,
                e.name,
                e.type
            LIMIT 20
            """

            rows = self.graph.ro_query(
                partial_query,
                params={"term": term}
            ).result_set

        return [
            {
                "labels": row[0],
                "id": row[1],
                "name": row[2],
                "type": row[3]
            }
            for row in rows
        ]

    # --------------------------------------------------
    # 2. RECUPERAR DADOS DA ENTIDADE
    # --------------------------------------------------

    def get_entity(self, entity_id):

        query = """
        MATCH (e {id: $entity_id})
        RETURN
            labels(e),
            e.id,
            e.name,
            e.type,
            e.description
        LIMIT 1
        """

        rows = self.graph.ro_query(
            query,
            params={"entity_id": entity_id}
        ).result_set

        if not rows:
            return None

        row = rows[0]

        return {
            "labels": row[0],
            "id": row[1],
            "name": row[2],
            "type": row[3],
            "description": row[4]
        }

    # --------------------------------------------------
    # 3. RECUPERAR RELACIONAMENTOS
    # --------------------------------------------------

    
    def get_relationships(self, entity_id):

        query = """
        MATCH (source)-[r]->(target)

        WHERE
            (source.id = $entity_id OR target.id = $entity_id)
            AND type(r) IN [
                'USES',
                'BELONGS_TO',
                'SUBTECHNIQUE_OF',
                'AFFECTS',
                'MADE_BY',
                'EXPLOITS',
                'TARGETS',
                'ASSOCIATED_WITH'
            ]

        OPTIONAL MATCH
            (c:Chunk {id: r.chunk_id})
            -[:PART_OF]->
            (d:Document)

        RETURN
            type(r),
            source.id,
            source.name,
            labels(source),
            target.id,
            target.name,
            labels(target),
            r.evidence,
            r.chunk_id,
            c.text,
            d.title,
            d.url,
            r.source,
            r.confidence

        LIMIT 200
        """

        self.last_queries.append(query.strip())

        rows = self.graph.ro_query(
            query,
            params={"entity_id": entity_id}
        ).result_set

        grouped = OrderedDict()

        for row in rows:

            (
                relationship,
                source_id,
                source_name,
                source_labels,
                target_id,
                target_name,
                target_labels,
                relationship_evidence,
                chunk_id,
                context,
                document,
                source_url,
                provenance_source,
                confidence
            ) = row

            key = (
                relationship,
                source_id,
                target_id
            )

            if key not in grouped:
                grouped[key] = {
                    "relationship": relationship,
                    "source": {
                        "id": source_id,
                        "name": source_name,
                        "labels": source_labels
                    },
                    "target": {
                        "id": target_id,
                        "name": target_name,
                        "labels": target_labels
                    },
                    "evidences": []
                }

            evidence = {
                "chunk_id": chunk_id,
                "text": context,
                "document": document,
                "source_url": source_url,
                "relationship_evidence": relationship_evidence,
                "source": provenance_source,
                "confidence": confidence
            }

            existing_ids = {
                item["chunk_id"]
                for item in grouped[key]["evidences"]
            }

            if chunk_id not in existing_ids:
                grouped[key]["evidences"].append(evidence)

        return list(grouped.values())


    # --------------------------------------------------
    # 4. RECUPERAR EVIDÊNCIAS DIRETAS
    # --------------------------------------------------

    def get_evidences(self, entity_id):

        query = """
        MATCH
            (e {id: $entity_id})
            -[:MENTIONED_IN]->
            (c:Chunk)
            -[:PART_OF]->
            (d:Document)

        RETURN
            c.id,
            d.title,
            d.url,
            c.text

        LIMIT 30
        """

        rows = self.graph.ro_query(
            query,
            params={"entity_id": entity_id}
        ).result_set

        evidences = []

        for row in rows:
            evidences.append({
                "chunk_id": row[0],
                "document": row[1],
                "source_url": row[2],
                "text": row[3]
            })

        return evidences

    # --------------------------------------------------
    # 5. RECUPERAÇÃO COMPLETA
    # --------------------------------------------------

    def retrieve(self, entity_id):

        entity = self.get_entity(entity_id)

        if not entity:
            return None

        relationships = self.get_relationships(entity_id)
        evidences = self.get_evidences(entity_id)

        return {
            "entity": entity,
            "relationships": relationships,
            "evidences": evidences
        }
