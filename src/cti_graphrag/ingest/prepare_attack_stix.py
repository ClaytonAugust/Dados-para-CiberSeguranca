
import json
import hashlib
import re

from collections import Counter, defaultdict
from pathlib import Path

import yaml


# ==================================================
# CONFIGURAÇÕES
# ==================================================

ROOT = Path(__file__).resolve().parents[3]

RAW_FILE = (
    ROOT / "data" / "raw" /
    "enterprise-attack-20.1.json"
)

SCHEMA_FILE = ROOT / "schema" / "schema.yaml"

PROCESSED = ROOT / "data" / "processed"

VERSION = "20.1"

SOURCE = "attack"

STIX_TO_LABEL = {
    "intrusion-set": "Group",
    "malware": "Software",
    "tool": "Software",
    "attack-pattern": "Technique",
    "x-mitre-tactic": "Tactic",
}

ID_PATTERNS = {
    "Group": r"G\d{4,}",
    "Software": r"S\d{4,}",
    "Technique": r"T\d{4,}(?:\.\d{3})?",
    "Tactic": r"TA\d{4}",
}

ALLOWED_USES = {
    ("Group", "Software"),
    ("Group", "Technique"),
    ("Software", "Technique"),
}


# ==================================================
# UTILITÁRIOS
# ==================================================

def write_jsonl(path, records):

    with path.open("w", encoding="utf-8") as file:

        for record in records:

            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                ) + "\n"
            )


def string_list(values):

    if not isinstance(values, list):
        return []

    return list(dict.fromkeys(
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    ))


def value_as_string(value):

    if value is None:
        return None

    if isinstance(value, (list, dict)):
        return json.dumps(
            value,
            ensure_ascii=False
        )

    return str(value)


def clean_properties(properties):

    return {
        key: value
        for key, value in properties.items()
        if value is not None and value != ""
    }


def get_external_id(obj):

    for reference in obj.get("external_references", []):

        if reference.get("source_name") == "mitre-attack":

            external_id = reference.get("external_id")

            if external_id:
                return external_id.upper()

    return None


def get_source_url(obj):

    references = obj.get("external_references", [])

    for reference in references:

        if (
            reference.get("source_name") == "mitre-attack"
            and reference.get("url")
        ):
            return reference["url"]

    for reference in references:

        if reference.get("url"):
            return reference["url"]

    return None


def is_active(obj):

    return (
        not obj.get("revoked", False)
        and not obj.get("x_mitre_deprecated", False)
    )


def load_configuration():

    if not RAW_FILE.is_file():
        raise FileNotFoundError(RAW_FILE)

    if not SCHEMA_FILE.is_file():
        raise FileNotFoundError(SCHEMA_FILE)

    with SCHEMA_FILE.open("r", encoding="utf-8") as file:
        schema = yaml.safe_load(file)

    with RAW_FILE.open("r", encoding="utf-8") as file:
        bundle = json.load(file)

    if bundle.get("type") != "bundle":
        raise ValueError("Arquivo não é um STIX Bundle.")

    return schema, bundle


# ==================================================
# VALIDAÇÃO DO SCHEMA
# ==================================================

def validate_schema(schema):

    for label in STIX_TO_LABEL.values():

        if label not in schema["labels"]:
            raise ValueError(
                f"Label ausente no schema: {label}"
            )

    required_relationships = {
        "USES",
        "BELONGS_TO",
        "SUBTECHNIQUE_OF",
        "PART_OF",
        "MENTIONED_IN",
    }

    for relationship in required_relationships:

        if relationship not in schema["relationships"]:
            raise ValueError(
                f"Relacionamento ausente no schema: {relationship}"
            )


def allowed_endpoints(schema, relationship):

    definitions = schema["relationships"][relationship]

    return {
        (item["from"], item["to"])
        for item in definitions["allowed_endpoints"]
    }


# ==================================================
# TEXTO DOS DOCUMENTOS
# ==================================================

