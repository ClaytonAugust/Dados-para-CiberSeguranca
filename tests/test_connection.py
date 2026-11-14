"""Integration tests against the real FalkorDB from docker compose."""

import pytest
from redis.exceptions import ResponseError

from cti_graphrag.config import load_settings
from cti_graphrag.graph.client import get_graph, run_query

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def graph():
    return get_graph()


def test_connects_to_configured_graph(graph):
    assert graph.name == load_settings().graph_name
    assert run_query("RETURN 1 AS status", graph=graph).result_set == [[1]]


def test_parameter_is_treated_as_value(graph):
    malicious = "x' }) MATCH (n) DETACH DELETE n //"
    result = run_query("RETURN $value AS v", {"value": malicious}, graph=graph, read_only=True)
    assert result.result_set == [[malicious]]


def test_read_only_rejects_writes(graph):
    with pytest.raises(ResponseError, match="read-only"):
        run_query("CREATE (:ProbeNode {x: 1})", graph=graph, read_only=True)


def test_timeout_stops_slow_query(graph):
    with pytest.raises(ResponseError, match="timed out"):
        run_query("UNWIND range(1, 200000000) AS x RETURN count(x)", graph=graph, timeout_ms=5)
