# Dados-para-CiberSeguran-a
Trabalho de Ricardo Roberto de Lima;
Desenvolvimento de um sistema avançado de **GraphRAG** (Graph-Augmented Retrieval-Augmented Generation) e
**KAG** (Knowledge-Augmented Generation) integrando **Python**, **Neo4j** e **LLMs**

## Requisitos

- Windows 10/11 atualizado.
- Docker Desktop iniciado e com engine Linux funcionando.
- Python 3.10+ (recomendado: Python 3.11+).
- PowerShell.

## 1. Configurar variáveis

No PowerShell, na raiz do projeto:

```powershell
Copy-Item .env.example .env
```

## 2. Iniciar FalkorDB

```powershell
docker compose up -d
```

O serviço publica as portas somente em `127.0.0.1`:

- `6379`: conexão do cliente Python.
- `3000`: FalkorDB Browser.

A imagem `falkordb/falkordb` inclui o servidor e o Browser. O volume `falkordb_data` e AOF mantêm os dados entre reinicializações do container.

Abrir o Browser: <http://localhost:3000>

Verificar o container:

```powershell
docker compose ps
docker compose logs --tail 100 falkordb
docker exec cti-falkordb redis-cli ping
```

A última linha deve retornar `PONG`.

## 3. Preparar Python

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Se o PowerShell bloquear a ativação do ambiente virtual, execute nesta janela:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 4. Testar a conexão

Com o container rodando e a `.venv` ativa:

```powershell
pytest tests/test_connection.py -v
```

Saída esperada: `4 passed`. Os testes conectam no grafo do `GRAPH_NAME`, conferem que um valor passado como parâmetro volta como texto (sem ser executado), que `read_only=True` recusa escrita e que o timeout corta uma consulta lenta. Não importam dados do dataset.

## 5. Operações úteis

Parar os containers sem apagar os dados:

```powershell
docker compose down
```

Iniciar novamente:

```powershell
docker compose up -d
```

Acompanhar logs:

```powershell
docker compose logs -f falkordb
```

**Atenção:** não use `docker compose down -v` enquanto quiser preservar o banco. A opção `-v` remove o volume `falkordb_data` e os dados persistidos.

## Como rodar

Com a `.venv` ativa, na raiz do projeto:

```powershell
ruff check .                      # lint
pytest -m "not integration"       # testes unitários (sem banco, sem internet)
pytest -m integration             # FalkorDB real; inclui o teste de conexão da seção 4
```

Carga do grafo gold (idempotente, pode rodar de novo):

```powershell
python -m cti_graphrag.ingest.normalize   # contagens de mapeamento + CSVs de revisão
python -m cti_graphrag.ingest.chunks      # data/processed/chunks.jsonl (181 chunks)
python -m cti_graphrag.ingest.load_gold   # grava o cti_gold e imprime contagens
python -m cti_graphrag.ingest.load_gold --reset   # apaga e recarrega; use ao mudar mapeamento ou schema
```

O `.env` precisa ter todas as variáveis do `.env.example`. Se faltar alguma, `cti_graphrag.config.load_settings()` falha listando todas as ausentes de uma vez.

## Dados

