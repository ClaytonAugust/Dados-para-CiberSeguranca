"""One text chunk per record, built only from free text (the extraction input).

Text = ``summary``; for ransomware groups also ``model`` and ``extortion``. No
structured list (tools, techniques, sectors, regions, origin) ever enters a chunk,
so the extraction LLM cannot read the gold answers.

    python -m cti_graphrag.ingest.chunks   # writes data/processed/chunks.jsonl
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from cti_graphrag.config import PROJECT_ROOT
from cti_graphrag.ingest.read import Dataset, load_dataset

SOURCE = "brandefense"
CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"


@dataclass(frozen=True)
class Chunk:
    id: str  # "<doc_id>#<n>"
    doc_id: str
    n: int
    subject_label: str  # label of the entity the document is about
    subject_id: str
    text: str


def doc_id(file: str, slug: str) -> str:
    return f"doc:{SOURCE}:{file}:{slug}"


def _chunk(file: str, slug: str, label: str, subject_id: str, parts: list[str | None]) -> Chunk:
    text = "\n\n".join(p.strip() for p in parts if p and p.strip())
    did = doc_id(file, slug)
    return Chunk(f"{did}#0", did, 0, label, subject_id, text)


def build_chunks(dataset: Dataset) -> list[Chunk]:
    chunks = [
        _chunk("apt-groups", g.slug, "Group", f"group:{g.slug}", [g.summary])
        for g in dataset.apt_groups
    ]
    chunks += [
        _chunk(
            "ransomware-groups",
            g.slug,
            "Group",
            f"group:{g.slug}",
            [
                g.summary,
                g.model and f"Model: {g.model}",
                g.extortion and f"Extortion: {g.extortion}",
            ],
        )
        for g in dataset.ransomware_groups
    ]
    chunks += [
        _chunk("malware", m.slug, "Software", f"software:{m.slug}", [m.summary])
        for m in dataset.malware
    ]
    chunks += [
        _chunk("attack-techniques", t.slug, "Technique", t.mitre_attack_id, [t.summary])
        for t in dataset.attack_techniques
    ]
    return chunks


def write_chunks(chunks: list[Chunk], path: Path = CHUNKS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for chunk in chunks:
            fh.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")


def text_lengths(chunks: list[Chunk]) -> dict[str, float]:
    sizes = [len(c.text) for c in chunks]
    return {"min": min(sizes), "median": statistics.median(sizes), "max": max(sizes)}


def main() -> None:
    chunks = build_chunks(load_dataset())
    write_chunks(chunks)
    print(f"chunks: {len(chunks)} -> {CHUNKS_PATH.relative_to(PROJECT_ROOT)}")
    print(f"tamanho do texto (caracteres): {text_lengths(chunks)}")


if __name__ == "__main__":
    main()
