# Avaliação do CTI GraphRAG

Rodada de 15/11/2026, sobre o grafo `cti_gold`. Todos os números vêm dos arquivos em
`eval/results/2026-11-15/`; cada tabela indica o arquivo de origem.

## 1. Como rodar

Use o ambiente `venv`, com o FalkorDB no ar e o `.env` preenchido (`GRAPH_NAME`, `LLM_MODEL`, `GEMINI_API_KEY`).

```bash
# testes unitários (sem banco e sem LLM)
venv\Scripts\python.exe -m pytest tests/ -q

# avaliação da recuperação (sem LLM; lê o cti_gold só com ro_query)
venv\Scripts\python.exe eval/fill_expected.py          # preenche expected_ids a partir das gold_cypher
venv\Scripts\python.exe eval/run_retrieval_eval.py     # -> retrieval.csv, resumo.json

# avaliação das respostas (com LLM; cache em eval/cache/llm/, retoma de onde parou)
set PYTHONPATH=src
venv\Scripts\python.exe eval/run_eval.py --limit 5     # sem --limit roda as 30 perguntas

# extração de triplas (com LLM; cache em eval/extraction/cache/)
venv\Scripts\python.exe -m cti_graphrag.extract.texts           # 30 textos, semente 42
venv\Scripts\python.exe -m cti_graphrag.extract.extractor       # --cache-only: sem LLM
venv\Scripts\python.exe -m cti_graphrag.extract.resolve         # nomes -> ids do cti_gold
venv\Scripts\python.exe -m cti_graphrag.extract.load_extracted  # escreve só no cti_extracted
venv\Scripts\python.exe eval/compare_graphs.py                  # -> extraction.csv, extraction_meta.json
```

## 2. Métricas: como são calculadas e onde podem enganar

| métrica | cálculo | onde pode enganar |
|---|---|---|
| recall (recuperação) | ids esperados encontrados ÷ ids esperados, sobre todos os nós devolvidos pelo `HybridRetriever.retrieve` | o retriever devolve centenas de nós, então o recall sobe só pelo volume |
| precisão (recuperação) | ids esperados encontrados ÷ nós devolvidos | o gabarito lista só a resposta direta; nós intermediários úteis contam como erro |
| recall nas 12 relações | o mesmo recall, mas só sobre as pontas das 12 primeiras relações, que são as que o `GraphRAGPipeline` manda ao LLM (`max_relationships=12`) | é o que o LLM realmente vê, mas uma pergunta com mais de 12 respostas nunca chega a 1,0 |
| precisão / recall / F1 (extração) | arestas distintas (grupo, relação, id do tail) do `cti_extracted` comparadas com as do `cti_gold`, para os mesmos grupos | depende de casar nomes com ids: um acerto com nome diferente (ex.: "governments") conta como erro |
| `name_recall` (respostas) | nomes do `expected_answer` que aparecem no texto da resposta ÷ nomes esperados | busca de texto: não verifica se a afirmação está correta nem pega sinônimos |
| `abstained` (respostas) | a resposta contém uma frase de abstenção ("não encontrei", "insuficiente"...) | lista fixa de frases; uma recusa escrita de outro jeito passa despercebida |
| `confidence` (pipeline) | média da similaridade dos chunks da busca vetorial (`answer.py:327-339`) | mede a proximidade do texto, não se a resposta está correta |
| latência | tempo de relógio de cada etapa, medido embrulhando os métodos do retriever | inclui rede e banco local; varia de uma rodada para outra |

## 3. Recuperação por categoria

Fonte: `eval/results/2026-11-15/resumo.json` (`por_grupo_sem_lista_longa`, `media_principal`, `lista_longa`).
As 6 perguntas de lista longa (mais de 20 ids: q09, q13, q17, q18, q20, q23) ficam fora das linhas por categoria e da média principal.

| categoria | n | recall | precisão | recall nas 12 relações | caminhos (média) | nós (média) |
|---|---|---|---|---|---|---|
| 1 salto | 8 | 0,81 | 0,02 | 0,10 | 406 | 296 |
| 2 saltos | 7 | 0,92 | 0,03 | 0,14 | 331 | 251 |
| 3 saltos | 3 | 0,39 | 0,01 | 0,02 | 353 | 273 |
| agregação | 3 | 1,00 | 0,04 | 0,03 | 239 | 168 |
| sem resposta | 3 | – | – | – | 352 | 258 |
| **média principal** | 21 | **0,82** | **0,03** | **0,09** | | |
| lista longa | 6 | 0,70 | 0,10 | 0,02 | | |

- **Tempo médio por pergunta:** 222 ms. A busca vetorial leva 21 ms, as entidades 4 ms e a expansão 194 ms (`tempo_ms_medio`).
- **Perguntas sem resposta:** mesmo assim vêm 285, 111 e 378 nós (q28, q29, q30; `sem_resposta_nos_recuperados`). A busca vetorial nunca volta vazia.

### Caso Lazarus (q01, "Quais ferramentas o Lazarus Group usa?")

Fonte: `eval/results/2026-11-15/retrieval.csv`, linha q01.
- O retriever devolveu 451 caminhos e 354 nós, com os 14 softwares esperados entre eles (recall 1,00).
- Nas 12 relações que vão ao LLM havia só 1 dos 14 (recall 0,07). As relações são ordenadas só pela similaridade da entidade de partida.
- Por isso, na Fase A, o LLM respondeu que "não foram encontrados registros suficientes" (achado 7 em `docs/achados.md`).

## 4. Extração de triplas

