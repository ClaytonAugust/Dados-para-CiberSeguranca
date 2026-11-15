# Avaliação — diário

## Fase B

- **B1 (15/11/2026)** — `eval/questions.csv` com 30 perguntas: 8 de 1 salto, 12 de 2, 4 de 3, 3 de agregação e 3 sem resposta. Cada `gold_cypher` usa só relações que existem no banco e ids reais, misturando ATT&CK (`G0032`, `S0367`, `T1190`) e `new:`. Rodei as 27 consultas com resposta e todas retornam ≥1 linha. `expected_answer` são os nomes devolvidos pela consulta; `expected_ids` fica vazio até a B2.
