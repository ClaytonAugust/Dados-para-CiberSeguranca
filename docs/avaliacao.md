# Avaliação — diário

## Fase B

- **B1 (15/11/2026)** — `eval/questions.csv` com 30 perguntas: 8 de 1 salto, 12 de 2, 4 de 3, 3 de agregação e 3 sem resposta. Cada `gold_cypher` usa só relações que existem no banco e ids reais, misturando ATT&CK (`G0032`, `S0367`, `T1190`) e `new:`. Rodei as 27 consultas com resposta e todas retornam ≥1 linha. `expected_answer` são os nomes devolvidos pela consulta; `expected_ids` fica vazio até a B2.

## Extração

- **T1 (15/11/2026)** — `src/cti_graphrag/extract/texts.py` gera `eval/extraction/texts.jsonl` com 30 textos (20 APT, 5 ransomware, 5 malware; semente 42). Cada texto tem só o summary, mais model e extortion no ransomware; tamanho em caracteres: mín. 249, mediana 341, máx. 938. `tests/test_extract_texts.py`: 6 testes passaram, rodados com o pytest do `.venv` porque o `venv` não tem pytest.