- Fonte: Brandefense threat-actor-dataset (CC-BY-4.0), em `data/raw/` (versionado no Git).
- Lidos e validados com Pydantic (`src/cti_graphrag/ingest/`): 52 APT, 28 ransomware, 59 malwares e 42 técnicas, iguais ao `meta.count` de cada arquivo.
- Limpeza na leitura: aliases em dois formatos (objeto nas APT, string nos demais) viram lista de strings; strings vazias viram nulo (ex.: 8 APT sem `suspected_origin`); táticas combinadas são separadas e a grafia unificada, o que reduz 28 grafias a 17 táticas; `motivation` em PHP serializado (`a:1:{i:0;s:9:"espionage";}`) ou texto com vírgulas vira lista (4 valores: espionage, financial, influence, sabotage); 5 nomes de grupo ou malware que eram título de artigo (ex.: "Amadey Malware: How the Loader Works...") viram o nome curto ("Amadey"), com o original em `title_raw`.
- Nome de técnica: vale o das listas `attack_techniques` de grupos e malwares (nome do ATT&CK); a página de `attack-techniques.json` só é usada para os 7 IDs que nenhuma lista cita, sem o final " (Txxxx)" ou " (Txxxx): ATT&CK Technique" (original em `title_raw`).
- Normalização (`python -m cti_graphrag.ingest.normalize`), medida em 14/11/2026:
  - **Setores:** 475 referências (317 grafias), lista fechada de 21 slugs. Em algum setor: 385 (81,1%). Só país, que vira `Country`: 27 (5,7%). Sem mapeamento: 63 (13,3%; 58 grafias), em `sectors_raw` e em `data/processed/unmapped_sectors.csv`. O casamento é por palavra-chave (regex buscada em qualquer parte do texto, sem diferenciar maiúsculas), não exato nem fuzzy.
  - **Regiões:** 131 referências; 91 viram só países, 7 viram países com sobra em `regions_raw` e 33 não têm país (ex.: "Europe", "Worldwide"); 43 países distintos.
  - **Origem:** 39 `attributed`, 2 `suspected`, 11 sem aresta (8 vazias e 3 "Not stated/Not attributed").
  - **Tools:** 480 referências. 21 são compostas e seguem a revisão manual em `data/curated/composite_tools.csv` (16 divididas, 2 viram alias, 3 puladas), o que dá 499 alvos. Casam com `malware.json` 31 pelo slug da URL, 91 pelo nome e 8 por alias (49 dos 59 softwares); 369 não casam e viram 345 nós Software novos.
  - Mapeamento completo de setores para revisão em `data/curated/sector_mapping_review.csv` (grafia | setores | país | contagem).
- USES: o STIX do dataset (`data/stix/threat-actors.stix.json` do repositório da Brandefense, contado em 14/11/2026) tem 1.535 `uses` porque não inclui o campo `tools` das APT: 685 técnicas das APT + 732 dos malwares + 118 (31 malwares de ransomware + 87 `used_by`), conta que confere com os JSON.
- O `cti_gold` tem 1.934 USES: inclui as tools das APT, dividindo as compostas e deduplicando por par.
- Chunks (`data/processed/chunks.jsonl`): 1 por registro, 181 no total; texto = `summary` (no ransomware também `model` e `extortion`), sem nenhuma lista estruturada. Tamanho do texto: mínimo 204, mediana 328, máximo 938 caracteres.
- Slug repetido é checado por arquivo: akira, black-basta, conti e revil existem como grupo de ransomware e como malware, e isso é esperado.

## Schema e IDs

- Vale hoje o `schema/schema.yaml` v1 (IDs do MITRE como chave, com Vulnerability, Product e Vendor).
- Proposta v2 para o dataset Brandefense em `docs/proposta-schema-v2.md`, **ainda não aplicada**: IDs por slug (`group:<slug>`, `software:<slug>`, `tactic:<slug>`), `mitre_id` como propriedade, Group com `kind` (apt/ransomware) e Vulnerability, Product e Vendor com `enabled: false`.
- O `cti_gold` já é carregado com os IDs da proposta, mas só com labels e relações que existem no v1 (lidas do `schema.yaml` pelo loader). Carga de 14/11/2026, igual em duas execuções seguidas:
  - Nós: Group 80 (52 APT + 28 ransomware), Software 404 (59 com página + 345 sem), Technique 390 (358 citadas + 32 técnicas-pai derivadas de subtécnicas), Tactic 17, Sector 21, Country 49, Document 181, Chunk 181.
  - Arestas: USES 1.934 (Group→Software 517, Group→Technique 685, Software→Technique 732), TARGETS 530, BELONGS_TO 431 (39 derivadas), SUBTECHNIQUE_OF 206, ASSOCIATED_WITH 42, PART_OF 181, MENTIONED_IN 181.
  - Pulado com aviso: DESCRIBES, que não existe no v1 (181 arestas: 80 Group, 59 Software, 42 Technique).
