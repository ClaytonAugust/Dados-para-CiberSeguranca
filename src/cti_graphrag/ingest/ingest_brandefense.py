
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import pycountry
import yaml
from dotenv import load_dotenv
from falkordb import FalkorDB


ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
SCHEMA_FILE = ROOT / "schema" / "schema.yaml"

FILES = {
    "apt-groups": "apt-groups.json",
    "ransomware-groups": "ransomware-groups.json",
    "malware": "malware.json",
    "attack-techniques": "attack-techniques.json",
}

BATCH_SIZE = 200

TACTIC_IDS = {
    "reconnaissance": "TA0043",
    "resource development": "TA0042",
    "initial access": "TA0001",
    "execution": "TA0002",
    "persistence": "TA0003",
    "privilege escalation": "TA0004",
    "defense evasion": "TA0005",
    "credential access": "TA0006",
    "discovery": "TA0007",
    "lateral movement": "TA0008",
    "collection": "TA0009",
    "exfiltration": "TA0010",
    "command and control": "TA0011",
    "impact": "TA0040",
}

SECTOR_ALIASES = {
    "aerospace": "Aerospace",
    "defense": "Defense",
    "nuclear": "Nuclear",
    "engineering": "Engineering",
    "healthcare": "Healthcare",
    "healthcare and public health": "Healthcare",
    "government": "Government",
    "government and public sector": "Government",
    "finance": "Finance",
    "financial services": "Finance",
    "energy": "Energy",
    "education": "Education",
    "technology": "Technology",
    "information technology": "Information Technology",
    "telecommunications": "Telecommunications",
    "communications": "Communications",
    "manufacturing": "Manufacturing",
    "transportation": "Transportation",
    "automotive": "Automotive",
    "agriculture": "Agriculture",
    "retail": "Retail",
    "media": "Media",
    "utilities": "Utilities",
    "chemical": "Chemical",
    "construction": "Construction",
}

COUNTRY_ALIASES = {
    "north korea": "KP",
    "south korea": "KR",
    "russia": "RU",
    "iran": "IR",
    "vietnam": "VN",
    "united states": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "usa": "US",
}


def slugify(value: str) -> str:
    """Generate a normalized identifier."""

    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )

    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)

    return value.strip("_")


def normalize(value: str) -> str:
    return slugify(value).replace("_", " ")


def clean_props(properties: dict) -> dict:
    return {
        key: value
        for key, value in properties.items()
        if value is not None and value != ""
    }


def aliases_list(raw) -> list:
    """Normalize aliases represented as strings or objects."""

    result = []

    if not isinstance(raw, list):
        return result

    for alias in raw:
        if isinstance(alias, str):
            name = alias
        elif isinstance(alias, dict):
            name = alias.get("name")
        else:
            continue

        if name and name not in result:
            result.append(name.strip())

    return result


def source_mitre_id(item: dict, pattern: str):
    """Extract canonical ATT&CK IDs from official source URLs."""

    for source in item.get("sources", []):
        if not isinstance(source, dict):
            continue

        content = (
            str(source.get("url", ""))
            + " "
            + str(source.get("title", ""))
        )

        match = re.search(pattern, content, re.IGNORECASE)

        if match:
            return match.group(1).upper()

    return None


def country_iso(value: str):
    """Resolve an exact country name to ISO alpha-2."""

    if not value:
        return None

    name = re.sub(
        r"\s*\([^)]*\)\s*$", "", value.strip()
    )

    key = normalize(name)

    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]

    try:
        return pycountry.countries.lookup(name).alpha_2
    except LookupError:
        return None


def tactic_names(value) -> list:
    """Support one or multiple tactics."""

    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = value.split(",")
    else:
        values = []

    return list(dict.fromkeys(
        item.strip()
        for item in values
        if isinstance(item, str) and item.strip()
    ))


