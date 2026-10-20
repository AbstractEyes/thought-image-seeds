"""The batch drawer and the row checker."""
import json

from thought_seeds.core import tp
from thought_seeds.rows import check_rows, draw, possible_names


def test_draw_allots_ids_and_series(tmp_path):
    path = draw(7, 3, 4, str(tmp_path), rng_seed=1)
    items = [json.loads(line) for line in open(path)]
    assert [it["kind"] for it in items] == ["series"] * 3 + ["single"] * 4
    ids = [i for it in items for i in it["ids"]]
    assert ids == [f"art-007{k:03d}" for k in range(13)]
    assert items[0]["series"] == "s-00700" and set(items[0]["specs"]) == {"simple", "medium", "deep"}
    assert all(it["license"] == "Apache-2.0" for it in items)


def test_check_rows_catches_license_spec_and_missing(tmp_path):
    path = draw(8, 1, 0, str(tmp_path), rng_seed=2)
    it = json.loads(open(path).readline())
    row = dict(tp.EXAMPLE, id=it["ids"][1], series=it["series"])
    rows = tmp_path / "batch_008.rows.jsonl"
    rows.write_text(json.dumps(row) + "\n")
    rep = check_rows(str(rows), path)
    assert rep["by_rule"].get("spec kept") == 1 and rep["by_rule"].get("missing") == 1


def test_possible_names_flags_capitalized_words_inside_sentences():
    row = {"thoughts": [{"step": "see", "text": "A woman reads, and Margaret smiles."}], "wordings": {"caption": "A dog."}}
    assert possible_names(row) == ["Margaret"]


def test_drawn_specs_are_photographs_paintings_or_illustrations(tmp_path):
    path = draw(9, 30, 30, str(tmp_path), rng_seed=3)
    doms = {json.loads(line)["domain"] for line in open(path)}
    assert doms <= {"photograph", "painting", "illustration"}