- Medido nos JSON: o texto dos resumos quase não cita ferramentas (2% das tools das APT) nem técnicas (1 de 685), então o recall de `USES` do `cti_extracted` contra o gold deve ser baixo.

## Decisões

| Data | Decisão | Alternativas descartadas | Motivo |
|---|---|---|---|
| 14/11/2026 | `config.py` exige as 8 variáveis do `.env`, inclusive `LLM_MODEL` e `LLM_API_KEY`; valor vazio conta como ausente | Validar só as variáveis de cada módulo | Erro de configuração aparece cedo e num lugar só |
| 14/11/2026 | Variável de ambiente do processo tem prioridade sobre o `.env` | Só o arquivo | Permite trocar o grafo (`GRAPH_NAME=cti_extracted`) sem editar arquivo |
| 14/11/2026 | `requirements.txt` convertido de UTF-16 para UTF-8, com `pytest` e `ruff` fixados | Manter UTF-16 | Padrão das ferramentas Python e diffs legíveis no Git |
| 14/11/2026 | `run_query` com `read_only=True` usa `GRAPH.RO_QUERY` | Só filtrar palavras-chave no Cypher | O próprio servidor recusa escrita; o filtro do `cypher_guard` vira uma segunda barreira, não a única |
| 14/11/2026 | Timeout padrão de 10 s por consulta, aplicado pelo servidor | Sem timeout; timeout só no socket | Consulta gerada por LLM pode explodir em caminhos; o servidor corta e devolve erro claro |
| 14/11/2026 | Modelos Pydantic com `extra="forbid"` | Aceitar campos extras em silêncio | Se a Brandefense mudar o formato, a leitura falha em vez de perder dado sem aviso |
| 14/11/2026 | `motivation` em PHP serializado é lido pelas strings entre aspas, ignorando o tamanho declarado | Desserializar PHP de verdade | O dado traz `s:10:"espionage"` (9 letras); um desserializador estrito falharia |
| 14/11/2026 | Nome de grupo ou malware com ":" (título de artigo) vira as N primeiras palavras, N = partes do slug ("ROMULUS ClickFix"); original em `title_raw` | Manter o título; cortar sufixos ("Malware", "Ransomware") de uma lista | O slug já diz quantas palavras tem o nome; uma lista de sufixos deixava "Delivery Platform" |
| 14/11/2026 | Technique: chave é o ID do ATT&CK; nome das listas de grupos e malwares tem prioridade sobre o título da página; ":" não é cortado em técnica | Usar o título da página | O título da página é de artigo ("Phishing (T1566): ATT&CK Technique") e o ":" é legítimo em subtécnica ("Server Software Component: Web Shell") |
| 14/11/2026 | `critical_infrastructure` entra na lista fechada (21 slugs) | Deixar sem mapeamento | 13 referências em 6 grafias; leva a cobertura em setor de 77,5% para 81,1% |
| 14/11/2026 | Setor mapeado por palavras-chave para a lista fechada; um valor pode dar vários setores ("Defense, media and communications in Japan" → defense, media, telecommunications + Japão) | Tabela manual das 317 grafias; LLM | Regras revisáveis num arquivo só (`ingest/vocab.py`) e sem chamar LLM no gold |
| 14/11/2026 | País só pelo nome ou sigla (US, UK); gentílicos ("Iranian", "Israeli") não contam | Contar gentílicos | "Israeli-made equipment" e "Russian critics" não dizem o país alvo |
| 14/11/2026 | Região em lista ("Germany, Czechia and France") vira um `Country` por item que é exatamente um país; o resto vai para `regions_raw` | Só valores com um único país, como dizia a proposta | Não perder países listados; continentes e blocos seguem sem nó |
| 14/11/2026 | Na origem, a fonte citada no fim (", per the US Cyber Safety Review Board") é ignorada | Ler o texto todo | Senão o Lapsus$ ganharia origem US, que é quem atribuiu, não a origem |
| 14/11/2026 | Tool casa com `malware.json` nesta ordem: slug da URL, nome, alias, nome em slug; sem casamento vira `software:<slug do nome>` com `has_page=false` | Criar sempre nó novo | Evita dois nós para o mesmo software (ex.: Uroburos → Snake) |
| 14/11/2026 | Carga do `cti_gold` antes do v2: IDs da proposta, só labels e relações do v1; o resto é pulado com aviso e contagem; propriedades novas (`kind`, `mitre_id`, `attribution`, `has_page`) já gravadas | Esperar o v2; gravar tudo | A Recuperação pode começar sobre dados reais; o que falta fica listado |
| 14/11/2026 | Uma aresta por (tipo, origem, destino); `doc_id`/`evidence` da primeira fonte e `doc_ids` com todas | Uma aresta por documento | O grafo responde "quem usa o quê" sem duplicar caminhos; a proveniência fica em `doc_ids` |
| 14/11/2026 | Técnica-pai ausente é criada a partir da subtécnica (T1592.002 → T1592, nome antes do ":"), com `derived_from_subtechnique=true` | Pular SUBTECHNIQUE_OF sem pai | O nome do ATT&CK já traz o pai ("Gather Victim Host Information: Software") |
| 14/11/2026 | Document (181) carregado já na parte 3 | Só na parte 4 | É label do v1 e é o alvo do `doc_id` das arestas gold |
| 14/11/2026 | `load_gold --reset` apaga o grafo e recarrega | Só MERGE | MERGE não remove nós que deixaram de existir; depois de mudar mapeamento ou schema, o reset garante um grafo limpo |
| 14/11/2026 | Chunk = 1 por registro, só texto livre (`summary`; `model` e `extortion` no ransomware) | Incluir campos estruturados no texto | O LLM de extração não pode ler o gabarito |
| 14/11/2026 | MENTIONED_IN no gold liga só o assunto do documento ao seu chunk | Buscar nomes de entidades no texto | Busca por nome é extração; no gold seria um resultado inventado |
| 14/11/2026 | Técnica com táticas diferentes em fontes diferentes recebe todas como BELONGS_TO | Escolher uma fonte | É o que os campos dizem; a divergência fica visível (ver Limitações) |
| 14/11/2026 | Técnica-pai derivada recebe BELONGS_TO para a união das táticas das subtécnicas, com `derived=true` | Deixar sem tática | Consultas por tática não perdem 32 técnicas; a marca separa o derivado do que veio da fonte |
| 14/11/2026 | ASSOCIATED_WITH tem `attribution`: `suspected` se a origem traz "(suspected)", `attributed` nos demais casos com país; sem país não há aresta e o texto vai para `origin_raw` | Aresta para todo valor; nó "Unknown" | Não inventar país e não misturar suspeita com atribuição nas respostas |

