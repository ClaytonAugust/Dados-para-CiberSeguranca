import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "compare_graphs", Path(__file__).resolve().parents[1] / "eval" / "compare_graphs.py")
cg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cg)


def by_rel(rows):
    return {r["relation"]: r for r in rows}


def test_precisao_recall_f1_por_relacao_e_total():
    gold = {("G1", "USES", "S1"), ("G1", "USES", "S2"), ("G1", "TARGETS", "sector:energy"),
            ("G1", "ASSOCIATED_WITH", "country:RU")}
    extracted = {("G1", "USES", "S1"), ("G1", "TARGETS", "new:Sector:power_grid"),
                 ("G1", "ASSOCIATED_WITH", "country:RU")}
    r = by_rel(cg.compare(extracted, gold))
    assert r["USES"]["precision"] == 1.0 and r["USES"]["recall"] == 0.5
    assert r["USES"]["f1"] == round(2 * 1 * 0.5 / 1.5, 4)
    assert r["TARGETS"]["hits"] == 0 and r["TARGETS"]["f1"] == 0.0
    assert r["total"]["n_extracted"] == 3 and r["total"]["n_gold"] == 4 and r["total"]["hits"] == 2


def test_sem_arestas_extraidas_precisao_indefinida():
    r = by_rel(cg.compare(set(), {("G1", "USES", "S1")}))
    assert r["USES"]["precision"] is None and r["USES"]["recall"] == 0.0


class FakeResult:
    def __init__(self, rows):
        self.result_set = rows


class FakeGraph:
    def ro_query(self, cypher, params):
        assert params["rels"] == cg.RELATIONS and "$ids" in cypher
        return FakeResult([["G1", "USES", "S1", "Software"], ["G1", "USES", "S1", "Software"],
                           ["G1", "USES", "T1059", "Technique"]])


def test_edges_usa_parametros_distintos_e_so_pares_permitidos():
    assert cg.edges(FakeGraph(), {"G1"}) == {("G1", "USES", "S1")}
