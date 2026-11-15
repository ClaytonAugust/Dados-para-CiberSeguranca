
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


# --------------------------------------------------
# CONFIGURAÇÕES
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[3]

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

ATTACK_VERSION = "20.1"

FILE_NAME = f"enterprise-attack-{ATTACK_VERSION}.json"

DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/"
    "mitre-attack/attack-stix-data/master/"
    f"enterprise-attack/{FILE_NAME}"
)

STIX_TYPES = {
    "Group": ["intrusion-set"],
    "Software": ["malware", "tool"],
    "Technique": ["attack-pattern"],
    "Tactic": ["x-mitre-tactic"],
}


# --------------------------------------------------
# DOWNLOAD
# --------------------------------------------------

def download_file(force=False):

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    path = RAW_DIR / FILE_NAME

    if path.exists() and not force:
        print(f"Arquivo já existe: {path}")
        print("Utilizando a cópia local.")
        return path

    print("Baixando MITRE ATT&CK STIX 2.1...")
    print(f"Versão: {ATTACK_VERSION}")
    print(f"Origem: {DOWNLOAD_URL}")

    request = Request(
        DOWNLOAD_URL,
        headers={
            "User-Agent": "CTI-GraphRAG-Project/1.0"
        }
    )

    temporary_path = path.with_suffix(".json.part")

    try:

        digest = hashlib.sha256()

        with urlopen(request, timeout=180) as response:

            with temporary_path.open("wb") as output:

                while True:

                    block = response.read(1024 * 1024)

                    if not block:
                        break

                    output.write(block)
                    digest.update(block)

        if temporary_path.stat().st_size == 0:
            raise ValueError("Arquivo baixado está vazio.")

        temporary_path.replace(path)

        print("Download concluído.")
        print(f"SHA-256: {digest.hexdigest()}")

    except Exception:

        temporary_path.unlink(missing_ok=True)
        raise

    return path


# --------------------------------------------------
# LEITURA E VALIDAÇÃO
# --------------------------------------------------

def load_bundle(path):

    print("\nValidando arquivo STIX...")

    with path.open("r", encoding="utf-8") as file:
        bundle = json.load(file)

    if bundle.get("type") != "bundle":
        raise ValueError("O arquivo não é um STIX Bundle.")

    objects = bundle.get("objects")

    if not isinstance(objects, list) or not objects:
        raise ValueError("Bundle sem coleção de objetos válida.")

    print("Bundle STIX reconhecido.")
    print("Total de objetos:", len(objects))

    return bundle


# --------------------------------------------------
# EXTRAÇÃO DOS IDS MITRE
# --------------------------------------------------

def get_external_id(obj):

    for reference in obj.get("external_references", []):

        if reference.get("source_name") == "mitre-attack":

            external_id = reference.get("external_id")

            if external_id:
                return external_id

    return None


def is_active(obj):

    return (
        not obj.get("revoked", False)
        and not obj.get("x_mitre_deprecated", False)
    )


# --------------------------------------------------
# INVENTÁRIO
# --------------------------------------------------

