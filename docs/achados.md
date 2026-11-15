# Achados no código existente

| # | Arquivo / linha | Problema | Sugestão |
|---|---|---|---|
| 1 | `requirements.txt` | Codificado em UTF-16 LE (gerado por `pip freeze >` no PowerShell). Ferramentas como grep/diff não leem. | Regravar em UTF-8. |
| 2 | `requirements.txt` | `pytest` e `ruff` não constam no arquivo e não estão no `venv` oficial (só no `.venv` antigo). | Adicionar (com ok do grupo). |
| 3 | `tests/*.py` | São scripts manuais; `pytest --collect-only tests` → "no tests collected". | Novos testes em `tests/test_*.py` com funções `test_`. |
| 4 | `src/cti_graphrag/llm/client.py:46,56-58` | Sem retry: um 503 ou timeout (120 s) do Gemini se propaga e `GraphRAGPipeline.answer()` falha sem devolver `Answer`. Observado em 15/11/2026: 2 de 3 perguntas falharam. | Retry com backoff (`num_retries` do LiteLLM) ou devolver `Answer` de erro. |
| 5 | `src/cti_graphrag/pipeline/answer.py:270` | A busca vetorial sempre devolve os k chunks mais próximos, então `context_parts` nunca fica vazio e o "Não encontrei isso no grafo." quase não acontece: a abstenção depende só do LLM. Observado: "receita de bolo de cenoura" chegou ao LLM. | Limiar mínimo de `similarity` antes de montar o contexto. |
| 6 | `src/cti_graphrag/pipeline/answer.py` | Latência de ~100 s em 1 pergunta (Lazarus: `latency_ms=99837`, 15/11/2026). Etapas ainda não medidas separadamente. | Medir por etapa (Parte 3 da Fase B). |
