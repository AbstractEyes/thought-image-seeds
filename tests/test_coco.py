"""The COCO importer on a tiny inline fixture shaped like annotations_trainval2017.zip (no network)."""
import json
import os
import zipfile

from thought_seeds import core
from thought_seeds.sources import coco

CATS = [{"supercategory": "person", "id": 1, "name": "person"}, {"supercategory": "vehicle", "id": 2, "name": "bicycle"},
        {"supercategory": "animal", "id": 18, "name": "dog"}, {"supercategory": "sports", "id": 38, "name": "kite"}]


def _ann(aid, image_id, cat, box, crowd=0):
    # the real file's field order: segmentation, area, iscrowd, image_id, bbox, category_id, id
    return {"segmentation": [[box[0], box[1], box[0] + box[2], box[1], box[0] + box[2], box[1] + box[3]]],
            "area": box[2] * box[3] / 2.0, "iscrowd": crowd, "image_id": image_id, "bbox": box, "category_id": cat, "id": aid}


def _write_fixture(raw):
    images = [{"license": 4, "file_name": f"{i:012d}.jpg", "coco_url": "", "height": 480, "width": 640, "date_captured": "",
               "flickr_url": "", "id": i} for i in (1, 2, 3)]
    anns = [_ann(10, 1, 1, [50.0, 100.0, 100.0, 300.0]), _ann(11, 1, 18, [400.0, 300.0, 150.0, 120.0]),
            _ann(20, 2, 1, [100.0, 100.0, 100.0, 300.0]),
            _ann(30, 3, 1, [280.0, 300.0, 60.0, 150.0]), _ann(31, 3, 38, [300.0, 20.0, 60.0, 40.0])]
    caps = [(1, "A man in a red jacket standing next to a brown dog."), (1, "A man standing beside his brown dog on a beach."),
            (1, "A man wearing a red jacket stands near a dog at the beach."), (1, "Man and dog on the beach at sunset."),
            (1, "A man with his dog on the sand, photographed by John Smith."),
            (2, "A naked man on a beach."), (2, "A man on a beach."),
            (3, "A woman flying a kite on the beach."), (3, "A woman with a kite flying high above her."),
            (3, "A red kite flying over a woman on the sand."), (3, "A woman on a beach looks up."), (3, "A kite in the sky.")]
    inst = {"info": {"description": "COCO 2017 Dataset"}, "licenses": [], "images": images, "annotations": anns, "categories": CATS}
    capf = {"info": {}, "licenses": [], "images": images,
            "annotations": [{"image_id": i, "id": 100 + k, "caption": t} for k, (i, t) in enumerate(caps)]}
    d = os.path.join(raw, "coco")
    os.makedirs(d)
    with zipfile.ZipFile(os.path.join(d, coco.ZIP), "w") as z:
        # compact separators like the real file, so the pattern reader (not the fallback) is what runs
        z.writestr("annotations/instances_val2017.json", json.dumps(inst, separators=(",", ": ")))
        z.writestr("annotations/captions_val2017.json", json.dumps(capf))


def test_seeds_from_the_fixture(tmp_path):
    _write_fixture(str(tmp_path))
    out = {s["seed_id"]: s for s in coco.seeds(str(tmp_path))}
    assert set(out) == {"coco:1", "coco:3"}                              # image 2 holds an explicit word
    assert coco.STATS["explicit words"] == 1
    s = out["coco:1"]
    assert s["domain"] == "photograph" and s["genre"] == "animal" and s["held"] is False
    assert s["spec"] == {
        "person": {"count": "1", "gender": "man"},
        "thing": {"name": "dog", "count": "1", "position": "right", "colour": "brown"},
        "body": {"pose": "standing"},
        "wear": {"clothing": "jacket", "colour": "red"},
        "scene": {"setting": "beach"},
        "relation": [{"a": "man", "rel": "left of", "b": "dog"}]}
    assert "John" not in s["hint"] and s["hint"].startswith("A man in a red jacket standing next to a brown dog.")
    assert s["source"] == {"dataset": "coco", "id": "1", "license": "CC BY 4.0", "url": "https://cocodataset.org/#explore?id=1"}
    assert core.check_spec(s["spec"]) == []
    k = out["coco:3"]["spec"]
    assert k["thing"]["name"] == "kite" and k["thing"]["state"] == "flying" and k["person"]["gender"] == "woman"
    assert {"a": "woman", "rel": "below", "b": "kite"} in k["relation"]   # a kite is aloft: 'below' is a true reading


def test_pattern_reader_matches_the_full_parse(tmp_path):
    _write_fixture(str(tmp_path))
    with zipfile.ZipFile(os.path.join(str(tmp_path), "coco", coco.ZIP)) as z:
        raw = z.read("annotations/instances_val2017.json")
    images, cats, anns = coco._instances(raw)
    d = json.loads(raw)
    assert images == d["images"] and cats == d["categories"]
    assert sum(len(v) for v in anns.values()) == len(d["annotations"])
    # another field order: the reader falls back to the full parse and gets the same boxes
    d2 = dict(d, annotations=[{k: a[k] for k in ("id", "category_id", "bbox", "image_id", "iscrowd", "area")}
                              for a in d["annotations"]])
    _, _, anns2 = coco._instances(json.dumps(d2).encode())
    assert {k: sorted(v) for k, v in anns2.items()} == {k: sorted(v) for k, v in anns.items()}


def test_a_sealed_object_only_in_the_held_tenth():
    cat_names = {c["id"]: c["name"] for c in CATS}
    cat_super = {c["name"]: c["supercategory"] for c in CATS}
    caps = ["A bicycle leaning on a wall.", "A red bicycle parked by a wall.", "A bicycle on a street.", "A bike by a wall.",
            "An old bicycle."]
    ann = [(2, 100.0, 100.0, 300.0, 200.0, 0)]
    assert core.sealed({"thing": {"name": "bicycle"}})
    held_id = next(i for i in range(1000) if core.held_pick(f"coco-image:{i}"))
    free_id = next(i for i in range(1000) if not core.held_pick(f"coco-image:{i}"))
    s = coco.build(held_id, 640, 480, ann, caps, cat_names, cat_super)
    assert s["held"] is True and s["spec"]["thing"]["name"] == "bicycle"
    s = coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)
    assert s is None or "bicycle" not in json.dumps(s["spec"])           # never a thing whose name the route would strip


def test_unshout_drops_all_capitals_sentences():
    assert coco.unshout("A man near a TV. A sign for OMNI HOTELS. A MAN WITH A DOG") == "A man near a TV."
    assert core.drop_named(coco.unshout("A JOHN SMITH poster.")) == ""


def test_module_contract():
    for name in ("DATASET", "LICENSE", "URL", "ATTRIBUTION", "CITATION", "TAKEN"):
        assert isinstance(getattr(coco, name), str) and getattr(coco, name)
    assert coco.LICENSE == "CC BY 4.0" and "@inproceedings" in coco.CITATION and "@article" in coco.CITATION
