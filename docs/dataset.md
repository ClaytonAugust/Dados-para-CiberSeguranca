# Dataset: Brandefense threat-actor-dataset

## Fonte e licença
- Repositório: <https://github.com/BRANDEFENSE/threat-actor-dataset> (publicado pela Brandefense, <https://brandefense.io>).
- Licença: **CC-BY-4.0**, conforme a API do GitHub e o bloco `meta` de cada JSON. Uso livre com crédito: "Dados: Brandefense threat-actor-dataset (CC-BY-4.0)".
- Versão usada: arquivos gerados em 28/10/2026, baixados em 12/11/2026 por `scripts/download_brandefense.py`. Os hashes sha256 ficam em `data/raw/manifest.json`.

## Arquivos (`data/raw/`)
Cada arquivo tem `{"meta": {...}, "items": [...]}`.

| Arquivo | Itens | Campos de cada item |
|---|---|---|
| `apt-groups.json` | 52 | name, slug, url, last_updated, aliases (objetos `{name, source}`), summary, status, motivation, suspected_origin, attributed_by, mitre_attack_id, target_sectors, target_regions, attack_techniques (`{tactic, id, name}`), tools (`{name, type}`), sources |
| `ransomware-groups.json` | 28 | name, slug, url, last_updated, aliases (strings), summary, status, first_seen, model, extortion, target_sectors, malware (`{name, url}`), sources |
| `malware.json` | 59 | name, slug, url, last_updated, aliases, summary, type, platforms, first_seen, used_by (`{name, url}`), attack_techniques, sources |
| `attack-techniques.json` | 42 | name, slug, url, last_updated, mitre_attack_id, tactic, summary, sources |

## Campos estruturados (gold) e textos (extração)
- **Estruturados**, só para o `cti_gold`: tools, malware, used_by, attack_techniques, target_sectors, target_regions, suspected_origin, mitre_attack_id e tactic.
- **Texto**, a única entrada do LLM de extração: summary, model e extortion.

## Medições (14/11/2026)
- **Cobertura de páginas:** 351 técnicas são citadas, mas só 35 têm página em `attack-techniques.json`. Das 480 referências a tools e malware, 129 casam com `malware.json` por slug da URL, nome ou alias, cobrindo 49 dos 59 softwares. Sobram 333 nomes distintos sem página.
- **MITRE ID:** 47 de 52 APT têm `mitre_attack_id`; os softwares não têm esse campo.
- **Quanto do gabarito aparece literalmente no texto:**

  | O quê | Onde | Taxa |
  |---|---|---|
  | Tools das APT | summary | 10/449 (2%) |
  | Técnicas das APT | summary | 1/685 |
  | Técnicas dos malwares | summary | 1/732 |
  | Setores (APT) | summary | 15% |
  | Regiões | summary | 10% |
  | Origem | summary | 34/52 (65%) |
  | Malware dos ransomware | summary + model + extortion | 4/31 (13%) |

## Problemas de limpeza encontrados (ainda não tratados)
- **Setores:** 317 grafias distintas em texto livre (ex.: "Medical and energy", "South Korean defense").
- **Regiões:** 64 grafias que misturam países, continentes, blocos e listas (ex.: "Germany, Czechia and France", "NATO members", "Worldwide").
- **Origem:** valores como "China (suspected)", "Not stated in the sources" e 8 vazios.
- **Táticas:** 28 grafias para as táticas do ATT&CK, com combinações ("Persistence, Privilege Escalation"), diferenças de maiúsculas ("Command And Control") e táticas novas (Stealth, Defense Impairment).
- **Tools compostas:** algumas entradas juntam várias ferramentas (ex.: "Atera, TeamViewer, AnyDesk and ngrok").
- **Vocabulário de tipos:** `malware.type` (rat, wiper, abused-tool...) e `tools[].type` (Backdoor, Web shell...) usam vocabulários diferentes.
- **Aliases:** objetos nas APT e strings nos ransomware.
- **Grupo duplicado:** Cl0p aparece como grupo de ransomware e como alias de uma APT.
