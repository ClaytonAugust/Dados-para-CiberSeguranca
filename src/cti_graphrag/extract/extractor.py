"""Extrai triplas (head, relation, tail) dos textos com um LLM.

O LLM recebe só o texto. A resposta é JSON validado por Pydantic.
Relações permitidas:
  ASSOCIATED_WITH  Group -> Country
  TARGETS          Group -> Sector ou Country
  USES             Group -> Software
Cada chamada vai para um cache em disco; falhas têm 3 tentativas com
espera crescente. Triplas inválidas são descartadas e contadas.

Uso: python -m cti_graphrag.extract.extractor --limit 3
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

TEXTS_FILE = Path("eval/extraction/texts.jsonl")
OUT_FILE = Path("eval/extraction/triples_raw.jsonl")  # resolve.py gera triples.jsonl
CACHE_DIR = Path("eval/extraction/cache")
WAITS = [5, 15, 45]  # segundos antes da 2ª, 3ª tentativa (a 3ª espera não é usada)
PAUSE = 2  # pausa entre chamadas que não vieram do cache

ALLOWED_TAILS = {
    "ASSOCIATED_WITH": {"Country"},
    "TARGETS": {"Sector", "Country"},
    "USES": {"Software"},
}

PROMPT = """Você extrai relações de inteligência de ameaças de um texto.
O sujeito (head) é sempre o grupo ou ator descrito no texto.
Relações permitidas:
- ASSOCIATED_WITH: grupo -> país de origem ou patrocínio (tail_type "Country")
- TARGETS: grupo -> setor ("Sector") ou país ("Country") que ele ataca
- USES: grupo -> software, malware ou ferramenta que ele usa ("Software")
Regras:
- Use só o que está escrito no texto. Não use conhecimento externo.
- "evidence" é um trecho copiado literalmente do texto que sustenta a relação.
- "confidence" é um número de 0 a 1.
- Se não houver relação, devolva {"triples": []}.
Responda só com JSON no formato:
{"triples": [{"head": "...", "relation": "USES", "tail": "...",
"tail_type": "Software", "evidence": "...", "confidence": 0.9}]}

TEXTO:
"""


class Triple(BaseModel):
    head: str = Field(min_length=1)
    relation: Literal["ASSOCIATED_WITH", "TARGETS", "USES"]
    tail: str = Field(min_length=1)
    tail_type: Literal["Country", "Sector", "Software"]
    evidence: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def check_tail_type(self):
        if self.tail_type not in ALLOWED_TAILS[self.relation]:
            raise ValueError(f"{self.relation} não aceita {self.tail_type}")
        return self


def parse_triples(raw):
    """Converte a resposta do LLM em (triplas válidas, nº descartadas).

    JSON quebrado levanta exceção (conta como falha e gera nova tentativa);
    uma tripla inválida só é descartada.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`").removeprefix("json").strip()
    items = json.loads(raw)["triples"]
    valid, dropped = [], 0
    for item in items:
        try:
            valid.append(Triple(**item))
        except (ValidationError, TypeError):
            dropped += 1
    return valid, dropped


def call_llm(prompt, model):
    from litellm import completion

    resp = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},  # gemini-3.8-flash não aceita temperature
        timeout=120,
    )
    return resp.choices[0].message.content or ""


def cache_key(model, prompt):
    return hashlib.sha256(f"{model}\n{prompt}".encode()).hexdigest()[:24]


def extract(text, model, llm=call_llm, cache_dir=CACHE_DIR, waits=WAITS, sleep=time.sleep):
    """Devolve (triplas, descartadas, from_cache). Levanta exceção após 3 falhas."""
    prompt = PROMPT + text
    path = Path(cache_dir) / f"{cache_key(model, prompt)}.json"
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))["raw"]
        return (*parse_triples(raw), True)

    last_error = None
    for attempt in range(3):
        try:
            raw = llm(prompt, model)
            triples, dropped = parse_triples(raw)  # valida antes de gravar no cache
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": model, "raw": raw}, ensure_ascii=False),
                            encoding="utf-8")
            return triples, dropped, False
        except Exception as e:  # noqa: BLE001 — timeout, 503 e JSON inválido têm o mesmo tratamento
            last_error = e
            print(f"  tentativa {attempt + 1} falhou: {type(e).__name__}")
            if attempt < 2:
                sleep(waits[attempt])
    raise RuntimeError(f"3 tentativas falharam: {last_error}")


class CacheMiss(Exception):
    pass


def extract_cache_only(text, model, cache_dir=CACHE_DIR):
    """Como extract, mas só lê o cache; sem cache levanta CacheMiss."""
    def no_llm(prompt, model):
        raise CacheMiss()
    path = Path(cache_dir) / f"{cache_key(model, PROMPT + text)}.json"
    if not path.exists():
        raise CacheMiss()
    return extract(text, model, llm=no_llm, cache_dir=cache_dir)


def run(rows, model, out_file=OUT_FILE, extract_fn=extract, pause=PAUSE, sleep=time.sleep):
    """Processa os textos gravando cada resultado assim que chega (append + flush).

    O arquivo é recriado no início; textos já no cache saem sem chamar o LLM.
    Devolve {"ok": n, "erro": n, "sem_cache": n}.
    """
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("", encoding="utf-8")
    counts = {"ok": 0, "erro": 0, "sem_cache": 0}
    for i, row in enumerate(rows, start=1):
        cached = True
        try:
            triples, dropped, cached = extract_fn(row["text"], model)
            status = "ok"
        except CacheMiss:
            triples, dropped, status = [], 0, "sem_cache"
        except RuntimeError as e:
            triples, dropped, cached, status = [], 0, False, "erro"
            print(f"   {e}"[:1000], flush=True)  # 1000: dá para ler qual limite estourou
        counts[status] += 1
        with out_file.open("a", encoding="utf-8") as out:
            for t in triples:
                out.write(json.dumps({
                    "doc_id": row["doc_id"],
                    **t.model_dump(),
                    "evidence_in_text": t.evidence in row["text"],
                }, ensure_ascii=False) + "\n")
            out.flush()
        print(f"{i}/{len(rows)} {row['doc_id']} {status} "
              f"(triplas={len(triples)} descartadas={dropped} cache={cached})", flush=True)
        if not cached:
            sleep(pause)
    return counts


def main():
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cache-only", action="store_true",
                        help="não chama o LLM; usa só o que já está no cache")
    args = parser.parse_args()

    load_dotenv(".env")
    model = os.getenv("LLM_MODEL")
    if not model or (not args.cache_only and not os.getenv("GEMINI_API_KEY")):
        raise SystemExit("LLM_MODEL e GEMINI_API_KEY precisam estar no .env")

    rows = [json.loads(line) for line in TEXTS_FILE.read_text(encoding="utf-8").splitlines()]
    rows = rows[: args.limit]
    counts = run(rows, model, extract_fn=extract_cache_only if args.cache_only else extract)
    print(f"resumo: {counts}", flush=True)


if __name__ == "__main__":
    main()
