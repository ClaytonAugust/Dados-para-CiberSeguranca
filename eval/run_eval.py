"""Avaliação ponta a ponta, COM LLM: três sistemas na mesma pergunta.

  llm_puro     LLM só com a pergunta, sem contexto
  rag_vetorial busca vetorial (top 5 chunks) + gerar_resposta (mesmo prompt
               do GraphRAG, trechos rotulados [P1]..[P5])
  graphrag     GraphRAGPipeline(graph).answer(question)

Robustez, sem alterar llm/client.py:
  - retry: 3 tentativas com espera crescente, só para Timeout e 503
    (ServiceUnavailableError); outro erro (ex.: 429 de cota) falha direto;
  - cache em disco por (sistema, pergunta, modelo, commit do código em src/);
    rodar de novo pula o que já está no cache;
  - pausa entre chamadas que não vieram do cache;
  - falha definitiva vira linha status="erro" no CSV e não para a execução.

Métricas automáticas por linha (simples e explicáveis):
  - name_recall: fração dos nomes de expected_answer que aparecem no texto
    da resposta (sem diferenciar maiúsculas);
  - abstained: a resposta contém uma frase de abstenção (ABSTAIN_MARKERS).

Saída: eval/results/<data>/answers.csv
Uso: python eval/run_eval.py --limit 5
"""

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

QUESTIONS = Path("eval/questions.csv")
CACHE_DIR = Path("eval/cache/llm")
SYSTEMS = ["llm_puro", "rag_vetorial", "graphrag"]
RETRYABLE = {"Timeout", "ServiceUnavailableError"}
WAITS = [10, 30]  # espera antes da 2ª e da 3ª tentativa
PAUSE = 3
ERROR_CHARS = 1000  # suficiente para ler qual cota/limite estourou

ABSTAIN_MARKERS = [
    "não encontrei", "não foi possível validar", "não há informaç", "não há registro",
    "não foram encontrad", "não constam", "insuficiente", "não sei",
]

LLM_PURO_PROMPT = ("Você é um analista de inteligência de ameaças. Responda em português, "
                   "de forma objetiva. Se não souber, diga que não sabe.")


# ---------------------------------------------------------------- sistemas

def ask_llm_puro(question, model):
    from litellm import completion

    resp = completion(model=model, timeout=120, messages=[
        {"role": "system", "content": LLM_PURO_PROMPT},
        {"role": "user", "content": question},
    ])
    return {"answer": resp.choices[0].message.content or "", "n_paths": 0, "confidence": None}


def ask_rag_vetorial(question, retriever):
    from cti_graphrag.llm.client import gerar_resposta

    chunks = retriever.semantic_search(question, 5)
    context = "\n".join(f"\n[P{i}]\nTrecho: {str(c['text'])[:1500]}"
                        for i, c in enumerate(chunks, start=1))
    sims = [c["similarity"] for c in chunks if c.get("similarity") is not None]
    return {"answer": gerar_resposta(question, context), "n_paths": len(chunks),
            "confidence": round(sum(sims) / len(sims), 4) if sims else None}


def ask_graphrag(question, pipeline):
    a = pipeline.answer(question)
    return {"answer": a.answer, "n_paths": len(a.paths), "confidence": a.confidence}


# ---------------------------------------------------------------- robustez

def code_commit():
    """Último commit que mexeu em src/ (o código avaliado)."""
    out = subprocess.run(["git", "log", "-1", "--format=%h", "--", "src"],
                         capture_output=True, text=True, check=False)
    return out.stdout.strip() or "sem-git"


def cache_path(system, question, model, commit, cache_dir=CACHE_DIR):
    key = hashlib.sha256(f"{system}\n{question}\n{model}\n{commit}".encode()).hexdigest()[:24]
    return Path(cache_dir) / f"{system}_{key}.json"


def with_retry(fn, waits=WAITS, sleep=time.sleep):
    """Chama fn(); repete só em Timeout/503. Devolve (resultado, tentativas)."""
    for attempt in range(1, len(waits) + 2):
        try:
            return fn(), attempt
        except Exception as e:  # o tipo decide se repete; senão relança
            if type(e).__name__ not in RETRYABLE or attempt > len(waits):
                raise
            print(f"   tentativa {attempt} falhou ({type(e).__name__}); espera {waits[attempt - 1]} s",
                  flush=True)
            sleep(waits[attempt - 1])
    raise AssertionError("inalcançável")