Fontes: `eval/results/2026-11-15/extraction.csv` e `extraction_meta.json`.
Recorte: **N = 17 textos** extraídos dos 30 sorteados (15 APT, 2 ransomware, 0 malware). Os outros 13 falharam por erro 429 do Gemini, e a amostra ficou fechada em 17.
São 17 grupos do `cti_gold` e 3 relações. Foram extraídas 44 triplas, todas com a evidência literal no texto (44/44).
O head foi resolvido em 44/44; os tails, em Country 17/19, Sector 8/22 e Software 2/3.
Os setores passaram a casar também por palavra-chave com os nomes dos nós Sector. Depois disso, o `cti_extracted` foi apagado e recarregado.

| relação | extraídas | gold | acertos | precisão | recall | F1 |
|---|---|---|---|---|---|---|
| ASSOCIATED_WITH | 13 | 13 | 13 | 1,00 | 1,00 | 1,00 |
| TARGETS → Country | 5 | 47 | 3 | 0,60 | 0,06 | 0,12 |
| TARGETS → Sector | 22 | 23 | 4 | 0,18 | 0,17 | 0,18 |
| USES (→ Software) | 3 | 147 | 2 | 0,67 | 0,01 | 0,03 |
| total (micro) | 43 | 230 | 22 | 0,51 | 0,10 | 0,16 |

**Primeira rodada** (resolução de setores só por nome exato, Sector 3/22; `extraction.csv` do commit `c11868b`):
mudou só a linha TARGETS → Sector, com 3 acertos (precisão 0,14, recall 0,13, F1 0,13). O total era de 21 acertos (precisão 0,49, recall 0,09, F1 0,15).
Dos 5 setores que passaram a casar por palavra-chave, só 1 é aresta que existe no gold. Os outros 4 viraram ids válidos, mas o grupo não tem aquele alvo no `cti_gold`.

## 5. Respostas com LLM

**Não medida nesta rodada: cota do Gemini esgotada (erro 429).**
Na rodada de teste com 5 perguntas, as 15 linhas (3 sistemas × 5) saíram com status `erro` (`RateLimitError`).
O `eval/results/2026-11-15/answers.csv` não foi commitado. Para rodar quando a cota voltar:

```bash
set PYTHONPATH=src
venv\Scripts\python.exe eval/run_eval.py --limit 5   # depois, sem --limit, para as 30
```

## 6. Limitações

- **Amostra pequena na extração:** 17 de 30 textos e nenhum de malware, então os números da seção 4 valem só para esses 17 grupos.
- **Só 3 relações:** ASSOCIATED_WITH, TARGETS e USES (→ Software). USES → Technique e BELONGS_TO não foram avaliadas.
- **Recall de USES baixo:** os resumos quase não citam ferramentas. O gold vem das listas `tools`, que ficaram fora do texto de entrada de propósito.
- **Setores em texto livre:** mesmo casando por palavra-chave, 14 dos 22 continuam sem par ("banks", "oil and gas", "universities"...). Ligar esses nomes exigiria sinônimos.
- **Cota gratuita de 20 chamadas por dia no modelo usado** (`gemini-3.8-flash`, erro 429 `generate_content_free_tier_requests`, limite 20 por dia). Ela limitou a extração a 17 textos e impediu a avaliação das respostas.
- **Lista longa:** o critério de mais de 20 ids (igual ao `max_entities` do retriever) é uma escolha nossa e tira 6 perguntas da média principal.
- **`confidence` é similaridade média** da busca vetorial, não uma probabilidade de acerto.
- **Validação de referências só de formato:** `answer.py` confere que cada `[P#]` existe, mas não que o trecho citado sustenta a frase.

---

## Diário

- **B1** — `eval/questions.csv` com 30 perguntas: 8 de 1 salto, 12 de 2, 4 de 3, 3 de agregação e 3 sem resposta. Usa ids ATT&CK e `new:`; as 27 `gold_cypher` com resposta devolvem pelo menos 1 linha.
- **B2** — `fill_expected.py`: ficaram vazias só q28, q29 e q30.
- **B3** — `run_retrieval_eval.py`: resultados na seção 3.
- **B4** — `run_eval.py` (retry só em Timeout/503, cache, linha "erro"): 15/15 linhas com erro 429.
- **T1** — `texts.py`: 30 textos (20 APT, 5 ransomware, 5 malware), de 249 a 938 caracteres, com mediana de 341.
- **T2** — `extractor.py` em 3 textos: 8 triplas, 8/8 evidências literais. Heads genéricos ("this group") são resolvidos depois pelo `entity_name`.
- **T3** — Extração dos 30: 17 ok e 13 com 429; `resolve.py` gera `unresolved.csv`.
- **T4** — `load_extracted.py`: 45 nós e 43 arestas no `cti_extracted`; a 2ª execução não muda nada; `cti_gold` inalterado (Group 79).
- **T5** — `compare_graphs.py`: seção 4.
- **Complemento, parte 2** — Setores casados por palavra-chave no `resolve.py`, usando os nomes dos nós Sector, com o texto original em `tail_raw`. Setores resolvidos passaram de 3/22 para 8/22 (5 por palavra-chave). Fonte: `eval/extraction/triples.jsonl`. 
- **Complemento, parte 3** — Apaguei só o `cti_extracted` e recarreguei 2 vezes, com as mesmas contagens nas duas: Group 14, Country 9, Sector 17, Software 3; ASSOCIATED_WITH 13, TARGETS 27, USES 3. `cti_gold` continua com Group 79. Rodei `compare_graphs.py` de novo; o resultado está na seção 4.
