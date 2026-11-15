
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

RAW_FILE = (
    ROOT / "data" / "raw" /
    "enterprise-attack-20.1.json"
)

SUPPORTED = {
    "intrusion-set",
    "malware",
    "tool",
    "attack-pattern",
    "x-mitre-tactic",
}


def active(obj):
    return (
        not obj.get("revoked", False)
        and not obj.get("x_mitre_deprecated", False)
    )


def main():

    with RAW_FILE.open("r", encoding="utf-8") as file:
        bundle = json.load(file)

    all_objects = {
        obj["id"]: obj
        for obj in bundle["objects"]
        if obj.get("id")
    }

    active_objects = {
        obj["id"]: obj
        for obj in bundle["objects"]
        if obj.get("id") and active(obj)
    }

    reasons = Counter()
    details = Counter()

    total = 0

    for rel in active_objects.values():

        if rel.get("type") != "relationship":
            continue

        source_ref = rel.get("source_ref")
        target_ref = rel.get("target_ref")

        source = active_objects.get(source_ref)
        target = active_objects.get(target_ref)

        source_all = all_objects.get(source_ref)
        target_all = all_objects.get(target_ref)

        reason = None

        if not source or not target:

            if not source_all and not target_all:
                reason = "both_refs_missing"

            elif not source_all:
                reason = "source_ref_missing"

            elif not target_all:
                reason = "target_ref_missing"

            elif source_all and not source:
                reason = "source_inactive"

            elif target_all and not target:
                reason = "target_inactive"

        elif (
            source["type"] not in SUPPORTED
            or target["type"] not in SUPPORTED
        ):
            reason = "unsupported_endpoint"

        else:
            # Ambos endpoints são entidades suportadas.
            # Nesse caso, a relação não entrou no mapeamento
            # de USES, SUBTECHNIQUE_OF ou BELONGS_TO.
            reason = "unsupported_relationship_type"

        if reason:

            total += 1

            source_type = (
                source or source_all or {}
            ).get("type", "unknown")

            target_type = (
                target or target_all or {}
            ).get("type", "unknown")

            rel_type = rel.get(
                "relationship_type",
                "unknown"
            )

            reasons[reason] += 1

            details[
                (rel_type, source_type, target_type)
            ] += 1

    print("\n=== AUDITORIA DE RELACIONAMENTOS NÃO MAPEADOS ===")

    print("Total encontrado:", total)

    print("\nPOR MOTIVO:")

    for reason, count in reasons.most_common():
        print(f"{reason}: {count}")

    print("\nPOR TIPO DE RELACIONAMENTO E ENDPOINTS:")

    for (relation, source, target), count in details.most_common(30):
        print(
            f"{relation}: {source} -> {target}: {count}"
        )

    print("\n=== FIM DA AUDITORIA ===")


if __name__ == "__main__":
    main()
