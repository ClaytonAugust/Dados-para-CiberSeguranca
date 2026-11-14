# CLAUDE.md — guia do projeto CTI GraphRAG

Regras para qualquer pessoa ou agente que edite este repositório.

## Idioma e nomes
- Inglês no código, schema, labels e prompts. Português na resposta ao usuário, na interface, no README e no artigo.
- Labels em PascalCase singular, relações em UPPER_SNAKE_CASE, propriedades e funções em snake_case.
- `schema/schema.yaml` é a única fonte de labels e relações; nada de label digitado solto no código.

## Escopo
- O módulo de Recuperação (Luiz) pode editar `src/cti_graphrag/` (inclusive `graph/` e `config.py`), `tests/`, `eval/` e `docs/`.
- `schema/` é do responsável pela infraestrutura: mudanças entram como proposta em `docs/` e ele aplica.

## Dados
- Fonte: Brandefense threat-actor-dataset, licença CC-BY-4.0. Detalhes em `docs/dataset.md`.
- `data/raw/` continua no Git por decisão do grupo (commit de 12/11/2026); o download por `scripts/download_brandefense.py` confere o sha256 do `manifest.json`.
- Nunca commitar `.env`.

## IDs (proposta; vale depois que o dono do schema aprovar)
| Entidade | Formato | Exemplo |
|---|---|---|
| Group (APT e ransomware, com `kind`) | `group:<slug>` | `group:andariel` |
| Software (malware.json + tools) | `software:<slug>` | `software:acidrain` |
| Technique | ID do ATT&CK | `T1592.002` |
| Tactic | `tactic:<slug>` | `tactic:credential_access` |
| Sector | `sector:<slug>`, lista fechada | `sector:healthcare` |
| Country | `country:<ISO alfa-2>` | `country:KP` |
| Document | `doc:brandefense:<arquivo>:<slug>` | `doc:brandefense:apt-groups:andariel` |
| Chunk | `<doc_id>#<n>` | `doc:brandefense:apt-groups:andariel#0` |

- `mitre_id` vira propriedade quando existir.
- Vulnerability, Product e Vendor (e AFFECTS, MADE_BY, EXPLOITS) ficam com `enabled: false`: não há dados no dataset. Geradores de prompt e o `cypher_guard` ignoram o que estiver desativado.
- Setor não mapeado: sem nó `sector:other`; guardar em `sectors_raw` e em `data/processed/unmapped_sectors.csv`.
- Relações gold: `chunk_id` vazio, `doc_id` preenchido, `evidence="structured:<arquivo>.<campo>"`, `confidence=1.0`.
- Software: casar tools com `malware.json` por nome, alias e slug da URL antes de criar nó novo.

## Objeto Answer (Recuperação → interface e avaliação)
```json
{"answer": "Andariel usa o MagicRAT [P1]...",
 "paths": [{"id": "P1", "nodes": ["group:andariel", "software:magicrat"], "rels": ["USES"],
            "chunk_ids": ["doc:brandefense:apt-groups:andariel#0"]}],
 "nodes": [{"id": "group:andariel", "label": "Group", "name": "Andariel"}],
 "edges": [{"from": "group:andariel", "to": "software:magicrat", "type": "USES"}],
 "cypher": "MATCH ...", "confidence": 0.81, "latency_ms": 2300}
```
- Toda afirmação da resposta cita um caminho (`[P1]`). Um validador confere se cada `[Pn]` existe e se cada entidade citada está no contexto.
- Contexto vazio devolve "Não encontrei isso no grafo", sem chamar o LLM.
- Cypher gerado por LLM é só leitura (bloquear CREATE, MERGE, SET, DELETE, REMOVE, DROP e CALL fora de uma lista permitida), usa só labels e relações do schema e sempre tem LIMIT.
- Valores vindos do usuário entram no Cypher como parâmetros, nunca por concatenação de string.

## Configuração
- `.env` com FALKORDB_HOST, FALKORDB_PORT, GRAPH_NAME, LLM_MODEL, LLM_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIM=384, PROMPT_VERSION.
- LLM sempre via LiteLLM. Embeddings com BAAI/bge-small-en-v1.5.
- FalkorDB não é Neo4j (sem APOC, vetor com `vecf32()`, constraints por comando próprio): rode toda consulta contra o banco real antes de colocá-la no código e consulte a documentação da versão instalada.

## Avaliação honesta
- `cti_gold` é montado só a partir dos campos estruturados dos JSON.
- `cti_extracted` é montado só a partir do que o LLM leu nos textos (`summary`, `model`, `extortion`). O LLM de extração nunca recebe `tools`, `attack_techniques`, `target_sectors` nem as páginas `.md`.
- O recall de USES contra o gold vai ser baixo, porque os resumos quase não citam ferramentas. Isso é resultado a relatar, não defeito a corrigir vazando o gabarito.
- `expected_ids` de cada pergunta de teste sai de uma consulta Cypher sobre o `cti_gold`, guardada junto da pergunta. Nada de resposta esperada escrita de memória.
- Nunca ajuste código, prompt ou pergunta só para um teste passar. Se um resultado for ruim, mostre o número real e a causa provável.
- Chamadas de LLM na avaliação usam cache em disco (chave = modelo + versão do prompt + entrada).

## Como trabalhar
- Uma fase por vez; antes de editar, um plano curto (arquivos e o que muda em cada um).
- Cada fase em partes pequenas (em geral um arquivo ou uma função). Para cada parte: dizer em uma linha o que vai fazer, fazer só aquilo, terminar com um bloco "Como verificar" (comando + resultado esperado), rodar o comando e colar a saída real, fazer o commit e parar até o "ok".
- Testes unitários não dependem de internet nem de chave de API: o LLM é substituído por um dublê. O que precisa do banco ou do LLM real leva o marcador `integration`.
- Git: uma branch por tarefa (ex.: `feat/retrieval-hybrid`), Conventional Commits, um commit por passo que funciona, nunca push direto na `main`.
- Antes de dizer que terminou: `ruff check .` e `pytest -m "not integration"` passando, com a saída real no relatório.
- Se faltar informação ou uma decisão for do grupo, pergunte. Não escolha em silêncio.

## README.md
Ao fim de cada parte verificada, atualizar em português e em poucas linhas: Como rodar, Dados, Schema e IDs, Decisões (tabela com data, decisão, alternativas descartadas e motivo), Como funciona, Resultados (só números de `eval/results/`, com o caminho), Limitações e pendências. Anotar apenas o que já foi verificado.

## Relatório de checkpoint (fim de cada fase)
1. O que foi feito
2. Arquivos criados ou alterados
3. Comandos executados e saída real
4. Decisões tomadas e por quê
5. O que NÃO foi feito ou ficou frágil (obrigatório)
6. O que foi anotado no README.md
7. Dúvidas e decisões que dependem do Luiz ou do grupo
