
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

BASE_URL = (
    "https://raw.githubusercontent.com/"
    "BRANDEFENSE/threat-actor-dataset/main/data"
)

FILES = [
    "apt-groups.json",
    "ransomware-groups.json",
    "malware.json",
    "attack-techniques.json",
]


def download_file(filename: str) -> dict:
    url = f"{BASE_URL}/{filename}"

    request = Request(
        url,
        headers={"User-Agent": "CTI-GraphRAG-Research/1.0"}
    )

    with urlopen(request, timeout=30) as response:
        content = response.read()

    # Validate JSON before saving.
    data = json.loads(content.decode("utf-8"))

    if not isinstance(data.get("items"), list):
        raise ValueError(f"Formato inválido: {filename}")

    if "meta" not in data:
        raise ValueError(f"Metadados ausentes: {filename}")

    output = RAW_DIR / filename
    output.write_bytes(content)

    return {
        "filename": filename,
        "url": url,
        "count": len(data["items"]),
        "generated": data["meta"].get("generated"),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print("CTI GraphRAG - Download Brandefense")
    print("=" * 45)

    manifest = []

    for filename in FILES:
        print(f"\nBaixando: {filename}")

        result = download_file(filename)
        manifest.append(result)

        print(f"  Registros: {result['count']}")
        print(f"  Gerado em: {result['generated']}")
        print("  Status: OK")

    manifest_data = {
        "source": "BRANDEFENSE/threat-actor-dataset",
        "downloaded_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "files": manifest,
    }

    manifest_path = RAW_DIR / "manifest.json"

    manifest_path.write_text(
        json.dumps(
            manifest_data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("\n" + "=" * 45)
    print("Download concluído!")
    print(f"Arquivos salvos em: {RAW_DIR}")


if __name__ == "__main__":
    main()
