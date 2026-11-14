"""Unit tests for graph.client with a fake graph (no database needed)."""

import pytest

from cti_graphrag.graph.client import DEFAULT_TIMEOUT_MS, run_query


class FakeGraph:
    def __init__(self):
        self.calls = []

    def query(self, q, params=None, timeout=None):
        self.calls.append(("query", q, params, timeout))
        return "result"

    def ro_query(self, q, params=None, timeout=None):
        self.calls.append(("ro_query", q, params, timeout))
        return "ro-result"


def test_passes_params_and_default_timeout():
    graph = FakeGraph()
    assert run_query("RETURN $x", {"x": 1}, graph=graph) == "result"
    assert graph.calls == [("query", "RETURN $x", {"x": 1}, DEFAULT_TIMEOUT_MS)]


def test_none_params_become_empty_dict():
    graph = FakeGraph()
    run_query("RETURN 1", graph=graph)
    assert graph.calls[0][2] == {}


def test_custom_timeout_is_forwarded():
    graph = FakeGraph()
    run_query("RETURN 1", graph=graph, timeout_ms=250)
    assert graph.calls[0][3] == 250


def test_read_only_uses_ro_query():
    graph = FakeGraph()
    assert run_query("MATCH (n) RETURN n", graph=graph, read_only=True) == "ro-result"
    assert graph.calls[0][0] == "ro_query"


def test_rejects_non_dict_params():
    with pytest.raises(TypeError):
        run_query("RETURN 1", "x=1", graph=FakeGraph())


@pytest.mark.parametrize("cypher", ["", "   ", None])
def test_rejects_empty_cypher(cypher):
    with pytest.raises(ValueError):
        run_query(cypher, graph=FakeGraph())


@pytest.mark.parametrize("timeout", [0, -1, 1.5])
def test_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        run_query("RETURN 1", graph=FakeGraph(), timeout_ms=timeout)