## Como funciona

- **Leitura** (`src/cti_graphrag/ingest/read.py`): `load_dataset()` valida os 4 JSON com Pydantic, recusa campo desconhecido, slug repetido e contagem diferente do `meta`.
- **Normalização** (`src/cti_graphrag/ingest/normalize.py` e `vocab.py`): `parse_origin`, `map_sector`, `map_region`, `SoftwareIndex.match` e `technique_names` transformam os campos estruturados em IDs da proposta, sem acessar o banco.
- **Carga gold** (`ingest/build_gold.py`, `ingest/load_gold.py`, `graph/schema.py`): `build_gold()` monta nós e arestas em memória; `plan_load()` descarta o que o `schema.yaml` não tem (ou tem com `enabled: false`); `write_plan()` grava com `UNWIND ... MERGE ... SET +=` em lotes de 500, e os labels no Cypher vêm só do schema.
- **Chunks** (`ingest/chunks.py`): `build_chunks()` gera 1 chunk por registro (`<doc_id>#0`); o `build_gold()` cria o nó Chunk, PART_OF → Document e MENTIONED_IN a partir do assunto do documento.
- **Configuração** (`src/cti_graphrag/config.py`): `load_settings()` lê o `.env` e devolve um objeto imutável; a chave do LLM não aparece ao imprimir.
- **Acesso ao grafo** (`src/cti_graphrag/graph/client.py`): `get_graph(name)` reaproveita uma única conexão; `run_query(cypher, params, timeout_ms=..., read_only=...)` só aceita parâmetros em dict, para nenhum valor do usuário ser colado no Cypher.

