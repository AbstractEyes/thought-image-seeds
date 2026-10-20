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


def _spec(description):
    s, genre, hint = docci.spec_of(description)
    return s.spec(), hint


def test_hints_keep_no_name_opener_or_saint_fragment():
    _s, hint = _spec("A close-up view of a statue of Einstein sitting on a bench. Einstein's left arm rests on the bench. The bench "
                     "is gray.")
    assert hint == "The bench is gray."
    _s, hint = _spec("A front view of a stone statue of a monk. A plaque below it reads St. Francis. The statue stands in a garden.")
    assert hint == "A front view of a stone statue of a monk. The statue stands in a garden."
    _s, hint = _spec("An outdoor view of a gray stone wall. The wall is in Jackson Square in St. Louis. Ivy grows on the wall.")
    assert "Louis" not in hint and "St." not in hint
    _s, hint = _spec("The image shows a red barn in a field. In this image, the barn has a white door. The pixels of the sky are "
                     "blue.")
    assert hint == "A red barn in a field. The barn has a white door."               # no image talk, no pixels


def test_a_position_comes_only_from_a_sentence_that_places_the_thing():
    assert "position" not in _spec("A close-up view of a red apple on a wooden table. A knife is on the left side of the image.")[0][
        "thing"]                                                                       # the knife is placed, not the apple
    assert "position" not in _spec("A top-down view of a black dog lying on a rug, its head pointing towards the lower left "
                                   "corner of the image.")[0]["thing"]                # a direction places nothing
    assert _spec("A close-up view of a red star painted on a wall. The red star is on the left side of the image.")[0]["thing"][
        "position"] == "left"


def test_the_subject_is_a_noun():
    for d, name in (("An outdoor view of an older red brick building with white windows.", "building"),
                    ("A close-up view of a sign that says stop on a pole.", "sign"),
                    ("A close-up view of a bagel cut in half on a plate.", "bagel"),
                    ("A view at dusk of a tall courthouse with a clock tower.", "courthouse"),
                    ("An indoor top-down view captures a white cat with black patches on a wooden floor.", "cat"),
                    ("An outdoor high angled shot of a congested asphalt intersection besides an overpass.", "intersection"),
                    ("A close up view of a hand blown glass mug that is upside down.", "glass mug")):
        assert _spec(d)[0].get("thing", {}).get("name") == name, d
    assert "thing" not in _spec("A side view of a black mini cooper parked on a street.")[0]          # a brand is no noun
    assert _spec("A view at dusk of a tall courthouse with a clock tower.")[0]["scene"] == {"time": "dusk"}


def test_a_likeness_is_no_person():
    for d in ("A front view of two large nutcracker soldiers standing beside a door.",
              "A front view of a cardboard cutout of a person standing in a store.",
              "A close-up view of a white stone man sitting on a pedestal."):
        assert "person" not in _spec(d)[0], d


def test_weather_only_of_the_air_and_colours_only_of_the_whole_thing():
    for d in ("A close-up view of a car with foggy headlights on a street.",
              "A view of a small christmas tree covered in fake snow on a table.",
              "A close-up view of a fan with mist coming from the fan. The fan is white."):
        assert "weather" not in _spec(d)[0].get("scene", {}), d
    assert _spec("A wide view of a lake on a foggy morning. The sky is foggy.")[0]["scene"]["weather"] == "fog"
    for d in ("A close-up view of a wine cork on a table.", "A close-up view of an ice cream cone on a napkin.",
              "An outdoor view of a sand volleyball court on a beach."):
        assert "colour" not in _spec(d)[0]["thing"], d


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
    assert len(list(docci.seeds(str(tmp_path), limit=2))) == 2 and list(docci.seeds(str(tmp_path), limit=0)) == []
    assert len(list(docci.seeds(str(tmp_path), limit=None))) == 3


def test_module_contract():
    for name in ("DATASET", "LICENSE", "URL", "ATTRIBUTION", "CITATION", "TAKEN"):
        assert getattr(docci, name)
    assert docci.LICENSE == "CC BY 4.0" and "@inproceedings{OnoeDocci2024" in docci.CITATION


def test_a_noun_introduced_twice_has_no_count():
    s, _genre, _hint = docci.spec_of("An indoor view of a black and white cat and a dark gray cat on light wooden stairs. The black "
                                     "and white cat is sitting facing the front.")
    assert s.d["thing"]["name"] == "cat" and "count" not in s.d["thing"]
    s, _genre, _hint = docci.spec_of("An indoor view of a black and white cat on light wooden stairs. The cat is sitting.")
    assert s.d["thing"]["count"] == "1"
    assert docci.said_again("cat", "a cat sits beside another cat") and docci.said_again("cat", "two gray cats on a step")
    assert not docci.said_again("cat", "a cat's tail and the cat's paw")
