from cti_graphrag.extract.resolve import (
    build_index,
    match_sector_keyword,
    norm,
    resolve_triples,
    slug,
    words,
)


class FakeResult:
    def __init__(self, rows):
        self.result_set = rows


class FakeGraph:
    """Dublê do grafo: responde às 4 consultas do build_index."""

    def ro_query(self, cypher):
        if ":Group" in cypher:
            return FakeResult([["G1", "Sandworm", ["Voodoo Bear"]], ["G2", "APT29", None]])
        if ":Software" in cypher:
            return FakeResult([["S1", "NotPetya", []], ["S2", "Mimikatz", ["NotPetya"]]])
        if ":Country" in cypher:
            return FakeResult([["country:RU", "Russia"], ["country:KZ", "Kazakhstan (suspected)"]])
        if ":Sector" in cypher:
            return FakeResult([["sector:energy", "Energy"], ["sector:government", "Government"],
                               ["sector:technology", "Technology"],
                               ["sector:it", "Information Technology"]])
        raise AssertionError(cypher)


TEXTS = {"apt:sandworm": {"entity_name": "Sandworm"},
         "malware:x": {"entity_name": "X"}}


def tripla(doc_id, head, tail, tail_type, relation="USES"):
    return {"doc_id": doc_id, "head": head, "relation": relation, "tail": tail,
            "tail_type": tail_type, "evidence": "e", "confidence": 0.9}


def test_norm_e_slug():
    assert norm("  Kazakhstan (suspected) ") == "kazakhstan"
    assert slug("Power Grid!") == "power_grid"


def test_alias_e_maiusculas():
    index = build_index(FakeGraph())
    out, unresolved = resolve_triples([tripla("apt:sandworm", "voodoo BEAR", "notpetya", "Software")],
                                      TEXTS, index)
    assert out[0]["head_id"] == "G1" and out[0]["tail_id"] == "S1"  # nome vence alias
    assert unresolved == []


def test_pais_e_setor():
    index = build_index(FakeGraph())
    out, _ = resolve_triples([
        tripla("apt:sandworm", "Sandworm", "russia", "Country", "ASSOCIATED_WITH"),
        tripla("apt:sandworm", "Sandworm", "Kazakhstan", "Country", "TARGETS"),
        tripla("apt:sandworm", "Sandworm", "energy", "Sector", "TARGETS"),
    ], TEXTS, index)
    assert [t["tail_id"] for t in out] == ["country:RU", "country:KZ", "sector:energy"]


def test_head_generico_usa_entity_name_so_em_texto_de_grupo():
    index = build_index(FakeGraph())
    out, unresolved = resolve_triples([
        tripla("apt:sandworm", "this group", "NotPetya", "Software"),
        tripla("malware:x", "this group", "NotPetya", "Software"),
    ], TEXTS, index)
    assert out[0]["head_id"] == "G1" and out[0]["head_source"] == "entity_name"
    assert out[1]["head_id"] == "new:Group:this_group" and not out[1]["head_resolved"]
    assert unresolved == [{"doc_id": "malware:x", "role": "head", "label": "Group",
                           "name": "this group", "new_id": "new:Group:this_group"}]


def test_nao_resolvido_vira_new():
    index = build_index(FakeGraph())
    out, unresolved = resolve_triples([tripla("apt:sandworm", "Sandworm", "power grid", "Sector",
                                              "TARGETS")], TEXTS, index)
    assert out[0]["tail_id"] == "new:Sector:power_grid"
    assert len(unresolved) == 1 and unresolved[0]["role"] == "tail"


def test_malware_como_head_vira_head_type_software():
    index = build_index(FakeGraph())
    out, unresolved = resolve_triples([tripla("malware:x", "Mimikatz", "Russia", "Country",
                                              "TARGETS")], TEXTS, index)
    assert out[0]["head_type"] == "Software" and out[0]["head_id"] == "S2"
    assert out[0]["head_resolved"] and unresolved == []


def test_grupo_resolvido_tem_head_type_group():
    index = build_index(FakeGraph())
    out, _ = resolve_triples([tripla("apt:sandworm", "Sandworm", "NotPetya", "Software")],
                             TEXTS, index)
    assert out[0]["head_type"] == "Group"


def test_words_singular_simples():
    assert words("Local Governments and Utilities") == {"local", "government", "and", "utility"}


def test_setor_por_palavra_chave_casa_e_guarda_tail_raw():
    index = build_index(FakeGraph())
    out, unresolved = resolve_triples([tripla("apt:sandworm", "Sandworm", "local governments",
                                              "Sector", "TARGETS")], TEXTS, index)
    t = out[0]
    assert t["tail_id"] == "sector:government" and t["tail_resolved"]
    assert t["tail"] == "Government" and t["tail_raw"] == "local governments"
    assert t["tail_match"] == "palavra_chave" and unresolved == []


def test_setor_sem_palavra_chave_continua_nao_resolvido():
    index = build_index(FakeGraph())
    out, unresolved = resolve_triples([tripla("apt:sandworm", "Sandworm", "banks", "Sector",
                                              "TARGETS")], TEXTS, index)
    assert out[0]["tail_id"] == "new:Sector:banks"
    assert not out[0]["tail_resolved"] and out[0]["tail_raw"] == "banks"
    assert unresolved[0]["name"] == "banks"


def test_setor_ambiguo_continua_nao_resolvido():
    index = build_index(FakeGraph())
    # "information technology firms" contém as palavras de Technology e de Information Technology
    assert match_sector_keyword(index, "information technology firms") is None
    assert match_sector_keyword(index, "technology firms") == ("sector:technology", "Technology")


def test_nome_exato_tem_prioridade_e_marca_tail_match_nome():
    index = build_index(FakeGraph())
    out, _ = resolve_triples([tripla("apt:sandworm", "Sandworm", "Energy", "Sector", "TARGETS")],
                             TEXTS, index)
    assert out[0]["tail_match"] == "nome" and out[0]["tail_raw"] == "Energy"


def test_palavra_chave_so_vale_para_sector():
    index = build_index(FakeGraph())
    out, _ = resolve_triples([tripla("apt:sandworm", "Sandworm", "government tool", "Software")],
                             TEXTS, index)
    assert not out[0]["tail_resolved"]
