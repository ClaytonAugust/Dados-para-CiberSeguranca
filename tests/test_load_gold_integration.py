"""Loads the real gold graph twice into a scratch graph: counts must not change."""

import pytest

from cti_graphrag.graph.client import get_graph, run_query
from cti_graphrag.ingest.load_gold import load_gold

pytestmark = pytest.mark.integration


@pytest.fixture
def scratch_graph():
    graph = get_graph("test_cti_gold_idempotency")
    yield graph
    graph.delete()


def test_load_twice_gives_same_counts(scratch_graph):
    first = load_gold(scratch_graph)
    second = load_gold(scratch_graph)
    assert first["nodes_by_label"] == second["nodes_by_label"]
    assert first["edges_by_type"] == second["edges_by_type"]
    assert second["write"].get("nodes_created", 0) == 0
    assert second["write"].get("relationships_created", 0) == 0
    assert first["nodes_by_label"]["Group"] == 80


def test_reset_reloads_with_same_counts(scratch_graph):
    first = load_gold(scratch_graph)
    run_query("CREATE (:Group {id: 'group:stale'})", graph=scratch_graph)
    after_reset = load_gold(scratch_graph, reset=True)
    assert after_reset["reset"] is True
    assert after_reset["nodes_by_label"] == first["nodes_by_label"]
    assert after_reset["edges_by_type"] == first["edges_by_type"]


def test_reset_on_missing_graph(scratch_graph):
    assert load_gold(scratch_graph, reset=True)["reset"] is False
