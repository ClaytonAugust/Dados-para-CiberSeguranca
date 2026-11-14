"""Unit tests for the schema reader, the in-memory gold graph and the load plan."""

import pytest

from cti_graphrag.graph.schema import SchemaError, load_schema
from cti_graphrag.ingest.build_gold import GoldGraph, build_gold, tactic_id
from cti_graphrag.ingest.load_gold import plan_load
from cti_graphrag.ingest.models import AptGroup, AttackTechnique, Malware, RansomwareGroup
from cti_graphrag.ingest.read import Dataset

SCHEMA_V1_LIKE = """
schema_version: "1.0"
graphs: {gold: cti_gold}
labels:
  Group: {}
  Software: {}
  Technique: {}
  Tactic: {}
  Country: {}
  Document: {}
  Vendor: {enabled: false}
relationships:
  USES:
    allowed_endpoints:
      - {from: Group, to: Software}
      - {from: Group, to: Technique}
  ASSOCIATED_WITH:
    allowed_endpoints:
      - {from: Group, to: Country}
  MADE_BY:
    enabled: false
    allowed_endpoints:
      - {from: Software, to: Vendor}
"""


@pytest.fixture
def schema(tmp_path):
    path = tmp_path / "schema.yaml"
    path.write_text(SCHEMA_V1_LIKE, encoding="utf-8")
    return load_schema(path)


def test_schema_reader_skips_disabled(schema):
    assert "Vendor" not in schema.labels
    assert "MADE_BY" not in schema.relationships
    assert schema.allows_edge("USES", "Group", "Software")
    assert not schema.allows_edge("USES", "Software", "Technique")


def test_schema_reader_rejects_bad_names(tmp_path):
    path = tmp_path / "schema.yaml"
    path.write_text("labels:\n  bad_label: {}\n", encoding="utf-8")
    with pytest.raises(SchemaError):
        load_schema(path)


def test_real_schema_has_no_describes():
    assert "DESCRIBES" not in load_schema().relationships


def test_edges_are_deduplicated_and_keep_all_docs():
    gold = GoldGraph()
    a, b = ("Group", "group:a"), ("Software", "software:b")
    gold.add_edge("USES", a, b, "doc:1", "structured:apt-groups.tools")
    gold.add_edge("USES", a, b, "doc:2", "structured:malware.used_by")
    (edge,) = gold.edges.values()
    assert edge.props["doc_id"] == "doc:1"
    assert edge.props["doc_ids"] == ["doc:1", "doc:2"]
    assert edge.props["chunk_id"] == ""
    assert edge.props["confidence"] == 1.0
    assert edge.props["source"] == "gold"


def test_tactic_id():
    assert tactic_id("Command and Control") == "tactic:command_and_control"


@pytest.fixture
def tiny_dataset():
    apt = AptGroup.model_validate(
        {
            "name": "Andariel",
            "slug": "andariel",
            "aliases": [{"name": "Silent Chollima"}],
            "suspected_origin": "North Korea",
            "target_sectors": ["Defense", "Worldwide"],
            "tools": [{"name": "MagicRAT", "type": "RAT"}, {"name": "Mimikatz"}],
            "attack_techniques": [
                {
                    "id": "T1592.002",
                    "name": "Gather Victim Host Information: Software",
                    "tactic": "Reconnaissance",
                }
            ],
        }
    )
    ransom = RansomwareGroup.model_validate({"name": "Akira", "slug": "akira"})
    malware = Malware.model_validate(
        {
            "name": "Mimikatz",
            "slug": "mimikatz",
            "used_by": [{"name": "Andariel", "url": "https://x/apt-groups/andariel/"}],
        }
    )
    page = AttackTechnique.model_validate(
        {"name": "Phishing (T1566): ATT&CK Technique", "slug": "t1566", "mitre_attack_id": "T1566"}
    )
    return Dataset([apt], [ransom], [malware], [page])


def test_build_gold_ids_and_properties(tiny_dataset):
    gold = build_gold(tiny_dataset)
    group = gold.nodes["Group"]["group:andariel"]
    assert group["kind"] == "apt"
    assert group["sectors_raw"] == ["Worldwide"]
    assert gold.nodes["Software"]["software:magicrat"]["has_page"] is False
    assert gold.nodes["Software"]["software:mimikatz"]["has_page"] is True
    assert gold.nodes["Technique"]["T1592"]["name"] == "Gather Victim Host Information"
    assert gold.nodes["Technique"]["T1566"]["name"] == "Phishing"
    assert "doc:brandefense:apt-groups:andariel" in gold.nodes["Document"]
    origin = gold.edges[("ASSOCIATED_WITH", "group:andariel", "country:KP")]
    assert origin.props["attribution"] == "attributed"
    assert origin.props["evidence"] == "structured:apt-groups.suspected_origin"
    mimikatz = gold.edges[("USES", "group:andariel", "software:mimikatz")]
    assert mimikatz.props["doc_ids"] == [
        "doc:brandefense:apt-groups:andariel",
        "doc:brandefense:malware:mimikatz",
    ]
    assert ("SUBTECHNIQUE_OF", "T1592.002", "T1592") in gold.edges


def test_plan_skips_what_the_schema_lacks(tiny_dataset, schema):
    plan = plan_load(build_gold(tiny_dataset), schema)
    assert plan.skipped_labels == {"Sector": 1}
    assert plan.skipped_edges["DESCRIBES (Document->Group)"] == 2
    assert plan.skipped_edges["BELONGS_TO (Technique->Tactic)"] == 1
    assert "Group" in plan.nodes
    assert ("USES", "Group", "Software") in plan.edges
