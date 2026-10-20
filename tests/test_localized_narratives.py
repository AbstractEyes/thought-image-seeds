"""The Localized Narratives importer on a tiny inline fixture shaped like coco_val_captions.jsonl (no network)."""
import json
import os

from thought_seeds import core
from thought_seeds.sources import localized_narratives as ln

ROWS = [
    {"dataset_id": "mscoco_val2017", "image_id": "11", "annotator_id": 3,
     "caption": "In this image there is a woman wearing a blue jacket and sitting on a sofa. The sofa is in green color. "
                "Behind the woman there is a lamp. In the background there is a wall with a poster by Pablo Picasso."},
    {"dataset_id": "mscoco_val2017", "image_id": "12", "annotator_id": 4,
     "caption": "In this picture we can see two brown horses standing on the grass. In the background we can see trees."},
    {"dataset_id": "mscoco_val2017", "image_id": "12", "annotator_id": 5,
     "caption": "Here we can see two horses standing in a field. Behind them there are trees and the sky is cloudy."},
    {"dataset_id": "mscoco_val2017", "image_id": "12", "annotator_id": 6,
     "caption": "There are two horses and a fence. The sky is blue."},
    {"dataset_id": "mscoco_val2017", "image_id": "13", "annotator_id": 7, "caption": "A naked man stands on a beach."},
    {"dataset_id": "mscoco_val2017", "image_id": "14", "annotator_id": 8,
     "caption": "We can see a car on the road. On the right side of the image there is a car."},
]


def _write(raw):
    d = os.path.join(raw, "localized_narratives")
    os.makedirs(d)
    with open(os.path.join(d, "coco_val_captions.jsonl"), "w", encoding="utf-8") as fh:
        for r in ROWS:
            fh.write(json.dumps(r) + "\n")


def test_seeds_from_the_fixture(tmp_path):
    _write(str(tmp_path))
    out = {s["seed_id"]: s for s in ln.seeds(str(tmp_path))}
    assert set(out) == {"localized_narratives:11", "localized_narratives:12", "localized_narratives:14"}   # 13: explicit
    s = out["localized_narratives:11"]
    assert s["spec"] == {
        "person": {"count": "1", "gender": "woman"},
        "thing": {"name": "couch", "count": "1", "colour": "green"},
        "body": {"pose": "sitting"},
        "wear": {"clothing": "jacket", "colour": "blue"},
        "relation": [{"a": "lamp", "rel": "behind", "b": "woman"}]}
    assert s["genre"] == "interior" and s["domain"] == "photograph" and s["held"] is False
    assert "Picasso" not in s["hint"] and s["hint"].startswith("There is a woman wearing a blue jacket")
    assert s["source"] == {"dataset": "localized_narratives", "id": "11", "license": "CC BY 4.0",
                           "url": "https://cocodataset.org/#explore?id=11"}
    assert core.check_spec(s["spec"]) == []
    # three narrations: a value two of them agree on (the horses' count and state); 'brown' is one narration's word only
    h = out["localized_narratives:12"]["spec"]
    assert h["thing"] == {"name": "horse", "count": "2", "state": "standing"}
    # 'a car ... a car': two cars, each said of once: the name only (no count, no position)
    assert out["localized_narratives:14"]["spec"] == {"thing": {"name": "car"}}


def test_single_text_rules():
    f = ln.facts("A man in a red shirt and a woman in a white dress are standing near a dog.", True)
    assert ("person", "gender") not in f and ("person", "count") not in f      # two people, two genders: no single value
    f = ln.facts("In this picture we can see three people standing on the road.", True)
    assert f[("person", "count")] == "3" and ("body", "pose") not in f         # a pose is read for one person only
    f = ln.facts("There is a brown dog lying on the grass and a black and white cat sitting beside the dog.", True)
    assert f[("thing", "colour")] == "brown" and f["relation"] == [("cat", "beside", "dog")]


def test_one_person_takes_the_narrations_pronoun():
    f = ln.facts("There is a person standing on the ground and he is holding a racket. Behind him there is a fence.", False)
    assert f[("person", "count")] == "1" and f[("person", "gender")] == "man"
    f = ln.facts("A kid is standing and he is holding a ball.", False)
    assert f[("person", "gender")] == "boy" and f[("person", "age")] == "child"         # a young age turns the pronoun's gender
    f = ln.facts("A person is walking a dog and he is wagging his tail.", False)
    assert ("person", "gender") not in f                                                  # an animal in the text: 'he' may be the dog
    f = ln.facts("A person is talking to someone and she is laughing at his joke.", False)
    assert ("person", "gender") not in f                                                  # both pronouns: no reading


def test_animal_kin_and_a_second_thing():
    f = ln.facts("There is a giraffe and a calf. The calf is drinking milk at its mother. There is grass on the ground.", False)
    assert ("person", "count") not in f                                       # the giraffe's mother is not a person
    f = ln.facts("A mother is holding her baby near a dog on the grass.", False)
    assert ("person", "count") in f                                           # 'her baby': the people stay people
    f = ln.facts("A man is leaning on this table. On the table there are glasses. At the left there is a table with trophies.", False)
    assert f.get(("thing", "name")) == "table" and ("thing", "count") not in f   # 'this table ... a table': two tables
    f = ln.facts("In the center there is an airplane. In the background there is another airplane and a building.", False)
    assert f.get(("thing", "name")) == "airplane" and ("thing", "count") not in f


def test_words_read_off_a_sign_are_not_the_picture():
    t = "There is an object in the center. On the object there is some text written as meter remains as a courtesy to cyclist please pay."
    assert ln.unwritten(t) == "There is an object in the center. On the object there is some text written."
    f = ln.facts(t, False)
    assert not any(isinstance(k, tuple) and k[0] == "person" for k in f)            # no cyclist in the picture
    f = ln.facts("A man is standing near a board. Something is written on it.", False)
    assert f[("person", "count")] == "1"                                              # 'written on it' alone takes nothing away
    t = ("There is a sign board on which it is written as ''dog run'' and there is a house at the center, there is a boy who is "
         "walking at the left side, there are trees")
    assert ln.unwritten(t).startswith("There is a sign board on which it is written and there is a house")
    assert ln.facts(t, False)[("person", "gender")] == "boy"                          # the read words end at their closing quote
    t = "A board with text written as please pay here and there is a man standing beside it."
    assert ln.facts(t, False)[("person", "gender")] == "man"                          # unquoted: they end at the next clause


def test_the_hint_agrees_with_the_chosen_facts():
    narr = ["A woman is standing on the beach and holding a surfboard.",
            "A woman holding a surfboard on the sand near the ocean.",
            "In the center of the image there is a woman who is standing on the beach. She is wearing a black dress and holding a "
            "white skateboard. In the background there is an ocean and a sky with clouds."]
    s = ln.build(4242, narr)
    assert s["spec"]["thing"]["name"] == "surfboard" and "skateboard" not in s["hint"]


def test_module_contract():
    for name in ("DATASET", "LICENSE", "URL", "ATTRIBUTION", "CITATION", "TAKEN"):
        assert isinstance(getattr(ln, name), str) and getattr(ln, name)
    assert ln.LICENSE == "CC BY 4.0" and "@inproceedings{PontTuset_eccv2020" in ln.CITATION


def test_plain_narration_drops_the_act_of_looking():
    from thought_seeds.sources.localized_narratives import plain_narration
    assert plain_narration("In this picture I can see a man and a dog. We can also see trees. In this image there is a cat.") == \
        "A man and a dog. Trees. There is a cat."
