"""The batch drawer and the row checker."""
import json

from thought_seeds.core import tp
from thought_seeds.rows import check_rows, draw, incoherent, photo_ok, possible_names


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


def test_incoherent_catches_closed_eyes_night_window_light_and_a_horizon_against_the_angle():
    assert incoherent({"look": {"expression": "closed eyes", "eyes": "amber"}})
    assert incoherent({"person": {"gender": "girl"}, "look": {"expression": "closed eyes"},
                       "relation": [{"a": "girl", "rel": "looking at", "b": "lantern"}]})
    assert not incoherent({"look": {"expression": "closed eyes"}, "relation": [{"a": "cat", "rel": "looking at", "b": "bird"}]})
    assert incoherent({"shot": {"light": "soft window"}, "scene": {"setting": "kitchen", "time": "midnight"}})
    assert incoherent({"shot": {"angle": "worm's eye"}, "form": {"compose": "horizon high"}})
    assert incoherent({"shot": {"angle": "overhead"}, "form": {"compose": "horizon low"}})
    assert not incoherent({"shot": {"angle": "low angle"}, "form": {"compose": "horizon low"}})
    assert incoherent({"person": {"gender": "boy"}, "shot": {"framing": "macro"}, "thing": {"name": "camera"}})
    assert not incoherent({"shot": {"framing": "macro"}, "thing": {"name": "camera"}})


def test_photographs_keep_eyes_a_camera_finds_and_no_spotlight_in_the_day_outdoors():
    assert not photo_ok({"look": {"eyes": "scarlet"}}, "photograph") and photo_ok({"look": {"eyes": "scarlet"}}, "illustration")
    assert photo_ok({"look": {"eyes": "hazel"}}, "photograph")
    spot = {"shot": {"light": "spotlight"}, "scene": {"setting": "beach", "time": "noon"}}
    assert not photo_ok(spot, "photograph") and photo_ok(spot, "painting")
    assert photo_ok({"shot": {"light": "spotlight"}, "scene": {"setting": "studio", "time": "noon"}}, "photograph")


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
    assert incoherent({"body": {"pose": "jumping"}, "relation": [{"a": "girl", "rel": "leaning on", "b": "horse"}]})
    assert not incoherent({"body": {"pose": "resting"}, "relation": [{"a": "girl", "rel": "leaning on", "b": "horse"}]})
    assert incoherent({"form": {"medium": "cyanotype"}, "wear": {"clothing": "kimono", "colour": "crimson"}})
    assert not incoherent({"form": {"medium": "cyanotype"}, "wear": {"clothing": "kimono"}})
    assert not incoherent({"form": {"medium": "watercolour"}, "wear": {"colour": "crimson"}})
    assert incoherent({"shot": {"light": "silhouette"}, "form": {"contrast": "colour"}})
    from thought_seeds.rows import photo_ok
    assert not photo_ok({"thing": {"name": "dog", "colour": "light blue"}}, "photograph")
    assert photo_ok({"thing": {"name": "dog", "colour": "light blue"}}, "illustration")
    assert photo_ok({"thing": {"name": "dog", "colour": "light brown"}}, "photograph")
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
    # the classes the row writer reported at batches 030-035
    assert incoherent({"shot": {"light": "silhouette"}, "wear": {"colour": "red"}})
    assert not incoherent({"shot": {"light": "silhouette"}, "wear": {"clothing": "vest"}})
    assert incoherent({"shot": {"light": "silhouette", "framing": "extreme close"}, "wear": {"clothing": "vest"}})
    assert incoherent({"shot": {"framing": "macro"}, "scene": {"setting": "cliff"}})
    assert incoherent({"scene": {"setting": "night market", "time": "golden hour"}})
    assert not incoherent({"scene": {"setting": "night market", "time": "night"}})
    assert incoherent({"relation": [{"a": "kite", "rel": "behind", "b": "camera"}]})
    assert not incoherent({"relation": [{"a": "woman", "rel": "holding", "b": "camera"}]})
    assert incoherent({"relation": [{"a": "window", "rel": "under", "b": "table"}]})
    assert not incoherent({"relation": [{"a": "dog", "rel": "under", "b": "table"}]})
    assert not incoherent({"relation": [{"a": "cup", "rel": "under", "b": "table"}]})
    assert incoherent({"relation": [{"a": "tree", "rel": "in front of", "b": "book"}]})
    assert incoherent({"relation": [{"a": "umbrella", "rel": "above", "b": "tree"}]})
    assert not incoherent({"relation": [{"a": "kite", "rel": "above", "b": "tree"}]})
    series = {"simple": {"wear": {"colour": "red"}, "scene": {"setting": "cliff"}},
              "medium": {"wear": {"colour": "red"}, "scene": {"setting": "cliff"}, "look": {"hair": "afro"}},
              "deep": {"shot": {"light": "silhouette", "framing": "macro"}, "wear": {"colour": "red"}, "scene": {"setting": "cliff"},
                       "look": {"hair": "afro"}, "thing": {"name": "cup"}}}
    t = tighten(series)
    assert nested(t) and all("wear" not in s and "scene" not in s for s in t.values()) and not incoherent(t["deep"])
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


