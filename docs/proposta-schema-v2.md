# Proposta de schema v2 (dataset Brandefense)
Proposta do módulo de Recuperação para o dono do `schema/` aplicar. Números medidos em `data/raw/` (manifest de 12/11/2026). "Extraível" = % dos itens do gabarito cujo nome aparece literalmente no texto que o LLM de extração pode ler.

## Labels
| Label | ID | Propriedades (além de `id`, `name`) |
|---|---|---|
| Group | `group:<slug>` | `kind` (apt\|ransomware), `aliases`, `aliases_text`, `description`, `status`, `motivation`, `attributed_by`, `first_seen`, `model`, `extortion`, `mitre_id`, `sectors_raw`, `regions_raw`, `url`, `embedding` |
| Software | `software:<slug>` | `type_raw`, `aliases`, `aliases_text`, `platforms`, `first_seen`, `mitre_id`, `has_page`, `description` |
| Technique | ID ATT&CK (`T1592.002`) | `is_subtechnique`, `has_page`, `description`, `embedding` |
| Tactic | `tactic:<slug>` | — |
| Sector | `sector:<slug>`, lista fechada | — |
| Country | `country:<ISO alfa-2>` | — |
| Document | `doc:brandefense:<arquivo>:<slug>` | `title`, `url`, `source`, `last_updated` |
| Chunk | `<doc_id>#<n>` | `text`, `embedding` |

## Relações
Propriedades em toda relação semântica: `source` (gold\|extracted), `doc_id`, `chunk_id` (vazio no gold), `evidence` (`structured:<arquivo>.<campo>` no gold), `confidence` (1.0 no gold).

| Relação | De → Para | Gabarito (campo) | Extraível do texto? |
|---|---|---|---|
| USES | Group → Software | `apt-groups.tools`, `ransomware-groups.malware`, `malware.used_by` | Pouco: 2% (APT), 13% (ransomware), 22% (malware) |
| USES | Group → Technique | `apt-groups.attack_techniques` | Não: 1/685 |
| USES | Software → Technique | `malware.attack_techniques` | Não: 1/732 |
| SUBTECHNIQUE_OF | Technique → Technique | derivado do ID (`T1592.002` → `T1592`) | Não se aplica (estrutural) |
| BELONGS_TO | Technique → Tactic | `attack_techniques[].tactic`, `attack-techniques.tactic` | Parcial: 40% nas páginas de técnica |
| TARGETS | Group → Sector | `target_sectors` (mapeado na lista fechada) | Parcial: 15% (APT), 6% (ransomware) |
| TARGETS | Group → Country | `apt-groups.target_regions` (só os que viram 1 país) | Parcial: 10% |
| ASSOCIATED_WITH | Group → Country | `apt-groups.suspected_origin` | Sim: 65% |
| DESCRIBES | Document → Group, Software, Technique | página de origem do item | Estrutural |
| PART_OF | Chunk → Document | divisão em chunks | Estrutural |
| MENTIONED_IN | Group, Software, Technique, Tactic, Sector, Country → Chunk | só no `cti_extracted` | É a própria extração |

## Decisões
- **APT e ransomware no mesmo label `Group` com `kind`:** sim. Têm as mesmas relações (USES, TARGETS) e um caso real nos dois arquivos (Cl0p), então uma consulta só serve aos dois.
- **Regiões:** viram `Country` quando o texto mapeia para exatamente um país; o resto ("Europe", "NATO members", "Worldwide") fica na propriedade `regions_raw`. Um label `Region` não teria gabarito: as 64 grafias misturam continentes, blocos e listas de países.
- **Setores sem mapeamento:** `Sector.allowed_values` deixa de ser vazio, e não há nó `sector:other`. Ficam em `sectors_raw` e em `data/processed/unmapped_sectors.csv`. São 317 grafias distintas; a lista fechada proposta tem 20 slugs (government, defense, aerospace, financial, healthcare, energy, telecommunications, technology, education, manufacturing, transportation, retail, media, legal, research, cryptocurrency, ngo, hospitality, construction, agriculture).
- **Táticas:** dividir as que vêm juntas ("Persistence, Privilege Escalation") e unificar maiúsculas; 28 grafias viram as táticas do ATT&CK atual, incluindo Stealth e Defense Impairment.
- **Software e técnica sem página** viram nó com `has_page=false`: 333 nomes de tool e 316 técnicas citadas não têm página. Antes de criar, casar por nome, alias e slug da URL (129 de 480 referências casam).

## O que sai do schema atual (v1)
- **Vulnerability, Product, Vendor, AFFECTS, MADE_BY, EXPLOITS:** ficam `enabled: false`, porque não há nenhum campo de CVE no dataset.
- **ID do MITRE como chave de Group, Software e Tactic:** vira a propriedade `mitre_id`. 5 de 52 APT, os ransomware e os softwares sem página não têm ID do MITRE, e o dataset não traz `TA00xx`.
- **`Software.type` restrito a [malware, tool]:** vira `type_raw`. `malware.type` (rat, wiper...) e `tools[].type` (Backdoor, Web shell...) usam vocabulários diferentes.
- **`chunk_id` e `evidence` obrigatórios com texto:** o gold vem de campos estruturados e não tem trecho; por isso `doc_id` passa a ser obrigatório e o `chunk_id` fica vazio.

## 10 perguntas multi-hop
| # | Pergunta | Caminho |
|---|---|---|
| 1 | Que técnicas de Credential Access o Andariel usa? | `(:Group)-[:USES]->(:Technique)-[:BELONGS_TO]->(:Tactic)` |
| 2 | Que grupos norte-coreanos usam ransomware? | `(:Country)<-[:ASSOCIATED_WITH]-(:Group)-[:USES]->(:Software)` |
| 3 | Que grupos compartilham software com o Sandworm? | `(:Group)-[:USES]->(:Software)<-[:USES]-(:Group)` |
| 4 | Que táticas as técnicas do AcidRain cobrem? | `(:Software)-[:USES]->(:Technique)-[:BELONGS_TO]->(:Tactic)` |
| 5 | Que ransomware atacam saúde e usam Cobalt Strike? | `(:Sector)<-[:TARGETS]-(:Group)-[:USES]->(:Software)` |
| 6 | Que técnicas-pai têm subtécnicas usadas por grupos russos? | `(:Country)<-[:ASSOCIATED_WITH]-(:Group)-[:USES]->(:Technique)-[:SUBTECHNIQUE_OF]->(:Technique)` |
| 7 | Que softwares de grupos chineses fazem credential dumping (T1003)? | `(:Country)<-[:ASSOCIATED_WITH]-(:Group)-[:USES]->(:Software)-[:USES]->(:Technique)` |
| 8 | Que países são alvo de grupos que usam o mesmo software que o Lazarus? | `(:Group)-[:USES]->(:Software)<-[:USES]-(:Group)-[:TARGETS]->(:Country)` |
| 9 | Que táticas usam os grupos iranianos que atacam governo? | `(:Sector)<-[:TARGETS]-(:Group)-[:ASSOCIATED_WITH]->(:Country)`, `(:Group)-[:USES]->(:Technique)-[:BELONGS_TO]->(:Tactic)` |
| 10 | Que trecho fundamenta que o Andariel usa o MagicRAT? | `(:Chunk)-[:PART_OF]->(:Document)-[:DESCRIBES]->(:Group)-[:USES]->(:Software)` |

Todas têm resposta não vazia nos JSON do gabarito (conferido em 14/11/2026). As perguntas 1 a 9 não têm resposta via texto na maior parte dos casos: o recall do `cti_extracted` nelas deve ser baixo.
