"""The DOCCI importer on a tiny inline fixture shaped like docci_descriptions.jsonlines (no network)."""
import json

from thought_seeds import core
from thought_seeds.sources import docci

ROWS = [
    {"example_id": "train_00001", "split": "train", "image_file": "train_00001.jpg",
     "description": "An overhead view of two brown ducks swimming in a pond. The ducks are on the left side of the image. Behind the "
                    "ducks is a wooden fence. The sky is overcast. A sign that reads \"PARK\" is next to the fence. The photo was "
                    "taken by John Smith in Austin."},
    {"example_id": "train_00002", "split": "train", "image_file": "train_00002.jpg",
     "description": "A medium shot of a young girl wearing a red dress and a straw hat standing on a beach. The girl is smiling."},
    {"example_id": "train_00003", "split": "train", "image_file": "train_00003.jpg",
     "description": "A close-up view of a stone statue of a man holding a sword. The statue is in the center of the image."},
    {"example_id": "train_00004", "split": "train", "image_file": "train_00004.jpg", "description": "A nude figure on a bed."},
]


def test_ducks_spec_and_hint():
    s, genre, hint = docci.spec_of(ROWS[0]["description"])
    spec = s.spec()
    assert spec["thing"] == {"name": "ducks", "count": "2", "colour": "brown", "position": "left"}   # no living state for two
    assert spec["shot"] == {"angle": "overhead"} and spec["scene"] == {"weather": "overcast"}
    assert spec["relation"] == [{"a": "wooden fence", "rel": "behind", "b": "ducks"}]
    assert spec["form"] == {"medium": "photograph"} and genre == "wildlife"
    assert "Smith" not in hint and "PARK" not in hint and '"' not in hint                 # names and quoted text dropped
    assert hint.startswith("An overhead view of two brown ducks") and len(hint) <= core.HINT_MAX
    assert core.check_spec(spec) == []


def test_person_subject():
    s, _genre, _hint = docci.spec_of(ROWS[1]["description"])
    spec = s.spec()
    assert spec["person"] == {"count": "1", "gender": "girl", "age": "child"}
    assert spec["wear"] == {"clothing": "dress", "colour": "red", "accessory": "hat"}
    assert spec["scene"] == {"setting": "beach"} and spec["shot"] == {"framing": "medium shot"}


def test_statue_is_a_thing_not_a_person():
    s, genre, _hint = docci.spec_of(ROWS[2]["description"])
    spec = s.spec()
    assert "person" not in spec and spec["thing"] == {"name": "stone statue", "count": "1", "position": "centre"}
    assert genre == "still life"


def test_noun_phrases():
    np = docci.parse_np(docci._tokens("real sized stuffed dog with white fur"))
    assert np["name"] == "stuffed dog" and np["made"]
    assert docci.parse_np(docci._tokens("white Harlequin cat next to a fountain"))["name"] == "cat"     # the brand word left out
    np = docci.parse_np(docci._tokens("metal dish drying rack"))      # the phrase runs through 'drying' to its noun
    assert np["head"] == "rack" and np["made"] and np["name"] == "rack"  # (a material word is kept only beside the noun)
    assert docci.parse_np(docci._tokens("partially visible one")) is None
    assert docci.parse_np(docci._tokens("high rise building filled with windows"))["name"] == "building"
    assert docci.counted_np(docci._tokens("a large number of black ants"))[0] == "many"
    assert docci.counted_np(docci._tokens("a piece of fish"))[0] is None


def test_time_words_and_plural_roles():
    s, _genre, _hint = docci.spec_of("A wide shot of a red barn in a field at sunset. The sky is clear.")
    assert s.spec()["scene"] == {"time": "dusk", "weather": "clear"}
    assert docci.PERSON_NOUNS["cyclists"][2] == "rider" and docci.PERSON_NOUNS["swimmers"][2] == "swimmer"


def test_colour_compounds():
    assert docci.parse_np(docci._tokens("cream-colored labradoodle"))["colours"] == ["cream"]
    assert docci.parse_np(docci._tokens("all-black electric bike"))["colours"] == ["black"]
    assert docci.parse_np(docci._tokens("light-brown horse"))["colours"] == ["light brown"]
    assert docci.parse_np(docci._tokens("yellow-crowned night heron"))["colours"] == []          # a part's colour


def test_seeds_from_a_file(tmp_path):
    d = tmp_path / "docci"
    d.mkdir()
    (d / docci.FILE).write_text("\n".join(json.dumps(r) for r in ROWS) + "\n", encoding="utf-8")
    out = list(docci.seeds(str(tmp_path)))
    assert [s["seed_id"] for s in out] == ["docci:train_00001", "docci:train_00002", "docci:train_00003"]
    assert docci.STATS["skip: explicit word"] == 1
    for seed in out:
        assert set(seed) == {"seed_id", "domain", "genre", "spec", "hint", "source", "held"}
        assert seed["source"] == {"dataset": "docci", "id": seed["seed_id"].split(":", 1)[1], "license": "CC BY 4.0",
                                  "url": docci.URL}
        assert core.check_spec(seed["spec"]) == [] and not (core.sealed(seed["spec"]) and not seed["held"])
    assert len(list(docci.seeds(str(tmp_path), limit=2))) == 2


def test_module_contract():
    for name in ("DATASET", "LICENSE", "URL", "ATTRIBUTION", "CITATION", "TAKEN"):
        assert getattr(docci, name)
    assert docci.LICENSE == "CC BY 4.0" and "@inproceedings{OnoeDocci2024" in docci.CITATION
