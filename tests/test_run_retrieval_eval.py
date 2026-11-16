import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "run_retrieval_eval", Path(__file__).resolve().parents[1] / "eval" / "run_retrieval_eval.py")
rre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rre)


def rel(src, tgt):
    return {"source": {"id": src}, "target": {"id": tgt}}


class FakeRetriever:
    """Dublê: mesma estrutura de saída do HybridRetriever.retrieve."""

    def semantic_search(self, q):
        return ["chunk"]

    def find_entities(self, s):
        return [{"id": "G1"}]

    def expand_graph(self, e):
        return [rel("G1", f"S{i}") for i in range(1, 15)]  # 14 relações

    def retrieve(self, question):
        s = self.semantic_search(question)
        e = self.find_entities(s)
        return {"entities": e, "relationships": self.expand_graph(e)}


def row(qid, expected, category="group_software", hops="1"):
    return {"id": qid, "question": "?", "expected_ids": ";".join(expected),
            "category": category, "hops": hops}


def test_recall_precisao_e_top12():
    out = rre.evaluate([row("q1", ["S1", "S13", "X"])], FakeRetriever())[0]
    # todos os nós: G1 + S1..S14 = 15; acertos S1, S13
    assert out["n_nodes"] == 15 and out["hits"] == 2
    assert out["recall"] == 2 / 3 and out["precision"] == 2 / 15
    # top12: S13 fica de fora (13ª relação)
    assert out["hits_top12"] == 1 and out["n_nodes_top12"] == 13
    assert out["missing"] == "X"
    assert out["n_paths"] == 14
    assert {out["ms_vetorial"], out["ms_entidades"], out["ms_expansao"]} != {None}


def test_sem_resposta_e_lista_longa_ficam_fora_da_media():
    rows = [row("q1", ["S1"]), row("q2", [f"Z{i}" for i in range(21)]),
            row("q3", [], category="no_answer", hops="0")]
    results = rre.evaluate(rows, FakeRetriever())
    assert results[2]["recall"] is None and results[1]["lista_longa"]
    s = rre.summarize(results)
    assert s["media_principal"]["n"] == 1 and s["media_principal"]["recall"] == 1.0
    assert s["lista_longa"]["ids"] == ["q2"]
    assert s["sem_resposta_nos_recuperados"] == {"q3": 15}


def test_grupos():
    assert rre.group_of(row("a", [], hops="2")) == "2_saltos"
    assert rre.group_of(row("a", [], hops="1")) == "1_salto"
    assert rre.group_of(row("a", [], category="aggregation")) == "agregacao"
