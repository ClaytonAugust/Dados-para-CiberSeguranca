
import os

from dotenv import load_dotenv
from litellm import completion

from cti_graphrag.llm.prompts import SYSTEM_PROMPT

load_dotenv()


def gerar_resposta(pergunta: str, contexto: str) -> str:
    """
    Gera uma resposta fundamentada nas evidências do grafo.
    """

    if not contexto or not contexto.strip():
        return "Não encontrei evidências suficientes no grafo."

    modelo = os.getenv("LLM_MODEL")

    if not modelo:
        raise ValueError("LLM_MODEL não configurado no .env")

    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY não configurada no .env")

    try:
        resposta = completion(
            model=modelo,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": (
                        f"PERGUNTA:\n{pergunta}\n\n"
                        f"EVIDÊNCIAS RECUPERADAS:\n{contexto}"
                    )
                }
            ],
            reasoning_effort="low",
            max_tokens=512,
            timeout=120
        )

        conteudo = resposta.choices[0].message.content

        if not conteudo:
            return "O modelo não retornou uma resposta."

        return conteudo

    except Exception as erro:
        print(f"Erro ao consultar o LLM: {erro}")
        raise