def build_chunk_text(obj, entity_id):

    name = obj.get("name", "Unknown")

    parts = [
        "Dataset: MITRE ATT&CK Enterprise",
        f"Version: {VERSION}",
        f"Entity: {name}",
        f"ATT&CK ID: {entity_id}",
        f"STIX type: {obj.get('type')}",
    ]

    fields = [
        "description",
        "aliases",
        "platforms",
        "primary_motivation",
        "secondary_motivations",
        "resource_level",
        "first_seen",
        "last_seen",
        "kill_chain_phases",
        "x_mitre_platforms",
        "x_mitre_domains",
    ]

    for field in fields:

        value = obj.get(field)

        if value not in (None, "", []):
            parts.append(
                f"{field}: "
                f"{json.dumps(value, ensure_ascii=False)}"
            )

    for reference in obj.get("external_references", []):

        if reference.get("url"):

            parts.append(
                "Reference: "
                + str(reference.get("source_name", ""))
                + " | "
                + reference["url"]
            )

    return "\n".join(parts)


# ==================================================
# PREPARAÇÃO
# ==================================================

def prepare():

    schema, bundle = load_configuration()

    validate_schema(schema)

    objects = bundle["objects"]

    active_objects = [
        obj
        for obj in objects
        if is_active(obj)
    ]

    # STIX ID -> dados da entidade
    entity_index = {}

    entities_by_label = defaultdict(dict)

    documents = {}
    chunks = {}

    semantic_edges = {}
    structural_edges = {}

    mentions = set()

    # --------------------------------------------------
    # 1. IDENTIFICAR ENTIDADES
    # --------------------------------------------------

    print("\n[1] Preparando entidades...")

    for obj in active_objects:

        stix_type = obj.get("type")

        if stix_type not in STIX_TO_LABEL:
            continue

        label = STIX_TO_LABEL[stix_type]

        external_id = get_external_id(obj)

        if not external_id:
            raise ValueError(
                f"Entidade sem ID MITRE: {obj.get('name')}"
            )

        if not re.fullmatch(
            ID_PATTERNS[label],
            external_id
        ):
            raise ValueError(
                f"ID inválido: {label} / {external_id}"
            )

        name = obj.get("name")

        if not name:
            raise ValueError(
                f"Entidade sem nome: {external_id}"
            )

        stix_id = obj["id"]

        if stix_id in entity_index:
            raise ValueError(
                f"STIX ID duplicado: {stix_id}"
            )

        source_url = get_source_url(obj)

        aliases = string_list(
            obj.get("aliases", [])
        )

        # --------------------------------------------------
        # PROPRIEDADES CONFORME O SCHEMA
        # --------------------------------------------------

        if label == "Group":

            properties = {
                "id": external_id,
                "name": name,
                "aliases": aliases,
                "aliases_text": " ".join(aliases),
                "description": obj.get("description"),
                "motivation": value_as_string(
                    obj.get("primary_motivation")
                ),
                "first_seen": obj.get("first_seen"),
                "last_updated": obj.get("modified"),
                "source_url": source_url,
                "is_provisional": False,
            }

        elif label == "Software":

            properties = {
                "id": external_id,
                "name": name,
                "type": stix_type,
                "source_type": stix_type,
                "aliases": aliases,
                "aliases_text": " ".join(aliases),
                "description": obj.get("description"),
                "platforms": string_list(
                    obj.get("x_mitre_platforms", [])
                ),
                "first_seen": obj.get("first_seen"),
                "last_updated": obj.get("modified"),
                "source_url": source_url,
                "is_provisional": False,
            }

        elif label == "Technique":

            properties = {
                "id": external_id,
                "name": name,
                "is_subtechnique": bool(
                    obj.get("x_mitre_is_subtechnique", False)
                ),
                "description": obj.get("description"),
                "last_updated": obj.get("modified"),
                "source_url": source_url,
                "is_provisional": False,
            }

        elif label == "Tactic":

            properties = {
                "id": external_id,
                "name": name,
                "shortname": obj.get("x_mitre_shortname"),
                "is_provisional": False,
            }

        properties = clean_properties(properties)

        if external_id in entities_by_label[label]:
            raise ValueError(
                f"ID MITRE repetido: {label} {external_id}"
            )

        entities_by_label[label][external_id] = properties

        # --------------------------------------------------
        # DOCUMENTO E CHUNK
        # --------------------------------------------------

        document_id = f"doc:attack:{external_id}"
        chunk_id = f"{document_id}#0"

        text = build_chunk_text(
            obj,
            external_id
        )

        documents[document_id] = {
            "id": document_id,
            "title": name,
            "url": source_url,
            "source": SOURCE,
        }

        chunks[chunk_id] = {
            "chunk_id": chunk_id,
            "doc_id": document_id,
            "source": SOURCE,
            "url": source_url,
            "text": text,
        }

        entity_index[stix_id] = {
            "label": label,
            "id": external_id,
            "name": name,
            "chunk_id": chunk_id,
        }

        # Entidade mencionada em seu próprio documento.
        mentions.add(
            (label, external_id, chunk_id)
        )

    print("Entidades identificadas:")

    for label, entities in entities_by_label.items():
        print(f"  {label}: {len(entities)}")

    # --------------------------------------------------
    # 2. REGISTRAR RELACIONAMENTOS
    # --------------------------------------------------

    print("\n[2] Preparando relacionamentos...")

    allowed_uses = allowed_endpoints(
        schema,
        "USES"
    )

    allowed_subtechniques = allowed_endpoints(
        schema,
        "SUBTECHNIQUE_OF"
    )

    skipped = Counter()

    def add_semantic(
        relation,
        source,
        target,
        evidence
    ):

        endpoint = (
            source["label"],
            target["label"]
        )

        allowed = allowed_endpoints(
            schema,
            relation
        )

        if endpoint not in allowed:
            raise ValueError(
                f"Endpoint não permitido: "
                f"{source['label']}-[{relation}]->{target['label']}"
            )

        chunk_id = source["chunk_id"]

        key = (
            relation,
            source["label"],
            source["id"],
            target["label"],
            target["id"],
            chunk_id,
        )

        semantic_edges[key] = {
            "type": relation,
            "from_label": source["label"],
            "from_id": source["id"],
            "to_label": target["label"],
            "to_id": target["id"],
            "chunk_id": chunk_id,
            "source": "gold",
            "evidence": evidence,
            "confidence": 1.0,
        }

        mentions.add(
            (
                source["label"],
                source["id"],
                chunk_id
            )
        )

        mentions.add(
            (
                target["label"],
                target["id"],
                chunk_id
            )
        )

    for obj in active_objects:

        if obj.get("type") != "relationship":
            continue

        relation_type = obj.get("relationship_type")

        source = entity_index.get(
            obj.get("source_ref")
        )

        target = entity_index.get(
            obj.get("target_ref")
        )

        if not source or not target:
            skipped["missing_endpoint"] += 1
            continue

        evidence = (
            obj.get("description")
            or (
                f"MITRE ATT&CK STIX relationship: "
                f"{source['name']} {relation_type} "
                f"{target['name']}."
            )
        )

        if relation_type == "uses":

            endpoint = (
                source["label"],
                target["label"]
            )

            if endpoint not in ALLOWED_USES:
                skipped["uses_endpoint_not_supported"] += 1
                continue

            if endpoint not in allowed_uses:
                raise ValueError(
                    f"USES não permitido pelo schema: {endpoint}"
                )

            add_semantic(
                "USES",
                source,
                target,
                evidence
            )

        elif relation_type == "subtechnique-of":

            endpoint = (
                source["label"],
                target["label"]
            )

            if endpoint != ("Technique", "Technique"):
                skipped["invalid_subtechnique_endpoint"] += 1
                continue

            if endpoint not in allowed_subtechniques:
                raise ValueError(
                    "SUBTECHNIQUE_OF não permitido pelo schema."
                )

            add_semantic(
                "SUBTECHNIQUE_OF",
                source,
                target,
                evidence
            )

    # --------------------------------------------------
    # 3. BELONGS_TO A PARTIR DAS KILL CHAIN PHASES
    # --------------------------------------------------

    print("\n[3] Relacionando técnicas e táticas...")

    tactic_index = {}

    for obj in active_objects:

        if obj.get("type") != "x-mitre-tactic":
            continue

        shortname = obj.get("x_mitre_shortname")

        entity = entity_index.get(
            obj.get("id")
        )

        if shortname and entity:
            tactic_index[shortname] = entity

    for obj in active_objects:

        if obj.get("type") != "attack-pattern":
            continue

        technique = entity_index.get(
            obj.get("id")
        )

        if not technique:
            continue

        for phase in obj.get("kill_chain_phases", []):

            if phase.get("kill_chain_name") != "mitre-attack":
                continue

            tactic = tactic_index.get(
                phase.get("phase_name")
            )

            if not tactic:
                skipped["tactic_not_found"] += 1
                continue

            evidence = (
                f"MITRE ATT&CK technique "
                f"{technique['id']} ({technique['name']}) "
                f"is associated with tactic "
                f"{tactic['id']} ({tactic['name']})."
            )

            add_semantic(
                "BELONGS_TO",
                technique,
                tactic,
                evidence
            )

    # --------------------------------------------------
    # 4. RELACIONAMENTOS ESTRUTURAIS
    # --------------------------------------------------

    print("\n[4] Criando procedência estrutural...")

    for chunk_id, chunk in chunks.items():

        structural_edges[
            (
                "PART_OF",
                "Chunk",
                chunk_id,
                "Document",
                chunk["doc_id"],
            )
        ] = {
            "type": "PART_OF",
            "from_label": "Chunk",
            "from_id": chunk_id,
            "to_label": "Document",
            "to_id": chunk["doc_id"],
        }

    for label, entity_id, chunk_id in mentions:

        endpoint = (label, "Chunk")

        allowed = allowed_endpoints(
            schema,
            "MENTIONED_IN"
        )

        if endpoint not in allowed:
            raise ValueError(
                f"MENTIONED_IN não permitido: {endpoint}"
            )

        structural_edges[
            (
                "MENTIONED_IN",
                label,
                entity_id,
                "Chunk",
                chunk_id,
            )
        ] = {
            "type": "MENTIONED_IN",
            "from_label": label,
            "from_id": entity_id,
            "to_label": "Chunk",
            "to_id": chunk_id,
        }

    # --------------------------------------------------
    # 5. SALVAR JSONL
    # --------------------------------------------------

    print("\n[5] Salvando arquivos intermediários...")

    PROCESSED.mkdir(
        parents=True,
        exist_ok=True
    )

    entity_records = []

    for label, entities in entities_by_label.items():

        for properties in entities.values():

            entity_records.append({
                "label": label,
                "properties": properties,
            })

    semantic_records = list(
        semantic_edges.values()
    )

    structural_records = list(
        structural_edges.values()
    )

    write_jsonl(
        PROCESSED / "attack_entities.jsonl",
        entity_records
    )

    write_jsonl(
        PROCESSED / "attack_documents.jsonl",
        list(documents.values())
    )

    write_jsonl(
        PROCESSED / "chunks.jsonl",
        list(chunks.values())
    )

    write_jsonl(
        PROCESSED / "attack_semantic_relationships.jsonl",
        semantic_records
    )

    write_jsonl(
        PROCESSED / "attack_structural_relationships.jsonl",
        structural_records
    )

    # --------------------------------------------------
    # 6. RELATÓRIO
    # --------------------------------------------------

    entity_counts = {
        label: len(items)
        for label, items in entities_by_label.items()
    }

    semantic_counts = Counter(
        edge["type"]
        for edge in semantic_records
    )

    structural_counts = Counter(
        edge["type"]
        for edge in structural_records
    )

    summary = {
        "source": "MITRE ATT&CK Enterprise",
        "version": VERSION,
        "stix_version": bundle.get("spec_version"),
        "bundle_id": bundle.get("id"),
        "sha256": hashlib.sha256(
            RAW_FILE.read_bytes()
        ).hexdigest(),
        "entities": entity_counts,
        "total_entities": len(entity_records),
        "documents": len(documents),
        "chunks": len(chunks),
        "semantic_relationships": dict(semantic_counts),
        "total_semantic_relationships": len(
            semantic_records
        ),
        "structural_relationships": dict(
            structural_counts
        ),
        "total_structural_relationships": len(
            structural_records
        ),
        "mentions": len(mentions),
        "skipped_relationships": dict(skipped),
    }

    summary_path = (
        PROCESSED / "attack_preparation_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------
    # 7. EXIBIR RESULTADO
    # --------------------------------------------------

    print("\n" + "=" * 65)
    print("PREPARAÇÃO MITRE ATT&CK CONCLUÍDA")
    print("=" * 65)

    print("\nENTIDADES")

    for label, quantity in entity_counts.items():
        print(f"{label}: {quantity}")

    print("\nDOCUMENTOS:", len(documents))
    print("CHUNKS:", len(chunks))

    print("\nRELACIONAMENTOS SEMÂNTICOS")

    for relation, quantity in semantic_counts.items():
        print(f"{relation}: {quantity}")

    print("\nRELACIONAMENTOS ESTRUTURAIS")

    for relation, quantity in structural_counts.items():
        print(f"{relation}: {quantity}")

    print("\nVALORES NÃO PROCESSADOS")

    for reason, quantity in skipped.items():
        print(f"{reason}: {quantity}")

    print("\nArquivos gerados em:", PROCESSED)
    print("Resumo:", summary_path)

    print("\n" + "=" * 65)

    return summary


if __name__ == "__main__":
    prepare()
