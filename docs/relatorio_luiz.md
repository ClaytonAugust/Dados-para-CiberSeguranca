# Relatório — avaliação e extração (Luiz, branch `feat/avaliacao`)

## 1. Resumo
Entreguei a avaliação do CTI GraphRAG: um conjunto de perguntas com gabarito tirado do próprio grafo, a medição da recuperação sem LLM e um script que compara três sistemas com LLM.
Fiz também um experimento de Text-to-Graph: o LLM extrai relações de textos, elas são gravadas num grafo separado (`cti_extracted`) e comparadas com o `cti_gold`.
Tudo tem testes automáticos que não usam banco nem LLM reais. O `cti_gold` só foi lido (`ro_query`).

## 2. O que foi feito
- **Perguntas e gabarito** — `eval/questions.csv`: 30 perguntas de 1 a 3 saltos, agregação e sem resposta. O gabarito (`expected_ids`) sai das consultas `gold_cypher`, rodadas por `eval/fill_expected.py`.
- **Recuperação sem LLM** — `eval/run_retrieval_eval.py`: chama só `HybridRetriever.retrieve` e mede recall, precisão, nº de caminhos e tempo por etapa.
- **Text-to-Graph** — `src/cti_graphrag/extract/`: `texts.py` (30 resumos sorteados, sem as listas estruturadas), `extractor.py` (triplas em JSON validado, com cache e novas tentativas), `resolve.py` (liga nomes a ids do `cti_gold`, setores também por palavra-chave), `load_extracted.py` (MERGE só no `cti_extracted`) e `eval/compare_graphs.py` (precisão, recall e F1).
- **Respostas com LLM** — `eval/run_eval.py`: LLM puro, RAG vetorial e GraphRAG na mesma pergunta, com cache em disco, novas tentativas em timeout/503 e linha "erro" quando a chamada falha de vez.
- **Testes** — `tests/test_*.py` e `tests/conftest.py`, com dublês de LLM e de banco (`pytest tests/ -q`).

## 3. Resultados (rodada de 15/11/2026)
**Recuperação** — fonte: `eval/results/2026-11-15/resumo.json`. Ficam fora da média as 6 perguntas com mais de 20 ids esperados (q09, q13, q17, q18, q20, q23).

| categoria | n | recall | precisão | recall nas 12 relações que vão ao LLM |
|---|---|---|---|---|
| 1 salto | 8 | 0,81 | 0,02 | 0,10 |
| 2 saltos | 7 | 0,92 | 0,03 | 0,14 |
| 3 saltos | 3 | 0,39 | 0,01 | 0,02 |
| agregação | 3 | 1,00 | 0,04 | 0,03 |
| média (21 perguntas) | 21 | 0,82 | 0,03 | 0,09 |

**Caso Lazarus (q01)** — fonte: `eval/results/2026-11-15/retrieval.csv`.
- O retriever devolveu 451 caminhos e 354 nós, com os 14 softwares esperados entre eles (recall 1,00).
- Nas 12 relações que o pipeline manda ao LLM havia só 1 dos 14 (recall 0,07), então o LLM não tem como listar as ferramentas.

**Extração, 17 textos** — fontes: `extraction.csv` e `extraction_meta.json` (44 triplas, 44 com evidência literal).

| relação | extraídas | gold | acertos | precisão | recall | F1 |
|---|---|---|---|---|---|---|
| ASSOCIATED_WITH | 13 | 13 | 13 | 1,00 | 1,00 | 1,00 |
| TARGETS → Country | 5 | 47 | 3 | 0,60 | 0,06 | 0,12 |
| TARGETS → Sector, 1ª rodada (só nome exato) | 22 | 23 | 3 | 0,14 | 0,13 | 0,13 |
| TARGETS → Sector, 2ª rodada (+ palavra-chave) | 22 | 23 | 4 | 0,18 | 0,17 | 0,18 |
| USES (→ Software) | 3 | 147 | 2 | 0,67 | 0,01 | 0,03 |
| total, 2ª rodada | 43 | 230 | 22 | 0,51 | 0,10 | 0,16 |

## 4. O que os números significam
- A recuperação encontra quase tudo (recall 0,82), mas traz centenas de nós, e o que chega ao LLM é um recorte que perde a maioria das respostas (0,09).
- O gargalo é a ordem das relações antes do corte das 12, não a busca no grafo; o ponto mais fraco são as perguntas de 3 saltos (recall 0,39).
- Na extração, o LLM acerta a origem dos grupos (ASSOCIATED_WITH 1,00), mas recupera pouco de alvos e ferramentas, porque os resumos citam pouco disso.
- O baixo F1 total (0,16) reflete o texto de entrada curto, não só o extrator.

## 5. O que não foi feito e por quê
- **Respostas com LLM: não medido.** A cota gratuita do Gemini é de 20 chamadas por dia, e as 15 chamadas de teste deram erro 429 (`answers.csv`).
- **Extração dos 13 textos restantes: não medido**, pela mesma cota.
- **Text-to-Cypher: não feito.** O tempo foi para a avaliação e a extração.

## 6. Achados no código existente (`docs/achados.md`)
1. `requirements.txt` está em UTF-16, e grep/diff não leem o arquivo.
2. `pytest` e `ruff` não constam no `requirements.txt`.
3. Os scripts antigos em `tests/` não são coletados pelo pytest.
4. `llm/client.py` não tenta de novo: um timeout ou 503 derruba o `answer()`.
5. A busca vetorial sempre devolve contexto, então a abstenção depende só do LLM.
6. Latência ponta a ponta: não medida nesta rodada. A recuperação leva 222 ms em média (`resumo.json`).
7. Só as 12 primeiras relações vão ao LLM, ordenadas pela similaridade da entidade de partida, e isso perde respostas (caso Lazarus).

## 7. Como rodar (ambiente `venv`; `set PYTHONPATH=src` antes)
`venv\Scripts\python.exe -m pytest tests/ -q` → `eval/fill_expected.py` → `eval/run_retrieval_eval.py` → `eval/run_eval.py --limit 5`
Extração: `-m cti_graphrag.extract.texts` → `.extractor` (ou `--cache-only`) → `.resolve` → `.load_extracted` → `eval/compare_graphs.py`

## 8. Commits desta branch
`7723e29` perguntas com gold_cypher · `c2ef8a4` textos de entrada · `2a3fdbb` pytest/ruff no venv · `4e91435` extrator com Pydantic e cache
`6ccd54d` gravação por texto e --cache-only · `c069c82` resolve e carga no cti_extracted · `f4a9d40` preencher expected_ids
`171695d` avaliação da recuperação · `fcf17ee` extração de 17 textos · `ac140db` registro da carga · `0d3ba2d` comparação dos grafos
`47b7066` avaliação com LLM, retry e cache · `9f4e48d` TARGETS separado · `1040f47` relatório de avaliação
`0854850` erro com 1000 caracteres · `c11868b` setores por palavra-chave · `a1c1a9f` recarga e nova comparação
