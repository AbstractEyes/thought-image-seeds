"""The GQA importer on a tiny inline fixture shaped like sceneGraphs.zip (no network)."""
import io
import json
import zipfile

from thought_seeds import core
from thought_seeds.sources import gqa


def _o(name, x, y, w, h, attrs=(), rels=()):
    return {"name": name, "x": x, "y": y, "w": w, "h": h, "attributes": list(attrs),
            "relations": [{"name": p, "object": t} for p, t in rels]}


# a man in a red jacket on a beach under a cloudy sky, holding an umbrella, a sitting brown dog to his right
BEACH = {"width": 640, "height": 480, "objects": {
    "1": _o("man", 100, 80, 160, 380, ["standing"], [("wearing", "2"), ("holding", "3"), ("to the left of", "4")]),
    "2": _o("jacket", 110, 150, 140, 150, ["red"]),
    "3": _o("umbrella", 60, 20, 200, 120, ["black"]),
    "4": _o("dog", 450, 330, 120, 110, ["brown", "sitting"], [("to the right of", "1")]),
    "5": _o("sky", 0, 0, 640, 200, ["cloudy"]),
    "6": _o("beach", 0, 280, 640, 200, []),
    "7": _o("hand", 200, 200, 30, 30, [], [("of", "1")]),
}}
# two people of different genders of the same size: a count, no gender, no wear (the main one is not clear)
PAIR = {"width": 500, "height": 500, "objects": {
    "1": _o("man", 20, 50, 200, 400, [], [("wearing", "3")]),
    "2": _o("woman", 260, 60, 190, 390, []),
    "3": _o("coat", 30, 120, 180, 200, ["blue"]),
    "4": _o("pitcher", 220, 400, 40, 60, ["glass"]),          # a jug: no baseball in view, so not a person
}}
EMPTY = {"width": 100, "height": 100, "objects": {}}


def test_streamed_object_reader_survives_tiny_chunks():
    text = json.dumps({"11": BEACH, "12": PAIR, "13": EMPTY}, indent=1)
    got = list(gqa.iter_object(io.StringIO(text), chunk=7))
    assert [k for k, _ in got] == ["11", "12", "13"] and got[0][1] == BEACH


def test_beach_spec():
    s, genre = gqa.spec_of(BEACH)
    spec = s.spec()
    assert spec["person"] == {"count": "1", "gender": "man"}
    assert spec["wear"] == {"clothing": "jacket", "accessory": "umbrella", "colour": "red"}
    assert spec["body"] == {"pose": "standing"}
    assert spec["scene"] == {"setting": "beach", "weather": "overcast"}
    assert spec["thing"] == {"name": "dog", "count": "1", "colour": "brown", "state": "sitting", "position": "right"}
    assert spec["form"] == {"medium": "photograph"}
    rels = spec["relation"]
    assert {"a": "man", "rel": "holding", "b": "umbrella"} in rels
    assert any({r["a"], r["b"]} == {"man", "dog"} and r["rel"] in ("left of", "right of") for r in rels)
    assert all(r["a"] != "hand" and r["b"] != "hand" for r in rels)          # a body part is never a relation end
    assert core.check_spec(spec) == [] and genre == "documentary"           # the man fills a fifth of the frame: not a portrait


def test_pair_keeps_only_what_is_true_of_both():
    s, _ = gqa.spec_of(PAIR)
    spec = s.spec()
    assert spec["person"] == {"count": "2"}
    assert "wear" not in spec                                     # the coat is the man's, and he is not clearly the subject
    assert spec["thing"]["name"] == "pitcher"                    # the jug is the thing, not a third person
    assert gqa.spec_of(EMPTY) == (None, "no objects")


def test_seeds_from_a_zip(tmp_path):
    d = tmp_path / "gqa"
    d.mkdir()
    with zipfile.ZipFile(d / gqa.ZIP, "w") as z:
        z.writestr("train_sceneGraphs.json", json.dumps({"11": BEACH, "13": EMPTY}))
        z.writestr("val_sceneGraphs.json", json.dumps({"12": PAIR}))
    out = list(gqa.seeds(str(tmp_path)))
    assert [s["seed_id"] for s in out] == ["gqa:11", "gqa:12"]
    for seed in out:
        assert set(seed) == {"seed_id", "domain", "genre", "spec", "source", "held"}          # no hint: GQA has no text
        assert seed["domain"] == "photograph" and seed["source"]["license"] == "CC BY 4.0"
        assert core.check_spec(seed["spec"]) == [] and not (core.sealed(seed["spec"]) and not seed["held"])
    assert gqa.STATS["skip: no objects"] == 1
    assert list(gqa.seeds(str(tmp_path), limit=1))[0]["seed_id"] == "gqa:11"


def test_a_sealed_thing_name_takes_its_whole_system(tmp_path):
    # a standing man and a black bird ('bird' is a sealed thing name): a training seed loses the whole thing system (no count,
    # colour or position of nothing), a held seed keeps it
    bird = {"width": 640, "height": 480, "objects": {"1": _o("man", 100, 80, 160, 380, ["standing"]),
                                                     "2": _o("bird", 400, 100, 120, 100, ["black"])}}
    kept = next(str(i) for i in range(200) if not core.held_pick(f"gqa:{i}"))
    held = next(str(i) for i in range(200) if core.held_pick(f"gqa:{i}"))
    d = tmp_path / "gqa"
    d.mkdir()
    with zipfile.ZipFile(d / gqa.ZIP, "w") as z:
        z.writestr("train_sceneGraphs.json", json.dumps({kept: bird, held: bird}))
        z.writestr("val_sceneGraphs.json", json.dumps({}))
    out = {s["source"]["id"]: s for s in gqa.seeds(str(tmp_path))}
    assert out[kept]["held"] is False and "thing" not in out[kept]["spec"]
    assert out[kept]["spec"]["person"] == {"count": "1", "gender": "man"} and out[kept]["spec"]["body"] == {"pose": "standing"}
    assert out[held]["held"] is True
    assert out[held]["spec"]["thing"] == {"name": "bird", "count": "1", "colour": "black", "position": "right"}


def test_a_worn_watch_or_wine_glasses():
    g = {"width": 400, "height": 400, "objects": {"1": _o("man", 50, 20, 200, 370, [], [("wearing", "2"), ("holding", "3")]),
                                                  "2": _o("watch", 200, 200, 20, 20, ["silver"]),
                                                  "3": _o("wine glasses", 150, 150, 40, 40)}}
    assert gqa.spec_of(g)[0].spec()["wear"] == {"accessory": "watch"}     # a watch worn in a graph is the accessory


def test_module_contract():
    for name in ("DATASET", "LICENSE", "URL", "ATTRIBUTION", "CITATION", "TAKEN"):
        assert getattr(gqa, name)
    assert gqa.LICENSE == "CC BY 4.0" and "@inproceedings{hudson2019gqa" in gqa.CITATION
