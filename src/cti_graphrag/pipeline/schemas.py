
from pydantic import BaseModel, Field


class EvidencePath(BaseModel):
    id: str
    nodes: list[str] = Field(default_factory=list)
    rels: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    name: str


class GraphEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str = Field(alias="to")
    type: str


class Answer(BaseModel):
    answer: str

    paths: list[EvidencePath] = Field(
        default_factory=list
    )

    nodes: list[GraphNode] = Field(
        default_factory=list
    )

    edges: list[GraphEdge] = Field(
        default_factory=list
    )

    cypher: str = ""

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0
    )

    latency_ms: int = 0
