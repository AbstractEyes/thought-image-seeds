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
                         "form": {"medium": "oil painting", "style": "baroque"}}       # no origin statement: no era name
    assert core.check_spec(a["spec"]) == []
    assert "two brown dogs" in a["hint"] and a["hint"].startswith("A painting made with oil paint, canvas. It is dated 1650.")
    assert a["source"] == {"dataset": "wikidata", "id": "Q1", "license": "CC0 1.0", "url": "https://www.wikidata.org/wiki/Q1"}
    b = out["wikidata:Q2"]
    assert b["spec"] == {"person": {"count": "1"}, "thing": {"name": "lion"}}   # born 1600, painted 1610: no gender, no age
    assert "Peter" not in b["hint"] and "Venus" not in b["hint"] and "a figure and a lion" in b["hint"]
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


def _st(d, label, human=False, qty=None, sex=(), birth=()):
    return {"d": d, "label": label, "qty": qty, "colour": None, "pos": None, "nature": False, "human": human,
            "sex": set(sex), "birth": set(birth), "death": None}


def _work(*sts, year="1650", origin=None, genres="", mats="oil paint"):
    prop = {"inception": f"{year}-01-01T00:00:00Z" if not year.startswith("-") else f"{year}-01-01T00:00:00Z", "precision": "9",
            "mats": mats, "genres": genres}
    if origin is not None:
        prop["origin"] = origin
    return {f"s{i}": st for i, st in enumerate(sts)}, prop


TYPES = {"Q467": {"human"}, "Q144": {"animal"}, "Q726": {"animal"}, "Q1": {"artifact"}, "Q2": {"artifact"}, "Q3": {"artifact"},
         "Q4": {"artifact"}, "Q5": {"artifact"}}


def test_era_names_only_for_a_european_origin():
    def period(origin, year="1650"):
        stmts, prop = _work(_st("Q144", "dog"), _st("Q726", "horse"), year=year, origin=origin)
        return wikidata.build("Q10", "painting", stmts, prop, TYPES)["spec"].get("form", {}).get("period")
    assert period({"countries": ["Kingdom of the Netherlands"], "cultures": []}) == "baroque"
    assert period({"countries": [], "cultures": ["Italian Renaissance"]}, "1500") == "renaissance"
    assert period({"countries": ["Qing dynasty"], "cultures": []}) is None              # a Chinese work of 1721 is no baroque
    assert period({"countries": ["India"], "cultures": ["Hinduism"]}) is None
    assert period(None) is None                                                         # no statement: no era name
    assert period(None, "1850") == "19th century"                                       # the neutral names stay


def test_the_person_count_is_stated_never_summed():
    signers = [_st(f"Q{100 + i}", f"Signer {i}", human=True, sex=["Q6581097"]) for i in range(14)]
    stmts, prop = _work(*signers)
    seed = wikidata.build("Q11", "painting", stmts, prop, TYPES)
    assert "count" not in seed["spec"]["person"] and "14" not in seed["hint"] and "men" in seed["hint"]
    stmts, prop = _work(_st("Q200", "Louis", human=True, sex=["Q6581097"]), _st("Q1", "carriage"), _st("Q9", "postilion"))
    assert "count" not in wikidata.build("Q12", "painting", stmts, prop, TYPES)["spec"]["person"]   # an untyped figure: more
    stmts, prop = _work(_st("Q200", "Louis", human=True, sex=["Q6581097"]), _st("Q1", "carriage"), _st("Q8", "crowd"))
    assert "count" not in wikidata.build("Q13", "painting", stmts, prop, TYPES)["spec"].get("person", {})
    stmts, prop = _work(_st("Q200", "Louis", human=True, sex=["Q6581097"]), _st("Q1", "carriage"))
    assert wikidata.build("Q14", "painting", stmts, prop, TYPES)["spec"]["person"] == {"count": "1", "gender": "man"}
    stmts, prop = _work(_st("Q467", "soldier", qty=3), _st("Q1", "carriage"))
    assert wikidata.build("Q15", "painting", stmts, prop, TYPES)["spec"]["person"]["count"] == "3"     # a stated quantity