def inspect_bundle(bundle, path):

    objects = bundle["objects"]

    object_counts = Counter(
        obj.get("type", "unknown")
        for obj in objects
    )

    active_objects = [
        obj for obj in objects
        if is_active(obj)
    ]

    by_stix_id = {
        obj["id"]: obj
        for obj in active_objects
        if obj.get("id")
    }

    entity_stats = {}

    missing_ids = {}

    for label, types in STIX_TYPES.items():

        selected = [
            obj for obj in active_objects
            if obj.get("type") in types
        ]

        missing = [
            obj for obj in selected
            if not get_external_id(obj)
        ]

        entity_stats[label] = len(selected)
        missing_ids[label] = len(missing)

    # Subtécnicas.
    techniques = [
        obj for obj in active_objects
        if obj.get("type") == "attack-pattern"
    ]

    subtechniques = sum(
        bool(obj.get("x_mitre_is_subtechnique"))
        for obj in techniques
    )

    # Relacionamentos oficiais suportados pelo schema.
    allowed_uses = {
        ("intrusion-set", "malware"),
        ("intrusion-set", "tool"),
        ("intrusion-set", "attack-pattern"),
        ("malware", "attack-pattern"),
        ("tool", "attack-pattern"),
    }

    relationship_counts = Counter()
    mapped_relationships = Counter()

    for obj in active_objects:

        if obj.get("type") != "relationship":
            continue

        relation_type = obj.get("relationship_type")

        relationship_counts[relation_type] += 1

        source = by_stix_id.get(obj.get("source_ref"))
        target = by_stix_id.get(obj.get("target_ref"))

        if not source or not target:
            continue

        source_type = source.get("type")
        target_type = target.get("type")

        if (
            relation_type == "uses"
            and (source_type, target_type) in allowed_uses
        ):
            mapped_relationships["USES"] += 1

        elif (
            relation_type == "subtechnique-of"
            and source_type == "attack-pattern"
            and target_type == "attack-pattern"
        ):
            mapped_relationships["SUBTECHNIQUE_OF"] += 1

    # Táticas associadas às técnicas através do kill chain.
    tactic_shortnames = {
        obj.get("x_mitre_shortname")
        for obj in active_objects
        if obj.get("type") == "x-mitre-tactic"
    }

    technique_tactic_pairs = set()

    for technique in techniques:

        tech_id = get_external_id(technique)

        for phase in technique.get("kill_chain_phases", []):

            if phase.get("kill_chain_name") != "mitre-attack":
                continue

            shortname = phase.get("phase_name")

            if shortname in tactic_shortnames:
                technique_tactic_pairs.add(
                    (tech_id, shortname)
                )

    mapped_relationships["BELONGS_TO"] = len(
        technique_tactic_pairs
    )

    # Metadados da coleção.
    collections = [
        obj for obj in objects
        if obj.get("type") == "x-mitre-collection"
    ]

    collection_versions = [
        obj.get("x_mitre_version")
        for obj in collections
        if obj.get("x_mitre_version")
    ]

    file_hash = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    inventory = {
        "source": "MITRE ATT&CK Enterprise",
        "stix_version": "2.1",
        "attack_release": ATTACK_VERSION,
        "download_url": DOWNLOAD_URL,
        "file_name": path.name,
        "sha256": file_hash,
        "downloaded_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "bundle_id": bundle.get("id"),
        "total_objects": len(objects),
        "active_objects": len(active_objects),
        "object_counts": dict(object_counts),
        "entity_counts": entity_stats,
        "missing_external_ids": missing_ids,
        "subtechniques": subtechniques,
        "relationship_counts": dict(relationship_counts),
        "mapped_relationships": dict(mapped_relationships),
        "collection_versions": collection_versions,
    }

    return inventory


# --------------------------------------------------
# RELATÓRIO
# --------------------------------------------------

def save_report(inventory):

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    report_path = (
        PROCESSED_DIR / "attack_stix_inventory.json"
    )

    report_path.write_text(
        json.dumps(
            inventory,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("\nRelatório salvo:", report_path)


def show_report(inventory):

    print("\n" + "=" * 65)
    print("INVENTÁRIO MITRE ATT&CK ENTERPRISE")
    print("=" * 65)

    print("Versão:", inventory["attack_release"])
    print("STIX:", inventory["stix_version"])

    print("\nObjetos totais:", inventory["total_objects"])
    print("Objetos ativos:", inventory["active_objects"])

    print("\nENTIDADES")

    for label, quantity in inventory["entity_counts"].items():

        missing = inventory["missing_external_ids"][label]

        print(f"{label}: {quantity}")
        print(f"  Sem ID MITRE: {missing}")

    print("\nSUBTÉCNICAS:")
    print(inventory["subtechniques"])

    print("\nRELACIONAMENTOS MAPEADOS:")

    for relation, quantity in inventory[
        "mapped_relationships"
    ].items():

        print(f"{relation}: {quantity}")

    print("\nVERSÃO DA COLEÇÃO:")
    print(inventory["collection_versions"])

    print("\nSHA-256:")
    print(inventory["sha256"])

    print("\n" + "=" * 65)


# --------------------------------------------------
# EXECUÇÃO
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--force",
        action="store_true",
        help="Baixar novamente o arquivo oficial."
    )

    args = parser.parse_args()

    path = download_file(force=args.force)

    bundle = load_bundle(path)

    inventory = inspect_bundle(
        bundle,
        path
    )

    show_report(inventory)

    save_report(inventory)


if __name__ == "__main__":
    main()
