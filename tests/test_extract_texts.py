import json
from pathlib import Path

import pytest

from cti_graphrag.extract.texts import OUT_FILE, build_text

LIST_FIELDS = ["tools", "attack_techniques", "target_sectors", "target_regions",
               "aliases", "malware", "used_by", "platforms"]


def fake_item():
    # cada campo de lista tem um valor sentinela que não pode aparecer no texto
    item = {f: [f"SENTINELA_{f.upper()}"] for f in LIST_FIELDS}
    item.update(summary="Resumo do grupo.", model="RaaS", extortion="Dupla extorsão")
    return item


@pytest.mark.parametrize("kind", ["apt", "ransomware", "malware"])
def test_texto_nao_contem_campos_de_lista(kind):
    text = build_text(fake_item(), kind)
    assert "Resumo do grupo." in text
    assert "SENTINELA" not in text


def test_ransomware_inclui_model_e_extortion():
    text = build_text(fake_item(), "ransomware")
    assert "Modelo: RaaS" in text and "Extorsão: Dupla extorsão" in text


def test_apt_e_malware_ignoram_model_e_extortion():
    for kind in ["apt", "malware"]:
        assert build_text(fake_item(), kind) == "Resumo do grupo."


@pytest.mark.skipif(not Path(OUT_FILE).exists(), reason="texts.jsonl ainda não gerado")
def test_arquivo_gerado_tem_30_registros_sem_campos_de_lista():
    rows = [json.loads(l) for l in Path(OUT_FILE).read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 30
    assert [r["doc_id"].split(":")[0] for r in rows].count("apt") == 20
    for r in rows:
        assert set(r) == {"doc_id", "entity_name", "text"}
        assert r["text"].strip()
        for f in LIST_FIELDS:
            assert f"{f}:" not in r["text"].lower()