def test_no_age_or_gender_from_a_birth_year():
    stmts, prop = _work(_st("Q300", "Ashurbanipal", human=True, sex=["Q6581097"], birth=[-684]), _st("Q726", "horse"), year="-0667")
    seed = wikidata.build("Q16", "sculpture", stmts, prop, TYPES)
    assert seed["spec"]["person"] == {"count": "1"} and "boy" not in seed["hint"]      # under 18 by the birth year: withheld
    stmts, prop = _work(_st("Q301", "Sitter", human=True, sex=["Q6581072"], birth=[1600]), _st("Q726", "horse"))
    assert wikidata.build("Q17", "painting", stmts, prop, TYPES)["spec"]["person"] == {"count": "1", "gender": "woman"}


def test_activities_and_ideas_are_never_the_thing():
    stmts, prop = _work(_st("Q2", "combined driving"), _st("Q3", "mathematics"), _st("Q4", "philosophy"), _st("Q5", "prayer"),
                        _st("Q726", "horse"))
    seed = wikidata.build("Q18", "painting", stmts, prop, TYPES)
    assert seed["spec"]["thing"]["name"] == "horse" and "Also shown: combined driving" in seed["hint"]
    for low in ("ice skating", "bathing", "ethnography", "astronomy", "childhood"):
        assert wikidata._not_a_thing(low), low
    for low in ("painting", "building", "sailing ship", "earring", "city", "hood", "fence"):
        assert not wikidata._not_a_thing(low), low


def test_the_explicit_filter_reads_inside_labels_and_genres():
    for label in ("erotic dance", "prostitute", "brothel", "human sexuality", "The Rape of Europa", "butt plug"):
        stmts, prop = _work(_st("Q1", label), _st("Q144", "dog"), _st("Q726", "horse"))
        assert wikidata.build("Q19", "painting", stmts, prop, TYPES) is None, label
    stmts, prop = _work(_st("Q144", "dog"), _st("Q726", "horse"), genres="erotic art")
    assert wikidata.build("Q19", "painting", stmts, prop, TYPES) is None
    stmts, prop = _work(_st("Q144", "dog"), _st("Q726", "horse"), genres="nude")
    assert wikidata.build("Q19", "painting", stmts, prop, TYPES) is not None            # an art nude is no explicit work


def test_a_museum_work_is_routed_by_the_museum_seed_id(tmp_path):
    raw = str(tmp_path)
    os.makedirs(os.path.join(raw, "met"))
    os.makedirs(os.path.join(raw, "nga"))
    with open(os.path.join(raw, "met", "MetObjects.csv"), "w", encoding="utf-8", newline="") as fh:
        fh.write("Object ID,Title,Object Wikidata URL\n436535,A,https://www.wikidata.org/wiki/Q42\n"
                 "436530,B,https://www.wikidata.org/wiki/Q42\n10,C,\n")
    with open(os.path.join(raw, "nga", "objects.csv"), "w", encoding="utf-8", newline="") as fh:
        fh.write("objectid,title,wikidataid\n46131,D,Q43\n")
    links = wikidata.museum_links(raw)
    assert links == {"Q42": {"met": ["436535", "436530"]}, "Q43": {"nga": ["46131"]}}
    assert wikidata.museum_group(None, links, "Q42") == "met:436530"                     # the smallest object id
    assert wikidata.museum_group({"aic": ["27992"], "met": []}, links, "Q43") == "aic:27992"   # a stated id; AIC before NGA
    assert wikidata.museum_group(None, links, "Q44") is None
    sealed = core.HELD["thing"][0]                                                       # a sealed thing: the routing shows
    qid = next(f"Q{i}" for i in range(1000, 9000) if not core.held_pick(f"wikidata:Q{i}"))
    group = next(f"met:{i}" for i in range(1000, 9000) if core.held_pick(f"met:{i}"))
    stmts, prop = _work(_st("Q2", sealed))
    seed = wikidata.build(qid, "painting", stmts, prop, {"Q2": {"artifact"}}, group)
    assert seed["held"] is True and seed["spec"]["thing"]["name"] == sealed             # the group's draw, not the work's own
    unrouted = wikidata.build(qid, "painting", stmts, prop, {"Q2": {"artifact"}})
    assert unrouted is None or unrouted["held"] is False


def test_wikidata_contract_constants():
    assert wikidata.DATASET == "wikidata" and wikidata.LICENSE == "CC0 1.0"
    assert wikidata.CITATION.strip().startswith("@") and wikidata.URL.startswith("https://") and wikidata.ATTRIBUTION
