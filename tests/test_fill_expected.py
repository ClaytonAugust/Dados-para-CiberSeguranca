import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "fill_expected", Path(__file__).resolve().parents[1] / "eval" / "fill_expected.py")
fill_expected = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fill_expected)


class FakeResult:
    def __init__(self, header, rows):
        self.header, self.result_set = header, rows


class FakeGraph:
    def __init__(self):
        self.queries = []

    def ro_query(self, cypher):
        self.queries.append(cypher)
        if "vazio" in cypher:
            return FakeResult([[1, "id"], [1, "name"]], [])
        return FakeResult([[1, "id"], [1, "name"]], [["G2", "b"], ["G1", "a"], ["G2", "b"]])


def test_preenche_ids_ordenados_sem_repeticao_e_deixa_vazias():
    rows = [{"id": "q1", "gold_cypher": "MATCH x"}, {"id": "q2", "gold_cypher": "MATCH vazio"},
            {"id": "q3", "gold_cypher": ""}]
    g = FakeGraph()
    fill_expected.fill(rows, g)
    assert [r["expected_ids"] for r in rows] == ["G1;G2", "", ""]
    assert len(g.queries) == 2  # sem gold_cypher não consulta o banco
