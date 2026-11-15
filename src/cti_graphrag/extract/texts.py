"""Gera os textos de entrada para o teste de extração.

Lê os JSON de data/raw e sorteia 30 registros (20 APT, 5 ransomware,
5 malware) com semente fixa. O texto leva só o summary (no ransomware,
também model e extortion). Nenhuma lista estruturada entra no texto,
para que a extração seja medida contra o grafo e não copiada do JSON.

Uso: python -m cti_graphrag.extract.texts
"""

import json
import random
from pathlib import Path

RAW_DIR = Path("data/raw")
OUT_FILE = Path("eval/extraction/texts.jsonl")
SEED = 42

# arquivo, prefixo do doc_id, quantidade
SOURCES = [
    ("apt-groups.json", "apt", 20),
    ("ransomware-groups.json", "ransomware", 5),
    ("malware.json", "malware", 5),
]

# campos de texto livre que podem entrar; todo o resto fica de fora
TEXT_FIELDS = {
    "apt": ["summary"],
    "ransomware": ["summary", "model", "extortion"],
    "malware": ["summary"],
}

LABELS = {"model": "Modelo", "extortion": "Extorsão"}


def build_text(item, kind):
    """Monta o texto só com os campos permitidos para o tipo."""
    parts = []
    for field in TEXT_FIELDS[kind]:
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        if field == "summary":
            parts.append(value.strip())
        else:
            parts.append(f"{LABELS[field]}: {value.strip()}")
    return "\n\n".join(parts)


def sample_records(raw_dir=RAW_DIR, seed=SEED):
    rng = random.Random(seed)
    records = []
    for filename, kind, n in SOURCES:
        items = json.loads((raw_dir / filename).read_text(encoding="utf-8"))["items"]
        items = sorted(items, key=lambda i: i["slug"])  # ordem estável antes do sorteio
        for item in rng.sample(items, n):
            records.append({
                "doc_id": f"{kind}:{item['slug']}",
                "entity_name": item["name"],
                "text": build_text(item, kind),
            })
    return records


def main():
    records = sample_records()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(records)} registros em {OUT_FILE}")


if __name__ == "__main__":
    main()