def test_seeded_series_come_from_series_seeds(tmp_path):
    from thought_seeds.rows import series_seed
    spec = {"thing": {"name": "mailbox", "count": "1", "colour": "black"}, "shot": {"framing": "close-up"}}

    def seed(sid, hint):
        return {"seed_id": f"docci:{sid}", "domain": "photograph", "genre": "documentary", "spec": spec, "hint": hint,
                "source": {"dataset": "docci", "id": sid, "license": "CC BY 4.0", "url": "https://example.org"}, "held": False}
    full, short = "A close up view of a black mailbox. " * 13, "A black mailbox."
    assert series_seed(seed("a", full)) and not series_seed(seed("b", short))
    assert not series_seed(dict(seed("c", full), spec={"thing": {"name": "mailbox", "colour": "black"}}))   # two records
    d = tmp_path / "seeds" / "docci"
    d.mkdir(parents=True)
    (d / "docci-00000.jsonl").write_text("".join(json.dumps(seed(f"l{i}", full)) + "\n" for i in range(3))
                                         + "".join(json.dumps(seed(f"s{i}", short)) + "\n" for i in range(3)))
    path = draw(50, 3, 2, str(tmp_path / "rows"), rng_seed=1, seeds=[str(tmp_path / "seeds")], seed_series=2)
    items = [json.loads(line) for line in open(path)]
    series = [it for it in items if it["kind"] == "series"]
    assert [bool(it["seed_id"]) for it in series] == [True, True, False]
    assert all(it["seed_id"].startswith("docci:l") and it["specs"] == {"deep": spec} for it in series[:2])
    assert [it["ids"] for it in series] == [["art-050000", "art-050001", "art-050002"], ["art-050003", "art-050004", "art-050005"],
                                            ["art-050006", "art-050007", "art-050008"]]
    assert all(it["seed_id"] for it in items if it["kind"] == "single")


def test_seeds_without_a_subject_are_never_drawn(tmp_path):
    from thought_seeds.rows import has_subject
    camera = {"shot": {"light": "studio flash", "focus": "bokeh"}, "form": {"medium": "photograph"}}
    robe = {"wear": {"clothing": "robe", "colour": "black"}, "form": {"period": "medieval"}}
    assert not has_subject(camera) and has_subject(robe) and has_subject({"relation": [{"a": "cat", "rel": "beside", "b": "vase"}]})

    def seed(sid, spec):
        return {"seed_id": f"diffusiondb:{sid}", "domain": "photograph", "genre": "portrait", "spec": spec, "hint": "",
                "source": {"dataset": "diffusiondb", "id": sid, "license": "CC0 1.0", "url": "https://example.org"}, "held": False}
    d = tmp_path / "seeds" / "diffusiondb"
    d.mkdir(parents=True)
    (d / "diffusiondb-00000.jsonl").write_text("".join(json.dumps(seed(f"c{i}", camera)) + "\n" for i in range(4))
                                               + "".join(json.dumps(seed(f"r{i}", robe)) + "\n" for i in range(2)))
    path = draw(51, 0, 2, str(tmp_path / "rows"), rng_seed=1, seeds=[str(tmp_path / "seeds")])
    assert {json.loads(line)["seed_id"] for line in open(path)} == {"diffusiondb:r0", "diffusiondb:r1"}


def test_a_picture_two_sources_share_is_drawn_once(tmp_path):
    from thought_seeds import io
    from thought_seeds.rows import picture_of
    spec = {"thing": {"name": "cup", "colour": "red"}, "scene": {"setting": "kitchen"}}

    def seed(ds, sid):
        return {"seed_id": f"{ds}:{sid}", "domain": "painting", "genre": "still life", "spec": spec, "hint": "",
                "source": {"dataset": ds, "id": sid, "license": "CC0 1.0", "url": "https://example.org"}, "held": False}
    for ds, sids in (("met", ["1", "2"]), ("wikidata", ["Q5"])):
        d = tmp_path / "seeds" / ds
        d.mkdir(parents=True)
        (d / f"{ds}-00000.jsonl").write_text("".join(json.dumps(seed(ds, s)) + "\n" for s in sids))
    (tmp_path / "seeds" / "wikidata" / "pictures.json").write_text(json.dumps({"wikidata:Q5": "met:1"}))
    pics = io.pictures(str(tmp_path / "seeds"))
    assert pics == {"wikidata:Q5": "met:1"} and picture_of(seed("wikidata", "Q5"), pics) == picture_of(seed("met", "1"), pics)
    assert picture_of(seed("coco", "9")) == "coco-image:9"
    for rng in range(4):
        rows = tmp_path / f"rows{rng}" / "prod"
        path = draw(40 + rng, 0, 2, str(rows), rng_seed=rng, seeds=[str(tmp_path / "seeds")])
        got = {json.loads(line)["seed_id"] for line in open(path)}
        assert "met:2" in got and len(got & {"met:1", "wikidata:Q5"}) == 1        # one row for the shared picture
