
import re
import time

from cti_graphrag.retrieval import HybridRetriever
from cti_graphrag.llm.client import gerar_resposta

from cti_graphrag.pipeline.schemas import (
    Answer,
    EvidencePath,
    GraphNode,
    GraphEdge
)


class GraphRAGPipeline:
    """
    Orquestra a recuperação híbrida, a montagem do contexto,
    a geração pelo LLM e a validação das citações.
    """

    def __init__(self, graph, model=None):

        self.retriever = HybridRetriever(
            graph,
            model=model
        )

    @staticmethod
    def _label(labels):

        if isinstance(labels, list) and labels:
            return labels[0]

        return "Entity"

    def answer(
        self,
        question: str,
        top_k: int = 5,
        max_entities: int = 20,
        max_relationships: int = 12
    ) -> Answer:

        start = time.perf_counter()

        # --------------------------------------------------
        # 1. RECUPERAÇÃO HÍBRIDA
        # --------------------------------------------------

        result = self.retriever.retrieve(
            question,
            top_k=top_k,
            max_entities=max_entities
        )

        semantic_results = result.get(
            "semantic_results", []
        )

        relationships = result.get(
            "relationships", []
        )

        cypher = result.get("cypher", "")

        # --------------------------------------------------
        # 2. ORGANIZAR NÓS, ARESTAS E CAMINHOS
        # --------------------------------------------------

        nodes = {}
        edges = {}
        paths = []

        context_parts = []
        covered_chunks = set()

        def add_node(entity):

            if not entity:
                return

            entity_id = entity.get("id")

            if not entity_id:
                return

            labels = entity.get(
                "labels",
                []
            )

            nodes[entity_id] = GraphNode(
                id=str(entity_id),
                label=self._label(labels),
                name=str(
                    entity.get("name") or entity_id
                )
            )

        # Entidades identificadas nos chunks.
        for entity in result.get("entities", []):
            add_node(entity)

        # --------------------------------------------------
        # 3. CONTEXTO A PARTIR DOS RELACIONAMENTOS
        # --------------------------------------------------

        for relationship in relationships[:max_relationships]:

            source = relationship["source"]
            target = relationship["target"]

            relation_type = relationship["relationship"]

            evidences = relationship.get(
                "evidences", []
            )[:3]

            if not evidences:
                continue

            source_id = str(source["id"])
            target_id = str(target["id"])

            add_node(source)
            add_node(target)

            edge_key = (
                source_id,
                target_id,
                relation_type
            )

            edges[edge_key] = GraphEdge(
                **{
                    "from": source_id,
                    "to": target_id,
                    "type": relation_type
                }
            )

            path_number = len(paths) + 1
            path_id = f"P{path_number}"

            chunk_ids = []

            context_parts.append(
                f"\n[{path_id}]"
            )

            context_parts.append(
                f"Relacionamento: {source.get('name') or source_id} "
                f"--[{relation_type}]--> "
                f"{target.get('name') or target_id}"
            )

            for evidence in evidences:

                chunk_id = evidence.get("chunk_id")

                if chunk_id:
                    chunk_ids.append(str(chunk_id))
                    covered_chunks.add(str(chunk_id))

                if evidence.get("relationship_evidence"):
                    context_parts.append(
                        "Evidência registrada: "
                        + str(
                            evidence["relationship_evidence"]
                        )
                    )

                if evidence.get("text"):
                    context_parts.append(
                        "Trecho documental: "
                        + str(evidence["text"])[:1500]
                    )

                if evidence.get("document"):
                    context_parts.append(
                        "Documento: "
                        + str(evidence["document"])
                    )

                if evidence.get("source_url"):
                    context_parts.append(
                        "URL: "
                        + str(evidence["source_url"])
                    )

                if evidence.get("source"):
                    context_parts.append(
                        "Origem do relacionamento: "
                        + str(evidence["source"])
                    )

            paths.append(
                EvidencePath(
                    id=path_id,
                    nodes=[
                        source_id,
                        target_id
                    ],
                    rels=[relation_type],
                    chunk_ids=list(dict.fromkeys(chunk_ids))
                )
            )

        # --------------------------------------------------
        # 4. CONTEXTO DOS CHUNKS SEM RELACIONAMENTO EXPANDIDO
        # --------------------------------------------------

        for item in semantic_results:

            chunk_id = item.get("chunk_id")

            if not chunk_id:
                continue

            if str(chunk_id) in covered_chunks:
                continue

            path_number = len(paths) + 1
            path_id = f"P{path_number}"

            document = item.get("document")
            source_url = item.get("source")

            paths.append(
                EvidencePath(
                    id=path_id,
                    nodes=[str(chunk_id)],
                    rels=[],
                    chunk_ids=[str(chunk_id)]
                )
            )

            nodes[str(chunk_id)] = GraphNode(
                id=str(chunk_id),
                label="Chunk",
                name=str(document or chunk_id)
            )

            context_parts.append(
                f"\n[{path_id}]"
            )

            context_parts.append(
                "Trecho recuperado por busca semântica "
                "(sem relacionamento expandido):"
            )

            context_parts.append(
                str(item.get("text") or "")[:1500]
            )

            context_parts.append(
                f"Documento: {document}"
            )

            context_parts.append(
                f"URL: {source_url}"
            )

        # --------------------------------------------------
        # 5. VERIFICAR SE EXISTEM EVIDÊNCIAS
        # --------------------------------------------------

        if not context_parts:

            return Answer(
                answer="Não encontrei isso no grafo.",
                paths=[],
                nodes=list(nodes.values()),
                edges=[],
                cypher=cypher,
                confidence=0.0,
                latency_ms=int(
                    (time.perf_counter() - start) * 1000
                )
            )

        context = "\n".join(context_parts)

        # --------------------------------------------------
        # 6. GERAR RESPOSTA COM O GEMINI
        # --------------------------------------------------

        generated_answer = gerar_resposta(
            question,
            context
        )

        # --------------------------------------------------
        # 7. VALIDAR CITAÇÕES
        # --------------------------------------------------

        valid_references = {
            path.id
            for path in paths
        }

        used_references = set(
            re.findall(
                r"\[(P\d+)\]",
                generated_answer
            )
        )

        invalid_references = (
            used_references - valid_references
        )

        if not used_references or invalid_references:

            generated_answer = (
                "Não foi possível validar as referências "
                "da resposta gerada. Consulte as evidências "
                "recuperadas antes de utilizar essa informação."
            )

        # --------------------------------------------------
        # 8. CALCULAR INDICADOR DE RECUPERAÇÃO
        # --------------------------------------------------

        similarities = [
            max(
                0.0,
                min(1.0, float(item["similarity"]))
            )
            for item in semantic_results
            if item.get("similarity") is not None
        ]

        confidence = (
            sum(similarities) / len(similarities)
            if similarities else 0.0
        )

        latency = int(
            (time.perf_counter() - start) * 1000
        )

        return Answer(
            answer=generated_answer,
            paths=paths,
            nodes=list(nodes.values()),
            edges=list(edges.values()),
            cypher=cypher,
            confidence=round(confidence, 4),
            latency_ms=latency
        )
