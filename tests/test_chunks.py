"""Unit tests for the chunks: free text only, one per record, linked to the subject."""

import json

from cti_graphrag.ingest.build_gold import build_gold
from cti_graphrag.ingest.chunks import build_chunks, text_lengths, write_chunks
from cti_graphrag.ingest.models import AptGroup, RansomwareGroup
from cti_graphrag.ingest.read import Dataset, load_dataset


def _tiny():
    apt = AptGroup.model_validate(
        {
            "name": "Andariel",
            "slug": "andariel",
            "summary": "Andariel is a North Korean group.",
            "tools": [{"name": "MagicRAT"}],
            "target_sectors": ["Defense"],
        }
    )
    ransom = RansomwareGroup.model_validate(
        {
            "name": "Akira",
            "slug": "akira",
            "summary": "Akira encrypts files.",
            "model": "RaaS",
            "extortion": "",
            "malware": [{"name": "Cobalt Strike", "url": "https://x/malware/cobalt-strike/"}],
        }
    )
    return Dataset([apt], [ransom], [], [])


def test_chunk_text_is_free_text_only():
    apt, ransom = build_chunks(_tiny())
    assert apt.id == "doc:brandefense:apt-groups:andariel#0"
    assert apt.text == "Andariel is a North Korean group."
    assert ransom.text == "Akira encrypts files.\n\nModel: RaaS"  # empty extortion dropped
    assert "MagicRAT" not in apt.text and "Defense" not in apt.text
    assert "Cobalt Strike" not in ransom.text


def test_gold_links_chunk_only_to_its_subject():
    gold = build_gold(_tiny())
    mentioned = [k for k in gold.edges if k[0] == "MENTIONED_IN"]
    assert sorted(mentioned) == [
        ("MENTIONED_IN", "group:akira", "doc:brandefense:ransomware-groups:akira#0"),
        ("MENTIONED_IN", "group:andariel", "doc:brandefense:apt-groups:andariel#0"),
    ]
    part_of = gold.edges[
        ("PART_OF", "doc:brandefense:apt-groups:andariel#0", "doc:brandefense:apt-groups:andariel")
    ]
    assert part_of.props == {"source": "gold", "doc_id": "doc:brandefense:apt-groups:andariel"}


def test_real_chunks():
    dataset = load_dataset()
    chunks = build_chunks(dataset)
    assert len(chunks) == 181
    assert len({c.id for c in chunks}) == 181
    by_doc = {c.doc_id: c for c in chunks}
    for g in dataset.apt_groups:  # APT chunk is exactly the summary
        assert by_doc[f"doc:brandefense:apt-groups:{g.slug}"].text == g.summary
    assert text_lengths(chunks)["min"] > 0


def test_write_chunks(tmp_path):
    path = tmp_path / "chunks.jsonl"
    write_chunks(build_chunks(_tiny()), path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rows] == [
        "doc:brandefense:apt-groups:andariel#0",
        "doc:brandefense:ransomware-groups:akira#0",
    ]
    assert set(rows[0]) == {"id", "doc_id", "n", "subject_label", "subject_id", "text"}