def run_one(system, question, call, model, commit, cache_dir=CACHE_DIR, waits=WAITS,
            sleep=time.sleep):
    """Devolve dict com answer, n_paths, confidence, latency_ms, status, cached, attempts."""
    path = cache_path(system, question, model, commit, cache_dir)
    if path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "cached": True}
    start = time.perf_counter()
    try:
        result, attempts = with_retry(call, waits=waits, sleep=sleep)
    except Exception as e:  # noqa: BLE001 — falha definitiva vira linha "erro"
        return {"answer": "", "n_paths": None, "confidence": None,
                "latency_ms": int((time.perf_counter() - start) * 1000),
                "status": "erro", "error": f"{type(e).__name__}: {e}"[:ERROR_CHARS],
                "cached": False, "attempts": None}
    record = {**result, "latency_ms": int((time.perf_counter() - start) * 1000),
              "status": "ok", "error": "", "attempts": attempts}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return {**record, "cached": False}


# ---------------------------------------------------------------- métricas

def name_recall(expected_answer, answer, category):
    if category == "no_answer" or not expected_answer.strip():
        return None
    names = [n.strip() for n in expected_answer.split(":")[-1].split(";") if n.strip()]
    text = answer.lower()
    return round(sum(n.lower() in text for n in names) / len(names), 4) if names else None


def abstained(answer):
    text = answer.lower()
    return any(m in text for m in ABSTAIN_MARKERS)


# ---------------------------------------------------------------- execução

def evaluate(rows, calls, model, commit, cache_dir=CACHE_DIR, pause=PAUSE, sleep=time.sleep,
             waits=WAITS):
    """calls: {sistema: função(question) -> dict}."""
    out = []
    for i, row in enumerate(rows, start=1):
        for system, call in calls.items():
            r = run_one(system, row["question"], lambda c=call, q=row["question"]: c(q),
                        model, commit, cache_dir=cache_dir, waits=waits, sleep=sleep)
            out.append({
                "id": row["id"], "system": system, "category": row["category"],
                "hops": row["hops"], "status": r["status"], "cached": r["cached"],
                "attempts": r.get("attempts"), "latency_ms": r["latency_ms"],
                "n_paths": r["n_paths"], "confidence": r["confidence"],
                "name_recall": name_recall(row["expected_answer"], r["answer"], row["category"]),
                "abstained": abstained(r["answer"]) if r["status"] == "ok" else None,
                "answer": r["answer"].replace("\n", " "), "error": r.get("error", ""),
                "model": model, "commit": commit,
            })
            print(f"{i}/{len(rows)} {row['id']} {system} {r['status']} "
                  f"cache={r['cached']} {r['latency_ms']} ms", flush=True)
            if r["status"] == "erro":
                print(f"   {r['error']}", flush=True)
            if not r["cached"]:
                sleep(pause)
    return out


def main():
    sys.path.insert(0, "src")
    from dotenv import load_dotenv
    from falkordb import FalkorDB

    from cti_graphrag.pipeline.answer import GraphRAGPipeline

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    load_dotenv(".env")
    model = os.getenv("LLM_MODEL")
    if not model or not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("LLM_MODEL e GEMINI_API_KEY precisam estar no .env")
    graph = FalkorDB(host=os.getenv("FALKORDB_HOST"),
                     port=int(os.getenv("FALKORDB_PORT"))).select_graph(os.getenv("GRAPH_NAME"))
    pipeline = GraphRAGPipeline(graph)
    retriever = pipeline.retriever  # mesmo modelo de embeddings, carregado uma vez
    calls = {
        "llm_puro": lambda q: ask_llm_puro(q, model),
        "rag_vetorial": lambda q: ask_rag_vetorial(q, retriever),
        "graphrag": lambda q: ask_graphrag(q, pipeline),
    }

    rows = list(csv.DictReader(QUESTIONS.open(encoding="utf-8")))[: args.limit]
    results = evaluate(rows, calls, model, code_commit())

    out_dir = Path("eval/results") / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "answers.csv"
    with out_file.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    erros = sum(r["status"] == "erro" for r in results)
    print(f"gravado em {out_file}: {len(results)} linhas, {erros} com erro")


if __name__ == "__main__":
    main()
