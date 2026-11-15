import json

import pytest

from cti_graphrag.extract.extractor import (
    CacheMiss,
    extract,
    extract_cache_only,
    parse_triples,
    run,
)


def resposta(*triples):
    return json.dumps({"triples": list(triples)})


OK = {"head": "APT1", "relation": "USES", "tail": "PoisonIvy", "tail_type": "Software",
      "evidence": "uses PoisonIvy", "confidence": 0.9}


def test_tripla_valida():
    triples, dropped = parse_triples(resposta(OK))
    assert len(triples) == 1 and dropped == 0
    assert triples[0].tail == "PoisonIvy"


@pytest.mark.parametrize("ruim", [
    {**OK, "relation": "BELONGS_TO"},                       # relação não permitida
    {**OK, "relation": "USES", "tail_type": "Country"},     # USES só aceita Software
    {**OK, "relation": "ASSOCIATED_WITH", "tail_type": "Sector"},
    {**OK, "confidence": 1.5},
    {k: v for k, v in OK.items() if k != "evidence"},
])
def test_tripla_invalida_e_descartada(ruim):
    triples, dropped = parse_triples(resposta(OK, ruim))
    assert len(triples) == 1 and dropped == 1


def test_targets_aceita_sector_e_country():
    a = {**OK, "relation": "TARGETS", "tail": "Energy", "tail_type": "Sector"}
    b = {**OK, "relation": "TARGETS", "tail": "Ukraine", "tail_type": "Country"}
    assert parse_triples(resposta(a, b))[1] == 0


def test_json_em_bloco_markdown():
    assert len(parse_triples("```json\n" + resposta(OK) + "\n```")[0]) == 1


def test_cache_evita_segunda_chamada(tmp_path):
    chamadas = []

    def llm(prompt, model):
        chamadas.append(prompt)
        return resposta(OK)

    r1 = extract("texto", "m", llm=llm, cache_dir=tmp_path, sleep=lambda s: None)
    r2 = extract("texto", "m", llm=llm, cache_dir=tmp_path, sleep=lambda s: None)
    assert len(chamadas) == 1
    assert r1[2] is False and r2[2] is True
    assert r2[0][0].tail == "PoisonIvy"


def test_retry_com_espera_crescente(tmp_path):
    esperas, tentativas = [], []

    def llm(prompt, model):
        tentativas.append(1)
        if len(tentativas) < 3:
            raise TimeoutError("timeout")
        return resposta(OK)

    triples, _, _ = extract("t", "m", llm=llm, cache_dir=tmp_path, waits=[1, 2, 4],
                            sleep=esperas.append)
    assert len(tentativas) == 3 and esperas == [1, 2]
    assert len(triples) == 1


def test_tres_falhas_levantam_erro_e_nao_gravam_cache(tmp_path):
    def llm(prompt, model):
        return "isto não é json"

    with pytest.raises(RuntimeError):
        extract("t", "m", llm=llm, cache_dir=tmp_path, sleep=lambda s: None)
    assert list(tmp_path.iterdir()) == []


def test_run_grava_cada_texto_ao_chegar_e_conta_erros(tmp_path, capsys):
    out = tmp_path / "raw.jsonl"
    linhas_vistas = []

    def fake_extract(text, model):
        linhas_vistas.append(len(out.read_text(encoding="utf-8").splitlines()))
        if text == "falha":
            raise RuntimeError("3 tentativas falharam")
        if text == "sem":
            raise CacheMiss()
        return parse_triples(resposta(OK))[0], 0, True

    rows = [{"doc_id": "a", "text": "uses PoisonIvy"}, {"doc_id": "b", "text": "falha"},
            {"doc_id": "c", "text": "sem"}, {"doc_id": "d", "text": "x"}]
    counts = run(rows, "m", out_file=out, extract_fn=fake_extract, sleep=lambda s: None)

    assert counts == {"ok": 2, "erro": 1, "sem_cache": 1}
    assert linhas_vistas == [0, 1, 1, 1]  # a linha de "a" já estava no disco antes de "b"
    saida = capsys.readouterr().out
    assert "1/4 a ok" in saida and "2/4 b erro" in saida and "3/4 c sem_cache" in saida


def test_cache_only_nao_chama_llm(tmp_path):
    with pytest.raises(CacheMiss):
        extract_cache_only("novo", "m", cache_dir=tmp_path)
    extract("novo", "m", llm=lambda p, m: resposta(OK), cache_dir=tmp_path)
    assert extract_cache_only("novo", "m", cache_dir=tmp_path)[2] is True
