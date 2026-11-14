"""Unit tests for the reading-level normalizers and the dataset reader.

The reader tests use data/raw/, which is versioned in Git (no internet needed).
"""

import json

import pytest
from pydantic import ValidationError

from cti_graphrag.ingest.models import (
    AptGroup,
    TechniqueRef,
    blank_to_none,
    canonical_tactic,
    normalize_aliases,
    split_tactics,
)
from cti_graphrag.ingest.read import DatasetError, load_dataset, read_file


# --- aliases: objects (APT) and strings (ransomware/malware) ----------------
def test_aliases_from_objects_and_strings():
    raw = [{"name": "Silent Chollima", "source": "MITRE"}, "Onyx Sleet", {"name": " "}, ""]
    assert normalize_aliases(raw) == ["Silent Chollima", "Onyx Sleet"]


def test_aliases_deduplicate_case_insensitive():
    assert normalize_aliases(["Lazarus", "lazarus", "LAZARUS "]) == ["Lazarus"]


def test_aliases_none_is_empty_list():
    assert normalize_aliases(None) == []


# --- empty strings -> None ---------------------------------------------------
@pytest.mark.parametrize("raw,expected", [("", None), ("   ", None), (" Iran ", "Iran"), (3, 3)])
def test_blank_to_none(raw, expected):
    assert blank_to_none(raw) == expected


# --- tactics: combined values and case ---------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Command And Control", "Command and Control"),
        ("credential access", "Credential Access"),
        ("  Defense Impairment ", "Defense Impairment"),
    ],
)
def test_canonical_tactic(raw, expected):
    assert canonical_tactic(raw) == expected


def test_split_combined_tactics():
    raw = "Stealth, Persistence, Privilege Escalation, Initial Access"
    expected = ["Stealth", "Persistence", "Privilege Escalation", "Initial Access"]
    assert split_tactics(raw) == expected


def test_split_tactics_removes_duplicates_and_blanks():
    assert split_tactics("Discovery, , discovery") == ["Discovery"]


def test_technique_ref_uses_tactic_alias_and_uppercases_id():
    raw = {"tactic": "Collection, Credential Access", "id": "t1056.001"}
    ref = TechniqueRef.model_validate(raw)
    assert ref.id == "T1056.001"
    assert ref.tactics == ["Collection", "Credential Access"]


# --- model ---------------------------------------------------------------------
def test_apt_group_normalizes_fields():
    group = AptGroup.model_validate(
        {
            "name": "X",
            "slug": "x",
            "status": "",
            "suspected_origin": " ",
            "aliases": [{"name": "Y", "source": "s"}],
        }
    )
    assert group.status is None
    assert group.suspected_origin is None
    assert group.aliases == ["Y"]


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        AptGroup.model_validate({"name": "X", "slug": "x", "new_field": 1})


# --- reader ----------------------------------------------------------------------
def test_reader_rejects_meta_count_mismatch(tmp_path):
    path = tmp_path / "apt-groups.json"
    path.write_text(json.dumps({"meta": {"count": 2}, "items": [{"name": "A", "slug": "a"}]}))
    with pytest.raises(DatasetError, match="meta.count=2"):
        read_file(path, AptGroup)


def test_reader_rejects_duplicate_slugs(tmp_path):
    path = tmp_path / "apt-groups.json"
    items = [{"name": "A", "slug": "a"}, {"name": "B", "slug": "a"}]
    path.write_text(json.dumps({"meta": {"count": 2}, "items": items}))
    with pytest.raises(DatasetError, match="duplicados"):
        read_file(path, AptGroup)


def test_load_real_dataset_counts():
    dataset = load_dataset()
    assert dataset.counts() == {
        "apt-groups": 52,
        "ransomware-groups": 28,
        "malware": 59,
        "attack-techniques": 42,
    }


def test_real_dataset_has_no_combined_or_miscased_tactics():
    dataset = load_dataset()
    refs = [t for g in dataset.apt_groups for t in g.attack_techniques]
    refs += [t for m in dataset.malware for t in m.attack_techniques]
    tactics = {tac for r in refs for tac in r.tactics}
    tactics |= {tac for t in dataset.attack_techniques for tac in t.tactics}
    assert all("," not in t for t in tactics)
    assert "Command And Control" not in tactics
