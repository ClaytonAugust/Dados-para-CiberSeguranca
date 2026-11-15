# Avaliação — diário

## Fase B

- **B1 (15/11/2026)** — `eval/questions.csv` com 30 perguntas: 8 de 1 salto, 12 de 2, 4 de 3, 3 de agregação e 3 sem resposta. Cada `gold_cypher` usa só relações que existem no banco e ids reais, misturando ATT&CK (`G0032`, `S0367`, `T1190`) e `new:`. Rodei as 27 consultas com resposta e todas retornam ≥1 linha. `expected_answer` são os nomes devolvidos pela consulta; `expected_ids` fica vazio até a B2.

## Extração

- **T1 (15/11/2026)** — `src/cti_graphrag/extract/texts.py` gera `eval/extraction/texts.jsonl` com 30 textos (20 APT, 5 ransomware, 5 malware; semente 42). Cada texto tem só o summary, mais model e extortion no ransomware; tamanho em caracteres: mín. 249, mediana 341, máx. 938. `tests/test_extract_texts.py`: 6 testes passaram no `venv` (pytest e ruff instalados com ok; `ruff check` sem erros).
- **T2 (15/11/2026)** — `src/cti_graphrag/extract/extractor.py` (Pydantic, cache em `eval/extraction/cache/`, 3 tentativas com espera de 5 s e 15 s). Rodado em 3 textos: 8 triplas, 0 descartadas, 8/8 evidências literais. Na 1ª rodada, apt-c-60 falhou 3× (timeout/503) e saiu na 2ª. No Sandworm o head veio como "this group" (o texto não cita o nome) e apareceram tails genéricos ("wipers", "power grid").
