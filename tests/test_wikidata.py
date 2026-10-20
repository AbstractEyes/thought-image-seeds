"""The Wikidata importer on a tiny fixture shaped like the kept SPARQL answers (no network)."""
import json
import os

from thought_seeds import core
from thought_seeds.sources import wikidata

E = "http://www.wikidata.org/entity/"


def _b(**kw):
    return {k: {"type": "uri" if str(v).startswith("http") else "literal", "value": str(v)} for k, v in kw.items()}


def _write(raw):
    d = os.path.join(raw, "wikidata")
    os.makedirs(d)
    sel = [{"id": "Q1", "kind": "painting", "n": 7}, {"id": "Q2", "kind": "painting", "n": 3}, {"id": "Q3", "kind": "sculpture", "n": 2},
           {"id": "Q4", "kind": "painting", "n": 2}]
    dep = [  # Q1: a woman with long hair and a hat, seated, two brown dogs, a forest at night
        _b(item=E + "Q1", st="s1", d=E + "Q467", dLabel="woman", human="false"),
        _b(item=E + "Q1", st="s2", d=E + "Q144", dLabel="dog", qty="2", colLabel="brown", human="false"),
        _b(item=E + "Q1", st="s3", d=E + "Q80151", dLabel="hat", human="false"),
        _b(item=E + "Q1", st="s4", d=E + "Q1144593", dLabel="sitting", human="false"),
        _b(item=E + "Q1", st="s5", d=E + "Q4421", dLabel="forest", human="false"),
        _b(item=E + "Q1", st="s6", d=E + "Q575", dLabel="night", human="false"),
        _b(item=E + "Q1", st="s7", d=E + "Q14130", dLabel="waist-length hair", human="false"),
        # Q2: a named boy (a human individual born 1600, painted 1610), a goddess (a name: dropped), a lion
        _b(item=E + "Q2", st="t1", d=E + "Q33923", dLabel="Saint Peter", human="true", sex=E + "Q6581097",
           birth="1600-01-01T00:00:00Z"),
        _b(item=E + "Q2", st="t2", d=E + "Q47652", dLabel="Venus", human="false", sex=E + "Q6581072"),
        _b(item=E + "Q2", st="t3", d=E + "Q140", dLabel="lion", human="false"),
        # Q3: a sexual act depicted: no seed
        _b(item=E + "Q3", st="u1", d=E + "Q467", dLabel="woman", human="false"),
        _b(item=E + "Q3", st="u2", d=E + "Q24826", dLabel="sexual intercourse", human="false"),
        # Q4: a posthumous portrait (the sitter born 1500, dead 1550, painted 1610): a man, no age
        _b(item=E + "Q4", st="v1", d=E + "Q77", dLabel="Old King", human="true", sex=E + "Q6581097",
           birth="1500-01-01T00:00:00Z"),
        _b(item=E + "Q4", st="v2", d=E + "Q726", dLabel="horse", human="false"),
    ]
    deaths = [_b(d=E + "Q77", dd="1550-01-01T00:00:00Z")]
    props = [_b(item=E + "Q1", genres="portrait", moves="Baroque", mats="oil paint|canvas", inception="1650-01-01T00:00:00Z",
                precision="9"),
             _b(item=E + "Q2", genres="religious art", moves="", mats="", inception="1610-01-01T00:00:00Z", precision="9"),
             _b(item=E + "Q3", genres="", moves="", mats="marble", inception="1700-01-01T00:00:00Z", precision="9"),
             _b(item=E + "Q4", genres="portrait", moves="", mats="oil paint", inception="1610-01-01T00:00:00Z", precision="9")]
    types = [_b(d=E + "Q467", root=E + "Q5"), _b(d=E + "Q144", root=E + "Q729"), _b(d=E + "Q80151", root=E + "Q11460"),
             _b(d=E + "Q80151", root=E + "Q16686448"), _b(d=E + "Q4421", root=E + "Q618123"), _b(d=E + "Q140", root=E + "Q729"),
             _b(d=E + "Q14130", root=E + "Q16686448"), _b(d=E + "Q726", root=E + "Q729")]
    with open(os.path.join(d, "selection.json"), "w") as fh:
        json.dump(sel, fh)
    for name, rows in (("depicts_0000.json", dep), ("props_0000.json", props), ("types_0000.json", types),
                       ("deaths_0000.json", deaths)):
        with open(os.path.join(d, name), "w") as fh:
            json.dump({"head": {"vars": []}, "results": {"bindings": rows}}, fh)


def test_wikidata_specs(tmp_path):
    raw = str(tmp_path)
    _write(raw)
    out = {s["seed_id"]: s for s in wikidata.seeds(raw)}
    assert set(out) == {"wikidata:Q1", "wikidata:Q2", "wikidata:Q4"}        # the sexual act left the third work out
    assert out["wikidata:Q4"]["spec"]["person"] == {"count": "1", "gender": "man"}       # posthumous: no age from the birth year
    assert "King" not in out["wikidata:Q4"]["hint"]
    a = out["wikidata:Q1"]
    assert a["domain"] == "painting" and a["genre"] == "portrait" and a["held"] is False
    assert a["spec"] == {"person": {"gender": "woman"}, "look": {"hair": "long"}, "wear": {"accessory": "hat"},
                         "body": {"pose": "sitting"}, "thing": {"name": "dog", "count": "2", "colour": "brown"},
                         "scene": {"setting": "forest", "time": "night"},
                         "form": {"medium": "oil painting", "style": "baroque", "period": "baroque"}}
    assert core.check_spec(a["spec"]) == []
    assert "two brown dogs" in a["hint"] and a["hint"].startswith("A painting made with oil paint, canvas. It is dated 1650.")
    assert a["source"] == {"dataset": "wikidata", "id": "Q1", "license": "CC0 1.0", "url": "https://www.wikidata.org/wiki/Q1"}
    b = out["wikidata:Q2"]
    assert b["spec"] == {"person": {"count": "1", "gender": "boy", "age": "child"}, "thing": {"name": "lion"},
                         "form": {"period": "baroque"}}
    assert "Peter" not in b["hint"] and "Venus" not in b["hint"] and "a boy and a lion" in b["hint"]
    assert b["genre"] == "religious art"


def test_a_date_before_the_era_and_a_belt():
    def st(d, label):
        return {"d": d, "label": label, "qty": None, "colour": None, "pos": None, "nature": False, "human": False, "sex": set(),
                "birth": set(), "death": None}
    stmts = {"s1": st("Q467", "woman"), "s2": st("Q83", "belt")}
    prop = {"inception": "-0339-01-01T00:00:00Z", "precision": "9", "mats": "bronze"}
    seed = wikidata.build("Q9", "sculpture", stmts, prop, {"Q467": {"human"}, "Q83": {"clothing"}})
    assert seed["spec"] == {"person": {"gender": "woman"}, "wear": {"accessory": "belt"},
                            "form": {"medium": "bronze", "period": "ancient"}}
    assert "It is dated 339 BCE." in seed["hint"]


def test_wikidata_contract_constants():
    assert wikidata.DATASET == "wikidata" and wikidata.LICENSE == "CC0 1.0"
    assert wikidata.CITATION.strip().startswith("@") and wikidata.URL.startswith("https://") and wikidata.ATTRIBUTION