## Limitações e pendências

- Em 14/11/2026 a chamada mínima ao LLM pelo LiteLLM falhou: o Google recusou a chave (`API_KEY_INVALID`) e o `LLM_MODEL` estava com texto de exemplo. Falta corrigir o `.env` e repetir.
- `run_query` devolve o `QueryResult` cru do FalkorDB; converter para dicts fica para quando a Recuperação precisar.
- O `docs/dataset.md` do repositório não numera armadilhas (1 a 12); as correções seguem as instruções explícitas da Fase 2, não essa numeração.
- Além do final " (Txxxx): ATT&CK Technique", também é removido o final " (Txxxx)" sem o resto (5 páginas, ex.: "Web Shell (T1505.003)"); em todos os 6 casos o nome da lista tem prioridade, então isso não muda nenhum nome no grafo.
- Setores: 13,3% das referências seguem sem mapeamento; são sobretudo regiões ("Middle East"), alvos vagos ("Many sectors", "Individuals") e tipos de equipamento ("Routers and edge devices").
- Casamento de setor por palavra-chave pode perder partes de valores compostos: "Mining" em "Energy and mining" não tem slug e some.
- Políticos, partidos e eleições são mapeados em `government` (ex.: "Politicians and activists" → government, ngo).
- 3 tools compostas foram puladas (`skip`), 3 referências: "VBS and PowerShell malware", "Word and PDF lures" e "CVE-2017-11882 and CVE-2020-0674".
- DESCRIBES (181 arestas) foi pulado porque não existe no schema v1. Depois que o v2 for aplicado, falta: rodar `schema/create_indexes.py`, recarregar o `cti_gold` e fazer a parte 5 (embeddings e índice vetorial).
- Sem índices (o `create_indexes.py` não foi rodado), o MERGE procura por `id` varrendo os nós; com ~1.100 nós a carga leva poucos segundos, mas não escala.
- A carga sem `--reset` não apaga nós antigos; depois de mudar mapeamento ou schema, rode com `--reset`.
- Táticas: 25 técnicas aparecem com táticas diferentes conforme a fonte (ex.: T1140 com Stealth em 7 fontes e Defense Evasion em 1); todas viram aresta. Depois das derivadas, 36 técnicas têm mais de 1 tática e nenhuma tem 0.
- As 32 técnicas-pai derivadas não têm tática em nenhuma fonte; as 39 BELONGS_TO delas (`derived=true`) são a união das táticas das subtécnicas, não um campo do dataset.
- USES deu 1.934, acima dos ~1.535 esperados. Brutas são 1.984 (449 tools + 31 malwares de ransomware + 87 `used_by` + 685 + 732); a divisão das tools compostas soma 19 e a deduplicação por par tira 69 de Group→Software. Não achei de onde vem o 1.535.
- Cl0p (ransomware) e TA505 (APT, alias "CL0P") ficam como dois Group separados.
- "Korea (Clop)" nas regiões fica em `regions_raw`: "Korea" sozinho não diz se é Norte ou Sul.
