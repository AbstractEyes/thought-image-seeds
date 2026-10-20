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


def test_counts_follow_the_captions():
    cat_names = {c["id"]: c["name"] for c in CATS}
    cat_super = {c["name"]: c["supercategory"] for c in CATS}
    free_id = next(i for i in range(1000) if not core.held_pick(f"coco-image:{i}"))
    # people boxed in the background, no caption speaks of them: no person system
    caps = ["A brown dog lying on the grass.", "A dog resting in a park.", "A dog on the lawn.", "A brown dog in a field."]
    ann = [(18, 200.0, 200.0, 200.0, 150.0, 0)] + [(1, 10.0 + 30 * k, 50.0, 8.0, 20.0, 0) for k in range(3)]
    s = coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)
    assert "person" not in s["spec"] and s["spec"]["thing"]["name"] == "dog"
    # seven dog boxes, the captions say two: the stated number wins
    caps = ["Two dogs playing in a park.", "Two brown dogs on the grass.", "A pair of dogs running.", "Dogs in a field."]
    ann = [(18, 20.0 + 80 * k, 200.0, 60.0, 50.0, 0) for k in range(7)]
    assert coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)["spec"]["thing"]["count"] == "2"
    # no number stated: more than three boxes read as 'several', more than ten as 'many'
    caps = ["Dogs playing in a park.", "Brown dogs on the grass.", "Some dogs running.", "Dogs in a field."]
    assert coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)["spec"]["thing"]["count"] == "several"
    assert coco._box_count(2, False) == "2" and coco._box_count(11, False) == "many" and coco._box_count(1, True) == "many"
    # one man in the captions, bystanders boxed behind him: the captions' one man; a group word leaves the boxes' count
    caps = ["A man walking a brown dog.", "A man with his dog on a street.", "A young man walks a dog.", "Dog on a leash."]
    ann = [(18, 200.0, 200.0, 200.0, 150.0, 0)] + [(1, 10.0 + 60 * k, 50.0, 40.0, 120.0, 0) for k in range(5)]
    assert coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)["spec"]["person"]["count"] == "1"
    caps = ["People walking a brown dog.", "A man with his dog on a street.", "Pedestrians and a dog.", "A dog with people."]
    assert coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)["spec"]["person"]["count"] == "several"
    # one person box, captions of a couple: the captions' number, and no single gender for the pair
    caps = ["A couple standing next to a dog.", "A man and a woman with a dog.", "A couple with their dog.",
            "A girl and a man by a dog."]
    ann = [(18, 200.0, 200.0, 200.0, 150.0, 0), (1, 10.0, 50.0, 40.0, 120.0, 0)]
    p = coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)["spec"]["person"]
    assert p["count"] == "2" and "gender" not in p
    # 'a women' is a slip for one woman, not a group
    assert coco._people_said(coco._Cap("A women who is playing tennis.")) == {"1"}
    assert coco._people_said(coco._Cap("Women playing tennis.")) == {"plural"}
    # one box around a group: 'another', 'each other' and plural-only captions
    ann = [(18, 200.0, 200.0, 200.0, 150.0, 0)]
    caps = ["One brown dog chasing another.", "A dog standing in a park.", "Two brown dogs are wrestling.", "A dog playing with another dog."]
    assert coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)["spec"]["thing"]["count"] == "2"
    caps = ["Brown dogs lying in the sun.", "Dozens of dogs in a field.", "A dog park with dogs.", "Dogs resting."]
    assert coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)["spec"]["thing"]["count"] == "several"
    assert coco._plural("dogs", "dog") and not coco._plural("dog", "dog") and coco._plural("buses", "bus")
    # two dog boxes, every caption says 'a dog': the count is unknown, not two
    ann = [(18, 100.0, 200.0, 200.0, 150.0, 0), (18, 400.0, 100.0, 60.0, 40.0, 0)]
    caps = ["A woman lying on a sofa next to a dog.", "A woman and a dog on a couch.", "The woman and a dog are resting.",
            "Girl playing with her dog."]
    t = coco.build(free_id, 640, 480, ann, caps, cat_names, cat_super)["spec"]["thing"]
    assert t["name"] == "dog" and "count" not in t


def test_sign_text_and_figurines_are_not_the_picture():
    c = coco._Cap("a small shed that says fire hydrant and hose.")
    assert not c.cats.get("fire hydrant")                                   # the label's words, not a hydrant
    c = coco._Cap("A woman reading a book on a bench.")
    assert "book" in c.t                                                    # a reader's book stays
    assert coco._people_said(coco._Cap("A cuddling bride and groom topper on a cake.")) == set()
    assert coco._people_said(coco._Cap("A plastic bride and groom on a wedding cake.")) == set()
    assert coco._people_said(coco._Cap("A bride and groom cutting a cake.")) == {"2"}       # real people stay people


def test_unshout_drops_all_capitals_sentences():
    assert coco.unshout("A man near a TV. A sign for OMNI HOTELS. A MAN WITH A DOG") == "A man near a TV."
    assert core.drop_named(coco.unshout("A JOHN SMITH poster.")) == ""


def test_module_contract():
    for name in ("DATASET", "LICENSE", "URL", "ATTRIBUTION", "CITATION", "TAKEN"):
        assert isinstance(getattr(coco, name), str) and getattr(coco, name)
    assert coco.LICENSE == "CC BY 4.0" and "@inproceedings" in coco.CITATION and "@article" in coco.CITATION
