"""Cross-file normalization of the Brandefense dataset (no database access)."""

from __future__ import annotations

from cti_graphrag.ingest.read import Dataset


def technique_names(dataset: Dataset) -> dict[str, str]:
    """ATT&CK ID -> name.

    The name from the ``attack_techniques`` lists of groups and malware wins (it
    is the ATT&CK name, e.g. "Server Software Component: Web Shell"); the page in
    attack-techniques.json is used only for IDs no list mentions.
    """
    names: dict[str, str] = {}
    for item in [*dataset.apt_groups, *dataset.malware]:
        for ref in item.attack_techniques:
            if ref.name and ref.id not in names:
                names[ref.id] = ref.name
    for page in dataset.attack_techniques:
        names.setdefault(page.mitre_attack_id, page.name)
    return names