def test_drawn_specs_pass_the_coherence_filter(tmp_path):
    from thought_seeds.rows import incoherent
    assert incoherent({"person": {"gender": "boy", "age": "20s"}}) == ["boy aged 20s"]
    assert incoherent({"scene": {"setting": "library", "weather": "fog"}})
    # the classes the row writer reported at batches 004-007
    macro = {"shot": {"framing": "macro"}, "relation": [{"a": "boy", "rel": "holding", "b": "suitcase"}]}
    assert incoherent(macro) == ["macro framing of a relation between two things"]
    assert incoherent({"shot": {"framing": "detail"}, "look": {"hair": "afro", "expression": "blush"}})
    assert not incoherent({"shot": {"framing": "detail"}, "look": {"hair": "afro"}})
    assert incoherent({"shot": {"light": "soft window"}, "scene": {"setting": "beach"}})
    assert incoherent({"shot": {"light": "street lamp"}, "scene": {"setting": "stadium"}})
    assert not incoherent({"shot": {"light": "street lamp"}, "scene": {"setting": "alley"}})
    assert incoherent({"shot": {"light": "golden"}, "scene": {"setting": "subway"}})
    assert incoherent({"form": {"compose": "horizon high"}, "scene": {"setting": "subway"}})
    assert incoherent({"relation": [{"a": "book", "rel": "inside", "b": "window"}]})
    assert incoherent({"relation": [{"a": "man", "rel": "holding", "b": "cup"}, {"a": "cup", "rel": "inside", "b": "suitcase"}]})
    assert incoherent({"shot": {"light": "high key"}, "scene": {"time": "blue hour"}})
    assert incoherent({"scene": {"weather": "heat shimmer", "time": "late evening"}})
    assert incoherent({"shot": {"light": "silhouette"}, "relation": [{"a": "hat", "rel": "same colour as", "b": "door"}]})
    assert incoherent({"shot": {"lens": "anamorphic"}, "form": {"medium": "lithograph"}})
    assert not incoherent({"shot": {"lens": "35mm"}, "form": {"medium": "3d render"}})
    assert incoherent({"shot": {"framing": "extreme close"}, "form": {"compose": "frame in frame"}})
    assert incoherent({"shot": {"framing": "extreme close"}, "thing": {"name": "dog"}})
    assert not incoherent({"shot": {"framing": "macro"}, "thing": {"name": "cup"}})
    assert incoherent({"shot": {"framing": "detail", "angle": "over the shoulder"}})
    assert incoherent({"shot": {"light": "silhouette"}, "form": {"contrast": "low"}})
    assert incoherent({"scene": {"setting": "library", "weather": "clear"}})
    assert incoherent({"body": {"pose": "floating"}, "scene": {"setting": "classroom"}})
    assert not incoherent({"body": {"pose": "floating"}, "scene": {"setting": "pier"}})
    assert incoherent({"scene": {"setting": "subway", "time": "blue hour"}})
    assert not incoherent({"scene": {"setting": "subway", "time": "midnight"}})
    assert incoherent({"shot": {"light": "candle"}, "scene": {"setting": "bridge", "weather": "storm"}})
    assert not incoherent({"shot": {"light": "candle"}, "scene": {"setting": "attic"}})
    assert incoherent({"shot": {"light": "fluorescent"}, "scene": {"setting": "stadium", "time": "afternoon"}})
    assert not incoherent({"shot": {"light": "fluorescent"}, "scene": {"setting": "stadium", "time": "night"}})
    assert incoherent({"relation": [{"a": "man", "rel": "holding", "b": "drum"}, {"a": "drum", "rel": "leaning on", "b": "chair"}]})
    from thought_seeds.rows import tighten
    series = {"medium": {"shot": {"framing": "macro"}, "look": {"hair": "afro", "expression": "blush"},
                         "relation": [{"a": "boy", "rel": "holding", "b": "cup"}]},
              "simple": {"look": {"hair": "afro"}}}
    t = tighten(series)
    assert t["medium"] == {"shot": {"framing": "macro"}, "look": {"hair": "afro"}} and not incoherent(t["medium"])
    assert t["simple"] == series["simple"] and series["medium"]["look"]["expression"] == "blush"     # the input is not changed
    # the cut is decided on the fullest rank and applied to all: the ranks stay nested
    from thought_seeds.rows import nested
    series = {"simple": {"wear": {"clothing": "uniform"}, "thing": {"name": "cup"}},
              "medium": {"shot": {"framing": "macro"}, "wear": {"clothing": "uniform"}, "thing": {"name": "cup"}},
              "deep": {"shot": {"framing": "macro"}, "look": {"hair": "afro"}, "wear": {"clothing": "uniform"}, "thing": {"name": "cup"}}}
    assert nested(series)
    t = tighten(series)
    assert nested(t) and "wear" not in t["simple"] and "wear" not in t["medium"] and t["deep"]["look"] == {"hair": "afro"}
    path = draw(11, 40, 40, str(tmp_path), rng_seed=5)
    for line in open(path):
        it = json.loads(line)
        for spec in (it["specs"].values() if it["kind"] == "series" else [it["spec"]]):
            assert not incoherent(spec)
            assert all("nonbinary" not in (r["a"], r["b"]) for r in spec.get("relation", []))


def test_draw_thin_specs_domains_and_seeded_depths(tmp_path):
    from thought_seeds.rows import seed_depth, thin
    path = draw(12, 20, 20, str(tmp_path), rng_seed=6, domains={"illustration": 1.0})
    for line in open(path):
        it = json.loads(line)
        assert it["domain"] == "illustration" or (it.get("spec") or it["specs"]["deep"]).get("form", {}).get("medium")
        if it["kind"] == "series":
            assert not thin(it["specs"]["simple"], "simple") and not thin(it["specs"]["medium"], "medium")
        else:
            assert not thin(it["spec"], it["depth"])
    rich = {"spec": {"person": {"gender": "man", "count": "1"}, "thing": {"name": "dog", "count": "1"}}, "hint": "x" * 320}
    assert seed_depth(rich) == "medium" and seed_depth(dict(rich, hint="")) == "simple"
    thin3 = {"spec": {"person": {"gender": "man", "count": "1"}, "thing": {"name": "dog"}}, "hint": "x" * 320}
    assert seed_depth(thin3) == "simple"                                    # three facts stay simple, whatever the hint
