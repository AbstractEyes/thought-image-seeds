"""The Parti importer and the shared prompt parser on a tiny PartiPrompts.tsv-shaped fixture (no network)."""
import json
import os

from thought_seeds import core
from thought_seeds.sources import parti

HEAD = "Prompt\tCategory\tChallenge\tNote\n"
ROWS = ["a red car to the left of two dogs\tVehicles\tProperties & Positioning\t\n",
        "A photo of an old man wearing a blue coat, sitting on a bench at night.\tPeople\tFine-grained Detail\t\n",
        "a painting of a cat in the style of Picasso\tArts\tStyle & Format\t\n",
        "a marina without any boats in it\tOutdoor Scenes\tLinguistic Structures\t\n",
        "bond\tAbstract\tBasic\tBiology-inspired concepts with multiple meanings\n",
        "four wine bottles\tArtifacts\tQuantity\t\n"]
NAMED = ["a statue of Abraham Lincoln wearing a shiny astronaut's helmet. The statue sits on the moon.\tPeople\tBasic\t\n",
         "a portrait of Napoleon riding a horse\tPeople\tBasic\t\n",
         "an oil painting of a dog in the style of Rembrandt\tArts\tStyle & Format\t\n",
         "a sport car melting into a clock, surrealist painting in the style of Salvador Dali\tArts\tStyle & Format\t\n",
         "a horse in a field, by Hokusai\tArts\tStyle & Format\t\n",
         "Gandalf saying you shall not pass\tPeople\tBasic\t\n",
         "a photograph of a blue porsche 356 coming around a bend in the road\tVehicles\tBasic\t\n",
         "A gundam stands tall with its sword raised. A dark moon is in the sky.\tIllustrations\tBasic\t\n",
         "three red lego blocks next to a cat\tArtifacts\tQuantity\t\n",
         "A high resolution photo of a rat working out in a gym.\tAnimals\tBasic\t\n"]


def _seeds(tmp_path, rows=ROWS, name="t"):
    raw = os.path.join(str(tmp_path), name)
    d = os.path.join(raw, "parti")
    os.makedirs(d)
    with open(os.path.join(d, "PartiPrompts.tsv"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HEAD + "".join(rows))
    return {s["seed_id"]: s for s in parti.seeds(raw)}


def _id(row):
    return "parti:" + parti.seed_id(row.split("\t")[0])


def test_parti_specs(tmp_path):
    out = _seeds(tmp_path)
    assert set(out) == {_id(ROWS[i]) for i in (0, 1, 2, 3, 5)}                      # 'bond' states no fact
    a = out[_id(ROWS[0])]
    assert a["spec"] == {"thing": {"name": "car", "count": "1", "colour": "red"},
                         "relation": [{"a": "car", "rel": "left of", "b": "dog"}]}
    assert a["domain"] == "illustration" and a["genre"] == "vehicles" and a["hint"] == "a red car to the left of two dogs."
    b = out[_id(ROWS[1])]
    assert b["spec"] == {"person": {"count": "1", "gender": "man", "age": "elderly"}, "wear": {"clothing": "coat", "colour": "blue"},
                         "body": {"pose": "sitting"}, "thing": {"name": "bench", "count": "1"}, "scene": {"time": "night"},
                         "form": {"medium": "photograph"}}
    assert b["domain"] == "photograph" and b["genre"] == "people"
    c = out[_id(ROWS[2])]
    assert c["domain"] == "painting" and c["genre"] == "art" and "Picasso" not in c["hint"] and c["spec"]["thing"]["name"] == "cat"
    assert out[_id(ROWS[3])]["spec"] == {"scene": {"setting": "harbour"}}           # the boats are negated
    d = out[_id(ROWS[5])]
    assert d["spec"] == {"thing": {"name": "bottle", "count": "4"}} and d["genre"] == "objects quantity"
    for s in out.values():
        assert core.check_spec(s["spec"]) == [] and s["source"]["license"] == "Apache-2.0"
        assert s["source"]["id"] == s["seed_id"].split(":", 1)[1] and len(s["source"]["id"]) == 16


def test_a_seed_id_does_not_move_with_the_row(tmp_path):
    first = _seeds(tmp_path, ROWS, "a")
    moved = _seeds(tmp_path, [ROWS[5], "a new prompt about a dog\tAnimals\tBasic\t\n"] + ROWS[:5], "b")
    assert all(moved[k] == v for k, v in first.items())                               # the same prompt, the same seed
    assert parti.seed_id("A red car ") == parti.seed_id("a  red car")                 # spaces and case folded


def test_no_name_reaches_a_hint_or_a_record(tmp_path):
    out = _seeds(tmp_path, NAMED)
    names = ("lincoln", "abraham", "napoleon", "rembrandt", "dali", "salvador", "hokusai", "gandalf", "porsche", "gundam", "lego")
    for s in out.values():
        text = (s.get("hint", "") + " " + json.dumps(s["spec"])).lower()
        assert not any(n in text for n in names), s
    rat = [s for s in out.values() if "rat" in s.get("hint", "")]
    assert rat and rat[0]["hint"] == "A photo of a rat working out in a gym."         # no resolution words


def test_strip_names():
    assert parti.strip_names("A cat. Oil painting in the style of Vincent Van Gogh.") == "A cat. Oil painting."
    assert parti.strip_names("A cat on a sofa. The mona lisa as a cat.") == "A cat on a sofa."      # a lower-case name
    assert parti.strip_names("A DSLR photo of a VW van. A dog.") == "A dog."                       # a brand in capitals goes
    assert parti.strip_names("A DSLR photo of a red van.") == "A DSLR photo of a red van."
    assert parti.strip_names("Gandalf saying you shall not pass. A dog.") == "A dog."              # a name opening a sentence
    assert parti.strip_names("a bloody mary cocktail") == "a bloody mary cocktail"


def test_module_contract():
    for name in ("DATASET", "LICENSE", "URL", "ATTRIBUTION", "CITATION", "TAKEN"):
        assert isinstance(getattr(parti, name), str) and getattr(parti, name)
    assert parti.LICENSE == "Apache-2.0" and "@article{yu2022scaling" in parti.CITATION