def classify_software(raw_type, default="malware") -> str:
    value = normalize(str(raw_type or default))

    tool_types = {
        "tool",
        "abused tool",
        "credential theft tool",
        "remote access tool",
    }

    return "tool" if value in tool_types else "malware"


def batches(items: list, size: int = BATCH_SIZE):
    for index in range(0, len(items), size):
        yield items[index:index + size]


class BrandefenseImporter:

    def __init__(self, graph, schema):
        self.graph = graph
        self.schema = schema

        self.nodes = {
            label: {}
            for label in schema["labels"]
        }

        self.group_index = defaultdict(set)
        self.software_index = defaultdict(set)

        self.edges = {}
        self.mentions = set()
        self.parts_of = set()

        self.documents = {}
        self.chunks = {}
        self.contexts = {}

        self.unmapped = []
        self.unmapped_keys = set()

        self.group_record_ids = {}
        self.software_record_ids = {}

        self.counts = defaultdict(int)

    def add_node(self, label: str, properties: dict):
        """Store nodes in memory before batch insertion."""

        properties = clean_props(properties)
        node_id = properties["id"]

        current = self.nodes[label].setdefault(
            node_id, {"id": node_id}
        )

        for key, value in properties.items():

            if isinstance(value, list):
                existing = current.get(key, [])
                if not isinstance(existing, list):
                    existing = []

                current[key] = list(dict.fromkeys(
                    existing + value
                ))

            elif key not in current or current[key] in (None, ""):
                current[key] = value

    def add_index(self, index, name: str, entity_id: str):
        key = normalize(name)

        if key:
            index[key].add(entity_id)

    def resolve_index(self, index, name: str):
        matches = index.get(normalize(name), set())

        if len(matches) == 1:
            return next(iter(matches))

        return None

    def add_mention(self, label: str, entity_id: str, chunk_id: str):
        self.mentions.add((label, entity_id, chunk_id))

    def add_semantic(
        self,
        relation: str,
        from_label: str,
        from_id: str,
        to_label: str,
        to_id: str,
        chunk_id: str,
        evidence: str,
    ):
        """Create a source-backed semantic relationship."""

        definitions = self.schema["relationships"][relation]

        allowed = {
            (item["from"], item["to"])
            for item in definitions["allowed_endpoints"]
        }

        if (from_label, to_label) not in allowed:
            raise ValueError(
                f"Relacionamento não permitido: "
                f"{from_label}-[{relation}]->{to_label}"
            )

        key = (
            relation, from_label, from_id,
            to_label, to_id, chunk_id
        )

        self.edges[key] = {
            "relation": relation,
            "from_label": from_label,
            "from_id": from_id,
            "to_label": to_label,
            "to_id": to_id,
            "chunk_id": chunk_id,
            "source": "gold",
            "evidence": evidence,
            "confidence": 1.0,
        }

        self.add_mention(from_label, from_id, chunk_id)
        self.add_mention(to_label, to_id, chunk_id)

    def report_unmapped(self, field: str, value):
        key = (field, str(value))

        if key not in self.unmapped_keys:
            self.unmapped_keys.add(key)

            self.unmapped.append({
                "field": field,
                "value": value,
                "reason": "Needs normalization or manual review"
            })

    def create_context(self, dataset: str, item: dict):
        """Create one record-level chunk and its source document."""

        name = item.get("name", "unknown")
        slug = item.get("slug") or slugify(name)

        doc_id = f"doc:brandefense:{dataset}:{slug}"
        chunk_id = f"{doc_id}#0"

        references = item.get("sources", [])

        document = {
            "id": doc_id,
            "title": name,
            "url": item.get("url"),
            "source": "brandefense",
        }

        parts = [
            f"Dataset: {dataset}",
            f"Entity: {name}",
        ]

        for field in (
            "summary",
            "suspected_origin",
            "attributed_by",
            "motivation",
            "target_sectors",
            "target_regions",
            "attack_techniques",
            "tools",
            "malware",
            "used_by",
            "platforms",
            "type",
            "status",
            "extortion",
            "first_seen",
        ):
            value = item.get(field)

            if value not in (None, "", []):
                parts.append(
                    f"{field}: {json.dumps(value, ensure_ascii=False)}"
                )

        for reference in references:
            if isinstance(reference, dict):
                parts.append(
                    "Reference: "
                    f"{reference.get('title', '')} | "
                    f"{reference.get('publisher', '')} | "
                    f"{reference.get('url', '')}"
                )

        chunk = {
            "id": chunk_id,
            "text": "\n".join(parts),
        }

        self.documents[doc_id] = document
        self.chunks[chunk_id] = chunk

        self.add_node("Document", document)
        self.add_node("Chunk", chunk)
        self.parts_of.add((chunk_id, doc_id))

        self.contexts[(dataset, slug)] = chunk_id

        return chunk_id

    def register_group(self, dataset: str, item: dict):
        name = item["name"]

        mitre_id = item.get("mitre_attack_id")

        if not (
            isinstance(mitre_id, str)
            and re.fullmatch(r"G\d{4,}", mitre_id.upper())
        ):
            mitre_id = source_mitre_id(
                item, r"/groups/(G\d{4,})"
            )

        existing_id = self.resolve_index(
            self.group_index, name
        )

        entity_id = (
            mitre_id.upper()
            if mitre_id
            else existing_id or f"new:Group:{slugify(item.get('slug') or name)}"
        )

        aliases = aliases_list(item.get("aliases", []))

        alias_metadata = item.get("aliases", [])

        properties = {
            "id": entity_id,
            "name": name,
            "aliases": aliases,
            "description": item.get("summary"),
            "status": item.get("status"),
            "motivation": item.get("motivation"),
            "suspected_origin": item.get("suspected_origin"),
            "attributed_by": item.get("attributed_by"),
            "target_regions": item.get("target_regions", []),
            "target_sectors_raw": item.get("target_sectors", []),
            "first_seen": item.get("first_seen"),
            "last_updated": item.get("last_updated"),
            "model": item.get("model"),
            "extortion": item.get("extortion"),
            "source_url": item.get("url"),
            "aliases_sources_json": json.dumps(
                alias_metadata,
                ensure_ascii=False
            ),
            "is_provisional": not bool(mitre_id),
        }

        self.add_node("Group", properties)

        self.add_index(self.group_index, name, entity_id)

        for alias in aliases:
            self.add_index(
                self.group_index, alias, entity_id
            )

        self.group_record_ids[(dataset, item.get("slug") or slugify(name))] = entity_id

        self.counts["group_records"] += 1

        return entity_id

    def register_software(self, item: dict):
        name = item["name"]

        mitre_id = item.get("mitre_attack_id")

        if not (
            isinstance(mitre_id, str)
            and re.fullmatch(r"S\d{4,}", mitre_id.upper())
        ):
            mitre_id = source_mitre_id(
                item, r"/software/(S\d{4,})"
            )

        existing_id = self.resolve_index(
            self.software_index, name
        )

        entity_id = (
            mitre_id.upper()
            if mitre_id
            else existing_id or f"new:Software:{slugify(item.get('slug') or name)}"
        )

        aliases = aliases_list(item.get("aliases", []))
        raw_type = item.get("type")

        self.add_node("Software", {
            "id": entity_id,
            "name": name,
            "type": classify_software(raw_type),
            "source_type": raw_type,
            "aliases": aliases,
            "description": item.get("summary"),
            "platforms": item.get("platforms", []),
            "first_seen": item.get("first_seen"),
            "last_updated": item.get("last_updated"),
            "source_url": item.get("url"),
            "is_provisional": not bool(mitre_id),
        })

        self.add_index(self.software_index, name, entity_id)

        for alias in aliases:
            self.add_index(
                self.software_index, alias, entity_id
            )

        self.software_record_ids[item.get("slug") or slugify(name)] = entity_id

        self.counts["software_records"] += 1

        return entity_id

    def ensure_group(self, name: str, url=None):
        entity_id = self.resolve_index(self.group_index, name)

        if entity_id:
            return entity_id

        entity_id = f"new:Group:{slugify(name)}"

        self.add_node("Group", {
            "id": entity_id,
            "name": name,
            "aliases": [],
            "source_url": url,
            "is_provisional": True,
        })

        self.add_index(self.group_index, name, entity_id)

        return entity_id

    def ensure_software(self, name: str, raw_type=None, url=None):
        entity_id = self.resolve_index(
            self.software_index, name
        )

        if entity_id:
            return entity_id

        entity_id = f"new:Software:{slugify(name)}"

        self.add_node("Software", {
            "id": entity_id,
            "name": name,
            "type": classify_software(raw_type),
            "source_type": raw_type,
            "aliases": [],
            "source_url": url,
            "is_provisional": True,
        })

        self.add_index(
            self.software_index, name, entity_id
        )

        return entity_id

    def ensure_country(self, name: str):
        iso = country_iso(name)

        if not iso:
            self.report_unmapped("country", name)
            return None

        entity_id = f"country:{iso}"

        self.add_node("Country", {
            "id": entity_id,
            "name": name,
        })

        return entity_id

    def ensure_sector(self, name: str):
        if country_iso(name):
            return None

        key = normalize(name)

        canonical = SECTOR_ALIASES.get(key)

        if not canonical:
            self.report_unmapped("target_sector", name)
            return None

        entity_id = f"sector:{slugify(canonical)}"

        self.add_node("Sector", {
            "id": entity_id,
            "name": canonical,
        })

        return entity_id

    def ensure_tactic(self, name: str):
        key = normalize(name)
        tactic_id = TACTIC_IDS.get(key)

        provisional = tactic_id is None

        if provisional:
            tactic_id = f"new:Tactic:{slugify(name)}"

        canonical_name = name.strip()

        self.add_node("Tactic", {
            "id": tactic_id,
            "name": canonical_name,
            "shortname": slugify(canonical_name),
            "is_provisional": provisional,
        })

        return tactic_id

    def ensure_technique(
        self,
        technique: dict,
        chunk_id: str,
        provisional=True,
    ):
        technique_id = technique.get("id")

        if not technique_id:
            self.report_unmapped(
                "technique_without_id",
                technique.get("name")
            )
            return None

        technique_id = technique_id.upper()

        if not re.fullmatch(r"T\d{4,}(?:\.\d{3})?", technique_id):
            self.report_unmapped(
                "invalid_technique_id", technique_id
            )
            return None

        name = technique.get("name")

        if not name:
            self.report_unmapped(
                "technique_without_name", technique_id
            )
            return None

        self.add_node("Technique", {
            "id": technique_id,
            "name": name,
            "is_subtechnique": "." in technique_id,
            "description": technique.get("summary"),
            "source_url": technique.get("url"),
            "is_provisional": provisional,
        })

        self.add_mention(
            "Technique", technique_id, chunk_id
        )

        for tactic_name in tactic_names(
            technique.get("tactic")
        ):
            tactic_id = self.ensure_tactic(tactic_name)

            self.add_semantic(
                "BELONGS_TO",
                "Technique", technique_id,
                "Tactic", tactic_id,
                chunk_id,
                f"Technique {technique_id} is associated "
                f"with tactic {tactic_name} in the source record."
            )

        return technique_id

    def process_targets(
        self,
        group_id: str,
        item: dict,
        chunk_id: str,
    ):
        for raw_sector in item.get("target_sectors", []):
            country_id = self.ensure_country(raw_sector)

            if country_id:
                self.add_semantic(
                    "TARGETS",
                    "Group", group_id,
                    "Country", country_id,
                    chunk_id,
                    f"The source lists {raw_sector} among "
                    f"the targets of {item['name']}."
                )
                continue

            sector_id = self.ensure_sector(raw_sector)

            if sector_id:
                self.add_semantic(
                    "TARGETS",
                    "Group", group_id,
                    "Sector", sector_id,
                    chunk_id,
                    f"The source lists {raw_sector} "
                    f"as a target sector of {item['name']}."
                )

        for region in item.get("target_regions", []):
            country_id = self.ensure_country(region)

            if country_id:
                self.add_semantic(
                    "TARGETS",
                    "Group", group_id,
                    "Country", country_id,
                    chunk_id,
                    f"The source lists {region} as a target region."
                )
            else:
                self.report_unmapped("target_region", region)

        origin = item.get("suspected_origin")

        if origin:
            country_id = self.ensure_country(origin)

            if country_id:
                attribution = item.get("attributed_by", "")

                self.add_semantic(
                    "ASSOCIATED_WITH",
                    "Group", group_id,
                    "Country", country_id,
                    chunk_id,
                    f"{item['name']} has suspected origin "
                    f"{origin}. Attribution: {attribution}."
                )

    def load_documents(self, datasets):
        print("\n[1] Criando documentos e chunks...")

        for dataset, items in datasets.items():
            for item in items:
                self.create_context(dataset, item)

        print(f"  Documentos: {len(self.documents)}")
        print(f"  Chunks: {len(self.chunks)}")

    def load_group_records(self, datasets):
        print("\n[2] Registrando grupos...")

        for dataset in ("apt-groups", "ransomware-groups"):
            for item in datasets[dataset]:
                entity_id = self.register_group(dataset, item)
                chunk_id = self.contexts[
                    (dataset, item.get("slug") or slugify(item["name"]))
                ]
                self.add_mention("Group", entity_id, chunk_id)

        print(f"  Grupos únicos: {len(self.nodes['Group'])}")

    def load_software_records(self, datasets):
        print("\n[3] Registrando softwares...")

        for item in datasets["malware"]:
            entity_id = self.register_software(item)
            chunk_id = self.contexts[
                ("malware", item.get("slug") or slugify(item["name"]))
            ]
            self.add_mention("Software", entity_id, chunk_id)

        print(f"  Softwares únicos: {len(self.nodes['Software'])}")

    def load_official_technique_records(self, datasets):
        print("\n[4] Registrando técnicas e táticas...")

        for item in datasets["attack-techniques"]:
            chunk_id = self.contexts[
                ("attack-techniques", item.get("slug") or slugify(item["name"]))
            ]

            self.ensure_technique({
                "id": item.get("mitre_attack_id"),
                "name": item.get("name"),
                "summary": item.get("summary"),
                "url": item.get("url"),
                "tactic": item.get("tactic"),
            }, chunk_id, provisional=False)

        print(f"  Técnicas: {len(self.nodes['Technique'])}")
        print(f"  Táticas: {len(self.nodes['Tactic'])}")

    def load_group_relationships(self, datasets):
        print("\n[5] Criando relacionamentos dos grupos...")

        for dataset in ("apt-groups", "ransomware-groups"):
            for item in datasets[dataset]:
                group_id = self.group_record_ids[
                    (dataset, item.get("slug") or slugify(item["name"]))
                ]

                chunk_id = self.contexts[
                    (dataset, item.get("slug") or slugify(item["name"]))
                ]

                # APT tools
                for tool in item.get("tools", []):
                    if not isinstance(tool, dict):
                        continue

                    name = tool.get("name")
                    if not name:
                        continue

                    software_id = self.ensure_software(
                        name, tool.get("type")
                    )

                    self.add_semantic(
                        "USES",
                        "Group", group_id,
                        "Software", software_id,
                        chunk_id,
                        f"{item['name']} lists {name} in its tools."
                    )

                # Ransomware malware
                for malware in item.get("malware", []):
                    if not isinstance(malware, dict):
                        continue

                    name = malware.get("name")
                    if not name:
                        continue

                    software_id = self.ensure_software(
                        name, "malware", malware.get("url")
                    )

                    self.add_semantic(
                        "USES",
                        "Group", group_id,
                        "Software", software_id,
                        chunk_id,
                        f"{item['name']} lists {name} "
                        f"in its malware field."
                    )

                # Group attack techniques
                for technique in item.get("attack_techniques", []):
                    if not isinstance(technique, dict):
                        continue

                    technique_id = self.ensure_technique(
                        technique,
                        chunk_id,
                        provisional=True
                    )

                    if technique_id:
                        self.add_semantic(
                            "USES",
                            "Group", group_id,
                            "Technique", technique_id,
                            chunk_id,
                            f"{item['name']} is associated with "
                            f"technique {technique_id}."
                        )

                self.process_targets(
                    group_id, item, chunk_id
                )

    def load_malware_relationships(self, datasets):
        print("\n[6] Criando relacionamentos dos malwares...")

        for item in datasets["malware"]:
            slug = item.get("slug") or slugify(item["name"])
            software_id = self.software_record_ids[slug]
            chunk_id = self.contexts[("malware", slug)]

            # Groups using the malware
            for group in item.get("used_by", []):
                if not isinstance(group, dict):
                    continue

                group_name = group.get("name")

                if not group_name:
                    continue

                group_id = self.ensure_group(
                    group_name, group.get("url")
                )

                self.add_semantic(
                    "USES",
                    "Group", group_id,
                    "Software", software_id,
                    chunk_id,
                    f"Malware record lists {group_name} "
                    f"in used_by for {item['name']}."
                )

            # Malware attack techniques
            for technique in item.get("attack_techniques", []):
                if not isinstance(technique, dict):
                    continue

                technique_id = self.ensure_technique(
                    technique,
                    chunk_id,
                    provisional=True
                )

                if technique_id:
                    self.add_semantic(
                        "USES",
                        "Software", software_id,
                        "Technique", technique_id,
                        chunk_id,
                        f"{item['name']} is associated with "
                        f"technique {technique_id}."
                    )

    def load_nodes(self, label: str, rows: list):
        if not rows:
            return

        query = f"""
        UNWIND $rows AS row
        MERGE (n:{label} {{id: row.id}})
        SET n += row
        """

        for batch in batches(rows):
            self.graph.query(
                query,
                params={"rows": batch}
            )

    def load_semantic_edges(self):
        grouped = defaultdict(list)

        for edge in self.edges.values():
            key = (
                edge["relation"],
                edge["from_label"],
                edge["to_label"],
            )

            grouped[key].append(edge)

        for (relation, from_label, to_label), rows in grouped.items():

            query = f"""
            UNWIND $rows AS row

            MATCH (a:{from_label} {{id: row.from_id}})
            MATCH (b:{to_label} {{id: row.to_id}})

            MERGE (a)-[r:{relation} {{chunk_id: row.chunk_id}}]->(b)

            SET r.source = row.source,
                r.evidence = row.evidence,
                r.confidence = row.confidence
            """

            for batch in batches(rows):
                self.graph.query(
                    query,
                    params={"rows": batch}
                )

    def load_structural_edges(self):
        print("\n[8] Criando relacionamentos estruturais...")

        part_rows = [
            {"chunk_id": chunk, "doc_id": doc}
            for chunk, doc in self.parts_of
        ]

        for batch in batches(part_rows):
            self.graph.query("""
                UNWIND $rows AS row
                MATCH (c:Chunk {id: row.chunk_id})
                MATCH (d:Document {id: row.doc_id})
                MERGE (c)-[:PART_OF]->(d)
            """, params={"rows": batch})

        grouped = defaultdict(list)

        for label, entity_id, chunk_id in self.mentions:
            grouped[label].append({
                "entity_id": entity_id,
                "chunk_id": chunk_id,
            })

        for label, rows in grouped.items():
            for batch in batches(rows):
                self.graph.query(f"""
                    UNWIND $rows AS row
                    MATCH (n:{label} {{id: row.entity_id}})
                    MATCH (c:Chunk {{id: row.chunk_id}})
                    MERGE (n)-[:MENTIONED_IN]->(c)
                """, params={"rows": batch})

    def save_audit_files(self):
        PROCESSED.mkdir(parents=True, exist_ok=True)

        def write_jsonl(path, rows):
            with path.open("w", encoding="utf-8") as file:
                for row in rows:
                    file.write(
                        json.dumps(row, ensure_ascii=False) + "\n"
                    )

        write_jsonl(
            PROCESSED / "chunks.jsonl",
            list(self.chunks.values())
        )

        triples = []

        for edge in self.edges.values():
            head = self.nodes[edge["from_label"]][edge["from_id"]]
            tail = self.nodes[edge["to_label"]][edge["to_id"]]

            triples.append({
                "head": {
                    "label": edge["from_label"],
                    "id": edge["from_id"],
                    "name": head.get("name"),
                },
                "relation": edge["relation"],
                "tail": {
                    "label": edge["to_label"],
                    "id": edge["to_id"],
                    "name": tail.get("name"),
                },
                "chunk_id": edge["chunk_id"],
                "evidence": edge["evidence"],
                "confidence": edge["confidence"],
                "prompt_version": "structured-brandefense-v1",
            })

        write_jsonl(
            PROCESSED / "brandefense_reference_triples.jsonl",
            triples
        )

        (PROCESSED / "unmapped_values.json").write_text(
            json.dumps(
                self.unmapped,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

    def run(self, datasets):
        self.load_documents(datasets)
        self.load_group_records(datasets)
        self.load_software_records(datasets)
        self.load_official_technique_records(datasets)
        self.load_group_relationships(datasets)
        self.load_malware_relationships(datasets)

        print("\n[7] Inserindo nós no FalkorDB...")

        for label, nodes in self.nodes.items():
            rows = list(nodes.values())
            self.load_nodes(label, rows)

            print(f"  {label}: {len(rows)}")

        print("\n[9] Inserindo relacionamentos semânticos...")
        self.load_semantic_edges()

        self.load_structural_edges()

        self.save_audit_files()

        stats = {
            "nodes": {
                label: len(rows)
                for label, rows in self.nodes.items()
            },
            "documents": len(self.documents),
            "chunks": len(self.chunks),
            "semantic_relationships": len(self.edges),
            "part_of": len(self.parts_of),
            "mentioned_in": len(self.mentions),
            "unmapped_values": len(self.unmapped),
        }

        (PROCESSED / "ingestion_summary.json").write_text(
            json.dumps(stats, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        print("\nINGESTÃO CONCLUÍDA")
        print(json.dumps(stats, indent=2, ensure_ascii=False))


def load_datasets():
    datasets = {}

    for dataset, filename in FILES.items():
        path = RAW / filename

        if not path.exists():
            raise FileNotFoundError(
                f"Arquivo não encontrado: {path}"
            )

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data.get("items"), list):
            raise ValueError(
                f"Formato inválido: {filename}"
            )

        datasets[dataset] = data["items"]

    return datasets


def main():
    load_dotenv(ROOT / ".env")

    with SCHEMA_FILE.open("r", encoding="utf-8") as file:
        schema = yaml.safe_load(file)

    if schema["graphs"]["gold"] != "cti_gold":
        raise ValueError("Nome inesperado para o grafo gold.")

    datasets = load_datasets()

    db = FalkorDB(
        host=os.getenv("FALKORDB_HOST", "127.0.0.1"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
    )

    graph = db.select_graph("cti_gold")

    importer = BrandefenseImporter(graph, schema)
    importer.run(datasets)


if __name__ == "__main__":
    import os
    sys.exit(main())
