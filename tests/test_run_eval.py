import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "run_eval", Path(__file__).resolve().parents[1] / "eval" / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)


# exceções com os mesmos nomes das do LiteLLM
class Timeout(Exception):
    pass


class ServiceUnavailableError(Exception):
    pass


class RateLimitError(Exception):
    pass


def ok(q="?"):
    return {"answer": "Usa Mimikatz e Cobalt Strike [P1].", "n_paths": 3, "confidence": 0.8}


def test_retry_so_em_timeout_e_503_com_espera_crescente():
    esperas, falhas = [], [Timeout(), ServiceUnavailableError()]

    def call():
        if falhas:
            raise falhas.pop(0)
        return "ok"

    assert run_eval.with_retry(call, waits=[1, 2], sleep=esperas.append) == ("ok", 3)
    assert esperas == [1, 2]


def test_429_nao_repete():
    chamadas = []

    def call():
        chamadas.append(1)
        raise RateLimitError("quota")

    with pytest.raises(RateLimitError):
        run_eval.with_retry(call, waits=[1, 2], sleep=lambda s: None)
    assert len(chamadas) == 1


def test_falha_definitiva_vira_linha_erro_e_nao_vai_para_cache(tmp_path):
    def call():
        raise Timeout("lento")

    r = run_eval.run_one("graphrag", "q", call, "m", "c1", cache_dir=tmp_path, waits=[0, 0],
                         sleep=lambda s: None)
    assert r["status"] == "erro" and "Timeout" in r["error"]
    assert list(tmp_path.iterdir()) == []


def test_cache_por_sistema_pergunta_modelo_commit(tmp_path):
    chamadas = []

    def call():
        chamadas.append(1)
        return ok()

    kw = {"cache_dir": tmp_path, "sleep": lambda s: None}
    assert run_eval.run_one("graphrag", "q", call, "m", "c1", **kw)["cached"] is False
    assert run_eval.run_one("graphrag", "q", call, "m", "c1", **kw)["cached"] is True
    run_eval.run_one("llm_puro", "q", call, "m", "c1", **kw)   # outro sistema
    run_eval.run_one("graphrag", "q", call, "m2", "c1", **kw)  # outro modelo
    run_eval.run_one("graphrag", "q", call, "m", "c2", **kw)   # outro commit
    assert len(chamadas) == 4


def test_evaluate_continua_apos_erro_e_retoma_pelo_cache(tmp_path):
    def quebra(q):
        raise RateLimitError("quota")

    rows = [{"id": "q1", "question": "Quais ferramentas?", "category": "group_software",
             "hops": "1", "expected_answer": "Mimikatz; Cobalt Strike; Impacket"},
            {"id": "q2", "question": "Bolo?", "category": "no_answer", "hops": "0",
             "expected_answer": "Não há essa informação no grafo."}]
    calls = {"graphrag": ok, "llm_puro": quebra}
    out = run_eval.evaluate(rows, calls, "m", "c", cache_dir=tmp_path, sleep=lambda s: None)
    assert [r["status"] for r in out] == ["ok", "erro", "ok", "erro"]
    assert out[0]["name_recall"] == round(2 / 3, 4) and out[2]["name_recall"] is None

    out2 = run_eval.evaluate(rows, calls, "m", "c", cache_dir=tmp_path, sleep=lambda s: None)
    assert [r["cached"] for r in out2 if r["system"] == "graphrag"] == [True, True]


def test_abstencao():
    assert run_eval.abstained("Não encontrei isso no grafo.")
    assert not run_eval.abstained("O grupo usa Mimikatz [P1].")


def test_name_recall_de_agregacao_com_prefixo():
    assert run_eval.name_recall("2 grupos: APT28; APT29", "APT28 e APT29", "aggregation") == 1.0
