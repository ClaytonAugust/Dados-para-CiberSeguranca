import pytest

from cti_graphrag.extract.load_extracted import load


class FakeGraph:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def query(self, cypher, params):
        self.calls.append((cypher, params))


T = {"doc_id": "apt:x", "head": "this group", "head_id": "G1", "head_type": "Group",
     "head_resolved": True,
     "head_source": "entity_name", "relation": "USES", "tail": "NotPetya",
     "tail_type": "Software", "tail_id": "S1", "tail_resolved": True,
     "evidence": "uses NotPetya", "confidence": 0.9}
TEXTS = {"apt:x": {"entity_name": "Sandworm"}}


@pytest.mark.parametrize("nome", ["cti_gold", "cti_extracted_teste", "", "CTI_EXTRACTED"])
def test_so_escreve_em_cti_extracted(nome):
    g = FakeGraph(nome)
    with pytest.raises(RuntimeError):
        load(g, [T], TEXTS)
    assert g.calls == []


def test_usa_merge_e_parametros():
    g = FakeGraph("cti_extracted")
    assert load(g, [T], TEXTS) == {"carregadas": 1, "rejeitadas_head": 0}
    assert len(g.calls) == 3
    for cypher, params in g.calls:
        assert "MERGE" in cypher and "CREATE (" not in cypher
        assert "NotPetya" not in cypher and "G1" not in cypher  # valores só em parâmetros
    assert g.calls[0][1]["name"] == "Sandworm"  # head genérico vira entity_name
    edge_cypher, edge_params = g.calls[2]
    assert "(h:Group {id: $head_id})" in edge_cypher
    assert ":USES {doc_id: $doc_id}" in edge_cypher and "r.source = 'extracted'" in edge_cypher
    assert edge_params["evidence"] == "uses NotPetya"


def test_recusa_relacao_fora_da_lista():
    with pytest.raises(ValueError):
        load(FakeGraph("cti_extracted"), [{**T, "relation": "DROP"}], TEXTS)


def test_head_que_nao_e_group_e_rejeitado_e_contado():
    g = FakeGraph("cti_extracted")
    malware_head = {**T, "doc_id": "malware:emotet", "head": "Emotet", "head_id": "S0367",
                    "head_type": "Software", "head_source": "head"}
    assert load(g, [malware_head, T], TEXTS) == {"carregadas": 1, "rejeitadas_head": 1}
    assert len(g.calls) == 3  # só a tripla válida foi escrita
