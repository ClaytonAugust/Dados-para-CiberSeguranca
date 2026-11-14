"""Unit tests for the reading-level normalizers and the dataset reader.

The reader tests use data/raw/, which is versioned in Git (no internet needed).
"""

import json

import pytest
from pydantic import ValidationError

from cti_graphrag.ingest.models import (
    AptGroup,
    AttackTechnique,
    Malware,
    TechniqueRef,
    blank_to_none,
    canonical_tactic,
    normalize_aliases,
    parse_motivation,
    split_tactics,
    split_title,
)
from cti_graphrag.ingest.normalize import technique_names
from cti_graphrag.ingest.read import Dataset, DatasetError, load_dataset, read_file


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


# --- motivation: PHP-serialized arrays and plain text -------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ('a:1:{i:0;s:9:"espionage";}', ["espionage"]),
        ('a:2:{i:0;s:9:"espionage";i:1;s:8:"sabotage";}', ["espionage", "sabotage"]),
        ('a:1:{i:0;s:10:"espionage";}', ["espionage"]),  # wrong length in the data
        ("espionage", ["espionage"]),
        ("financial, Espionage, sabotage", ["financial", "espionage", "sabotage"]),
        ("", []),
        (None, []),
    ],
)
def test_parse_motivation(raw, expected):
    assert parse_motivation(raw) == expected


# --- article titles used as names ---------------------------------------------
@pytest.mark.parametrize(
    "raw,slug,expected",
    [
        ("Nefilim Ransomware: Profile, Tactics and the Stryzhak Case", "nefilim", "Nefilim"),
        ("k0t Threat Actor: Edge Device Campaign", "k0t", "k0t"),
        ("ROMULUS ClickFix Delivery Platform: Payloads", "romulus-clickfix", "ROMULUS ClickFix"),
        ("Lazarus Group", "lazarus-group", "Lazarus Group"),
    ],
)
def test_split_title(raw, slug, expected):
    name, title_raw = split_title(raw, slug)
    assert name == expected
    assert title_raw == (raw if ":" in raw else None)


# --- technique names ----------------------------------------------------------
def test_technique_page_title_tail_is_removed():
    page = AttackTechnique.model_validate(
        {"name": "Phishing (T1566): ATT&CK Technique", "slug": "t1566", "mitre_attack_id": "T1566"}
    )
    assert page.name == "Phishing"
    assert page.title_raw == "Phishing (T1566): ATT&CK Technique"


def test_subtechnique_colon_is_kept():
    ref = TechniqueRef.model_validate(
        {"id": "T1592.002", "name": "Gather Victim Host Information: Software"}
    )
    assert ref.name == "Gather Victim Host Information: Software"
    page = AttackTechnique.model_validate(
        {"name": "Server Software Component: Web Shell", "slug": "x", "mitre_attack_id": "T1505"}
    )
    assert page.name == "Server Software Component: Web Shell"
    assert page.title_raw is None


def test_list_name_wins_over_page_name():
    ref = {"id": "T1566", "name": "Phishing", "tactic": "Initial Access"}
    pages = [
        {"name": "Phishing (T1566): ATT&CK Technique", "slug": "a", "mitre_attack_id": "T1566"},
        {"name": "Input Capture (T1056)", "slug": "b", "mitre_attack_id": "T1056"},
    ]
    group = AptGroup.model_validate({"name": "G", "slug": "g", "attack_techniques": [ref]})
    dataset = Dataset(
        apt_groups=[group],
        ransomware_groups=[],
        malware=[],
        attack_techniques=[AttackTechnique.model_validate(p) for p in pages],
    )
    assert technique_names(dataset) == {"T1566": "Phishing", "T1056": "Input Capture"}


def test_real_technique_names_have_no_page_tails():
    names = technique_names(load_dataset())
    assert names["T1102.001"] == "Web Service: Dead Drop Resolver"
    assert not any("ATT&CK Technique" in n or n.endswith(")") for n in names.values())


def test_model_keeps_original_title():
    malware = Malware.model_validate({"name": "Amadey Malware: How it Works", "slug": "amadey"})
    assert malware.name == "Amadey"
    assert malware.title_raw == "Amadey Malware: How it Works"


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


def test_duplicate_slugs_are_checked_per_file_only():
    # akira, black-basta, conti and revil are both a ransomware group and a malware
    dataset = load_dataset()
    shared = {g.slug for g in dataset.ransomware_groups} & {m.slug for m in dataset.malware}
    assert shared == {"akira", "black-basta", "conti", "revil"}


def test_real_dataset_names_and_motivations_are_clean():
    dataset = load_dataset()
    items = [*dataset.apt_groups, *dataset.ransomware_groups, *dataset.malware]
    assert all(":" not in item.name for item in items)
    assert sum(item.title_raw is not None for item in items) == 5
    motivations = {m for g in dataset.apt_groups for m in g.motivation}
    assert motivations == {"espionage", "financial", "influence", "sabotage"}


def test_real_dataset_has_no_combined_or_miscased_tactics():
    dataset = load_dataset()
    refs = [t for g in dataset.apt_groups for t in g.attack_techniques]
    refs += [t for m in dataset.malware for t in m.attack_techniques]
    tactics = {tac for r in refs for tac in r.tactics}
    tactics |= {tac for t in dataset.attack_techniques for tac in t.tactics}
    assert all("," not in t for t in tactics)
    assert "Command And Control" not in tactics
