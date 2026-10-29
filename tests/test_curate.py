"""The curation tools: the detectors, patches checked before they are written, the audit of a release, the seed pools."""
import json
import os

from thought_seeds import curate
from thought_seeds.build import main
from thought_seeds.core import tp


def _batch(d, b=9):
    rows = [dict(tp.EXAMPLE, id=f"art-{b:03d}000", series=f"s-{b:03d}00"), dict(tp.EXAMPLE, id=f"art-{b:03d}001", series=f"s-{b:03d}01")]
    path = d / f"batch_{b:03d}.rows.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path, rows


def test_detectors_find_definitions_remarks_and_genres_that_are_no_kind_of_picture():
    assert curate.gloss("Robe: a long, loose outer garment.")
    assert curate.gloss("A sink is a fixed basin with a tap.")
    assert curate.gloss("Turquoise is a blue-green.")
    assert not curate.gloss("Backlit: the lamps sit behind her, so her hair glows.")
    assert not curate.gloss("Neon is the main light.") and not curate.gloss("The lantern is the whole light.")
    assert curate.gloss_kind("Pigtails: hair tied into two tails.") == "bare"
    assert curate.gloss_kind("Rust is a brown-orange. The overalls sit close in hue to the flame.") == "mixed"
    assert curate.remark("Wry reads as amused, an inference.") and curate.remark("White is the one named colour.")
    assert not curate.remark("White blooms against the backlight.")
    assert curate.kind_ok("street portrait") and curate.kind_ok("environmental portrait") and curate.kind_ok("still life")
    assert not curate.kind_ok("harbour portrait") and not curate.kind_ok("night beach")
    assert not curate.kind_ok("food") and not curate.kind_ok("portrait street landscape")


def test_a_patch_writes_genres_and_edits_with_a_backup_and_a_log(tmp_path):
    path, rows = _batch(tmp_path)
    log = tmp_path / "log.jsonl"
    new = "A woman in a yellow raincoat with short hair and a wry half smile."
    res = curate.apply_patch([str(tmp_path)], {"genre": {"art-009000": "portrait"},
                                               "edits": {"art-009001": [[rows[1]["thoughts"][0]["text"], None, new]]}}, str(log))
    assert res["written"] and res["changes"] == 2 and not res["problems"] and not res["new_problems"]
    now = curate.read_rows(str(path))
    assert now[0]["genre"] == "portrait" and now[1]["thoughts"][0]["text"] == new
    assert os.path.exists(str(path) + ".bak") and len(log.read_text(encoding="utf-8").splitlines()) == 2


def test_a_patch_writes_nothing_for_a_missing_text_or_a_broken_chain_question(tmp_path):
    path, rows = _batch(tmp_path)
    before = path.read_text(encoding="utf-8")
    res = curate.apply_patch([str(tmp_path)], {"edits": {"art-009000": [["no such thought", None, None]]}})
    assert res["problems"] and not res["written"]
    mean = rows[0]["thoughts"][3]["text"]                       # it holds the chain question's value, 'single subject'
    res = curate.apply_patch([str(tmp_path)], {"edits": {"art-009000": [[mean, None, None]]}})
    assert res["new_problems"] and not res["written"]
    assert path.read_text(encoding="utf-8") == before and not os.path.exists(str(path) + ".tmp")


def test_a_restore_puts_a_dropped_thought_back_in_its_place(tmp_path):
    path, rows = _batch(tmp_path)
    form = rows[0]["thoughts"][2]["text"]
    assert curate.apply_patch([str(tmp_path)], {"edits": {"art-009000": [[form, None, None]]}})["written"]
    assert len(curate.read_rows(str(path))[0]["thoughts"]) == 4
    res = curate.apply_patch([str(tmp_path)], {"restore": {"art-009000": [[form, "Neon lights her face, seen from the waist up."]]}})
    assert res["written"]
    t = curate.read_rows(str(path))[0]["thoughts"]
    assert [x["step"] for x in t] == ["see", "place", "form", "mean", "say"] and t[2]["text"] == "Neon lights her face, seen from the waist up."


def test_the_audit_reads_every_accepted_row(tmp_path):
    d = tmp_path / "prod"
    d.mkdir()
    _batch(d)
    (tmp_path / "ACCEPTED.txt").write_text("# the accepted batches\nprod 9\n", encoding="utf-8")
    rep = curate.audit(str(tmp_path / "ACCEPTED.txt"))
    assert rep["rows"] == 2 and not rep["problems"] and not rep["duplicate_ids"] and not rep["genre"]
    assert len(rep["remark"]) == 2                              # the example row's 'an inference'


def test_pools_hold_the_quota_and_skip_held_seeds_and_drawn_pictures(tmp_path):
    src = tmp_path / "seeds" / "coco"
    src.mkdir(parents=True)
    spec = {"person": {"gender": "man", "count": "1"}, "wear": {"clothing": "suit"}, "scene": {"setting": "bus stop"}}
    seeds = [dict(tp.EXAMPLE_SEED, seed_id=f"coco:{i}", spec=spec, held=False) for i in range(6)]
    seeds.append(dict(seeds[0], seed_id="coco:99", held=True))
    (src / "coco-00000.jsonl").write_text("".join(json.dumps(s) + "\n" for s in seeds), encoding="utf-8")
    rows = tmp_path / "rows"
    rows.mkdir()
    (rows / "batch_001.specs.jsonl").write_text(json.dumps({"kind": "single", "ids": ["art-001000"], "seed_id": "coco:0"}) + "\n")
    res = curate.pools(str(tmp_path / "seeds"), [str(rows)], str(tmp_path / "pools"), 2, 3, {"coco": 1}, rng_seed=1)
    assert res["eligible"]["coco"] == 5 and res["picked"]["coco"] == 4
    ids = [json.loads(line)["seed_id"] for p in res["pools"] for line in open(p, encoding="utf-8")]
    assert len(ids) == 4 and "coco:0" not in ids and "coco:99" not in ids


def test_the_command_runs_the_acceptance_read(tmp_path, capsys):
    _batch(tmp_path)
    assert main(["--accept=9-9", f"--rows-dir={tmp_path}", "--sample=1"]) == 0
    out = capsys.readouterr().out
    assert "batch 009: rows 2" in out and "remark: 2" in out and "==== rows to read ====" in out
