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
