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
pytest -m integration             # testes contra o FalkorDB real (docker compose up -d)
```

O `.env` precisa ter todas as variáveis do `.env.example`. Se faltar alguma, `cti_graphrag.config.load_settings()` falha listando todas as ausentes de uma vez.

## Dados

- Fonte: Brandefense threat-actor-dataset (CC-BY-4.0), em `data/raw/` (versionado no Git).
- Lidos e validados com Pydantic (`src/cti_graphrag/ingest/`): 52 APT, 28 ransomware, 59 malwares e 42 técnicas, iguais ao `meta.count` de cada arquivo.
- Limpeza na leitura: aliases em dois formatos (objeto nas APT, string nos demais) viram lista de strings; strings vazias viram nulo (ex.: 8 APT sem `suspected_origin`); táticas combinadas são separadas e a grafia unificada, o que reduz 28 grafias a 17 táticas.

## Schema e IDs

- Vale hoje o `schema/schema.yaml` v1 (IDs do MITRE como chave, com Vulnerability, Product e Vendor).
- Proposta v2 para o dataset Brandefense em `docs/proposta-schema-v2.md`, **ainda não aplicada**: IDs por slug (`group:<slug>`, `software:<slug>`, `tactic:<slug>`), `mitre_id` como propriedade, Group com `kind` (apt/ransomware) e Vulnerability, Product e Vendor com `enabled: false`.
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

## Como funciona

- **Leitura** (`src/cti_graphrag/ingest/read.py`): `load_dataset()` valida os 4 JSON com Pydantic, recusa campo desconhecido, slug repetido e contagem diferente do `meta`.
- **Configuração** (`src/cti_graphrag/config.py`): `load_settings()` lê o `.env` e devolve um objeto imutável; a chave do LLM não aparece ao imprimir.
- **Acesso ao grafo** (`src/cti_graphrag/graph/client.py`): `get_graph(name)` reaproveita uma única conexão; `run_query(cypher, params, timeout_ms=..., read_only=...)` só aceita parâmetros em dict, para nenhum valor do usuário ser colado no Cypher.

## Limitações e pendências

- Em 14/11/2026 a chamada mínima ao LLM pelo LiteLLM falhou: o Google recusou a chave (`API_KEY_INVALID`) e o `LLM_MODEL` estava com texto de exemplo. Falta corrigir o `.env` e repetir.
- `run_query` devolve o `QueryResult` cru do FalkorDB; converter para dicts fica para quando a Recuperação precisar.
- A numeração das armadilhas citadas na Fase 2 (3, 4 e 10 na leitura) vem de um `docs/dataset.md` que não está no repositório; a leitura trata aliases em dois formatos, strings vazias e táticas combinadas, que podem não corresponder exatamente a essa numeração.
