"""Minimal FalkorDB client: one shared connection and parameterized queries."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from falkordb import FalkorDB, Graph
from falkordb.query_result import QueryResult

from cti_graphrag.config import Settings, load_settings

DEFAULT_TIMEOUT_MS = 10_000
CONNECT_TIMEOUT_S = 5


@lru_cache(maxsize=4)
def _connect(host: str, port: int) -> FalkorDB:
    return FalkorDB(host=host, port=port, socket_connect_timeout=CONNECT_TIMEOUT_S)


def get_graph(name: str | None = None, settings: Settings | None = None) -> Graph:
    """Return a graph handle; defaults to GRAPH_NAME from the .env."""
    settings = settings or load_settings()
    return _connect(settings.falkordb_host, settings.falkordb_port).select_graph(
        name or settings.graph_name
    )


def run_query(
    cypher: str,
    params: dict[str, Any] | None = None,
    *,
    graph: Graph | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    read_only: bool = False,
) -> QueryResult:
    """Run a Cypher query with parameters and a server-side timeout.

    User values must go in ``params``, never concatenated into ``cypher``.
    With ``read_only=True`` the query runs through GRAPH.RO_QUERY, so the
    server itself rejects any write.
    """
    if not isinstance(cypher, str) or not cypher.strip():
        raise ValueError("cypher must be a non-empty string")
    if params is not None and not isinstance(params, dict):
        raise TypeError("params must be a dict")
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise ValueError("timeout_ms must be a positive integer")

    graph = graph if graph is not None else get_graph()
    execute = graph.ro_query if read_only else graph.query
    return execute(cypher, params or {}, timeout=timeout_ms)
