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
