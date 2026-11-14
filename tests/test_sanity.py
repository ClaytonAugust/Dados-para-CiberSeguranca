"""Sanity check: expected counts from the JSON, and the real check on a scratch graph."""

import pytest

from cti_graphrag.graph.client import get_graph
from cti_graphrag.ingest.load_gold import load_gold
from cti_graphrag.ingest.models import AptGroup, AttackTechnique, Malware
from cti_graphrag.ingest.read import Dataset, load_dataset
from cti_graphrag.ingest.sanity import Check, expected_counts, run_checks


def test_expected_counts_from_json_fields():
    apt = AptGroup.model_validate(
        {
            "name": "A",
            "slug": "a",
            "suspected_origin": "Iran",
            "tools": [{"name": "X"}, {"name": "Y"}],
            "attack_techniques": [
                {"id": "T1592.002", "tactic": "Reconnaissance"},
                {"id": "T1592.002", "tactic": "Reconnaissance"},  # repeated pair
            ],
        }
    )
    malware = Malware.model_validate(
        {
            "name": "X",
            "slug": "x",
            "attack_techniques": [{"id": "T1003", "tactic": "Credential Access"}],
        }
    )
    page = AttackTechnique.model_validate(
        {"name": "P", "slug": "p", "mitre_attack_id": "T1003", "tactic": "Credential Access"}
    )
    e = expected_counts(Dataset([apt], [], [malware], [page]))
    assert e["records"] == 3
    assert e["techniques"] == 3  # T1592.002, T1003 and the missing parent T1592
    assert e["derived_parents"] == 1
    assert e["group_technique_pairs"] == 1
    assert e["tactic_pairs"] == 2
    assert e["group_software_refs"] == 2
    assert e["origins"] == 1


def test_check_status():
    assert Check("x", 1, 1, True).status == "OK"
    assert Check("x", 1, 2, True).status == "FALHA"
    assert Check("x", 1, 2, False).status == "DIFERENTE (explicado)"


@pytest.mark.integration
def test_sanity_on_fresh_load():
    graph = get_graph("test_cti_gold_sanity")
    try:
        load_gold(graph, reset=True)
        checks = run_checks(graph, load_dataset())
        failures = [c.name for c in checks if c.exact and not c.ok]
        assert failures == []
    finally:
        graph.delete()
