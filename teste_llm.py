
from src.cti_graphrag.llm.client import gerar_resposta

contexto = """
[P1]
Grupo: Andariel.
Relacionamento: USES.
Software: Gh0st RAT.
Evidência: O grupo Andariel utiliza o software Gh0st RAT.

[P2]
Software: Gh0st RAT.
Descrição: Ferramenta de acesso remoto.
"""

pergunta = "Qual ferramenta é utilizada pelo grupo Andariel?"

resposta = gerar_resposta(pergunta, contexto)

print("\n=== RESPOSTA DO LLM ===")
print(resposta)
