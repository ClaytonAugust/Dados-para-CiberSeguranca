
import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

FILES = [
    "apt-groups.json",
    "ransomware-groups.json",
    "malware.json",
    "attack-techniques.json",
]


def inspect_file(filename: str) -> None:
    path = RAW_DIR / filename

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    items = data["items"]

    print("\n" + "=" * 60)
    print(f"ARQUIVO: {filename}")
    print("=" * 60)

    print("Dataset:", data["meta"].get("dataset"))
    print("Licença:", data["meta"].get("license"))
    print("Total de registros:", len(items))

    all_keys = Counter()

    for item in items:
        all_keys.update(item.keys())

    print("\nCampos encontrados:")

    for key, count in sorted(all_keys.items()):
        print(f"  {key}: presente em {count}/{len(items)} registros")

    if items:
        print("\nExemplo de registro:")
        print(
            json.dumps(
                items[0],
                indent=2,
                ensure_ascii=False
            )
        )


def main() -> None:
    for filename in FILES:
        inspect_file(filename)

    print("\nInspeção concluída!")


if __name__ == "__main__":
    main()
