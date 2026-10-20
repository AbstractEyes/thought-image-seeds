"""The Art Institute of Chicago importer on a tiny batch shaped like the search API's JSON (no network)."""
import json
import re

from thought_seeds import core
from thought_seeds.sources import aic

BATCH = {"pagination": {"total": 3, "limit": 100, "offset": 0, "total_pages": 1, "current_page": 1}, "data": [
    {"id": 7001, "title": "Paris Street; Rainy Day", "date_start": 1877, "date_end": 1877,
     "medium_display": "Oil on canvas", "artwork_type_title": "Painting", "classification_title": "oil on canvas",
     "classification_titles": ["oil on canvas", "painting", "european painting"], "style_title": "Impressionism",
     "style_titles": ["Impressionism", "19th century"],
     "subject_titles": ["cityscapes", "umbrellas", "rain", "men", "France", "blue (color)", "Gustave Caillebotte"],
     "material_titles": ["oil paint (paint)", "canvas"], "technique_titles": ["oil painting"], "theme_titles": ["Essentials"],
     "color": {"h": 30, "l": 30, "s": 40, "percentage": 3.5, "population": 300},
     "description": "<p>Caillebotte captured a busy intersection of Paris. A man and a woman walk under one umbrella on the wet "
                    "cobblestones. J. M. W. Turner admired the street. Gray light fills the wide square.</p>",
     "is_public_domain": True, "place_of_origin": "Paris"},
    {"id": 7002, "title": "Bowl", "date_start": 1700, "date_end": 1720, "medium_display": "Silver",
     "artwork_type_title": "Vessel", "classification_titles": ["vessel", "bowl"], "style_title": None, "style_titles": [],
     "subject_titles": ["flowers"], "material_titles": ["silver"], "technique_titles": [], "theme_titles": [], "color": None,
     "description": None, "is_public_domain": True, "place_of_origin": "England"},
    {"id": 7003, "title": "Untitled", "date_start": 1900, "date_end": 1900, "medium_display": "Oil on canvas",
     "artwork_type_title": "Painting", "classification_titles": ["painting"], "subject_titles": [], "color": None,
     "description": "<p>A study.</p>", "is_public_domain": False},
]}


def test_aic_seeds(tmp_path):
    d = tmp_path / "aic"
    d.mkdir()
    (d / "batch-0001.json").write_text(json.dumps(BATCH), encoding="utf-8")
    got = {s["seed_id"]: s for s in aic.seeds(str(tmp_path))}
    assert set(got) == {"aic:7001", "aic:7002"}                     # the work that is not public domain is out
    p = got["aic:7001"]
    assert p["domain"] == "painting" and p["genre"] == "cityscape"
    assert p["spec"] == {"person": {"gender": "man"}, "scene": {"weather": "rain"}, "thing": {"name": "umbrella"},
                         "form": {"medium": "oil painting", "style": "impressionism", "palette": "blue and brown",
                                  "period": "19th century"}}
    assert "Caillebotte" not in p["hint"] and "Turner" not in p["hint"] and "Paris" not in p["hint"]
    assert p["hint"].startswith("A man and a woman walk under one umbrella on the wet cobblestones.")
    assert p["source"]["license"] == "CC BY 4.0"                      # the hint carries description text
    b = got["aic:7002"]
    assert b["domain"] == "design" and b["genre"] == "bowl"
    assert b["spec"] == {"thing": {"name": "bowl", "colour": "silver"}, "form": {"period": "baroque"}}
    assert b["source"]["license"] == "CC0 1.0"                         # no description: the record data alone, CC0
    for s in got.values():
        assert core.check_spec(s["spec"]) == []


def test_aic_helpers():
    assert aic.style_of(["Post-Impressionism"]) is None and aic.style_of(["Neo-Impressionism"]) == "pointillism"
    assert aic.style_of(["Impressionism"]) == "impressionism"
    assert aic.hsl_name({"h": 220, "s": 60, "l": 50, "percentage": 10}) == "blue"
    assert aic.hsl_name({"h": 0, "s": 0, "l": 5, "percentage": 4}) == "black"
    assert aic.palette(["yellow", "green"], "blue") == "yellow and blue"        # 'yellow and green' is over the budget
    assert aic.palette(["red"], None) is None


def _art(**kw):
    a = {"id": 7100, "title": "Untitled", "date_start": 1880, "date_end": 1880, "medium_display": "Oil on canvas",
         "artwork_type_title": "Painting", "classification_titles": ["painting"], "style_titles": [], "subject_titles": ["horses"],
         "material_titles": [], "technique_titles": [], "theme_titles": [], "color": None, "description": None,
         "is_public_domain": True, "place_of_origin": "France"}
    a.update(kw)
    return a


def test_description_hints_keep_no_name_fragment_or_image_talk():
    desc = ("<p>Gabriel Salmon cut the block in 1528. Salmon emphasized the violent action of the scene. In this image, a demigod "
            "wrestles a lion beneath a tree. A stamnos (pl. stamnoi) stands at the right. This image is one of a set. The print "
            "bears an ad monogram.</p>")
    seed = aic.build(_art(description=desc, subject_titles=["lions", "trees"]), core.corpus_vocab(["the lion and the tree"]))
    assert "Salmon" not in seed["hint"] and "monogram" not in seed["hint"] and "image" not in seed["hint"].lower()
    assert seed["hint"].startswith("A demigod wrestles a lion beneath a tree. A stamnos (pl. stamnoi) stands at the right.")


def test_a_speck_of_computed_colour_is_no_palette():
    assert aic.hsl_name({"h": 220, "s": 60, "l": 50, "percentage": 0.02}) is None          # 0.02 percent of the picture
    speck = aic.build(_art(subject_titles=["red (color)"], color={"h": 220, "s": 60, "l": 50, "percentage": 0.5}), set())
    wide = aic.build(_art(subject_titles=["red (color)"], color={"h": 220, "s": 60, "l": 50, "percentage": 4}), set())
    assert "palette" not in speck["spec"].get("form", {}) and wide["spec"]["form"]["palette"] == "red and blue"


def test_european_eras_follow_the_styles_and_the_place():
    gothic = aic.build(_art(date_start=1490, date_end=1500, style_titles=["Medieval"]), set())
    americas = aic.build(_art(date_start=1500, date_end=1520, place_of_origin="Mexico", classification_titles=["painting",
                                                                                                              "art of the americas"]), set())
    plain = aic.build(_art(date_start=1500, date_end=1520), set())
    assert "period" not in gothic["spec"]["form"] and "period" not in americas["spec"]["form"]
    assert plain["spec"]["form"]["period"] == "renaissance"


def test_a_design_title_names_an_object_or_nothing():
    def thing(title, cls, kind="Textile"):
        a = _art(title=title, artwork_type_title=kind, classification_titles=cls, medium_display="Wool and silk", date_start=1500,
                 date_end=1510, subject_titles=["red (color)", "blue (color)"])
        vocab = set(re.findall(r"[a-z]+", title.lower()))                # every title word a plain word: the title is read
        return aic.build(a, vocab)["spec"].get("thing", {}).get("name")
    tapestry = ["weaving - tapestry", "textile"]
    assert thing("The Stag Hunt, from Pastoral Hunting Scenes", tapestry) == "textile"          # the scene is not the object
    assert thing("A Falconer with Two Ladies and a Foot Soldier", tapestry) == "textile"
    assert thing("The Lovers", ["weaving - tapestry", "tapestry", "textile"]) == "tapestry"
    vessel = ["vessel", "ceramics", "ancient art"]
    assert thing("Column-Krater (Mixing Bowl)", vessel, "Vessel") == "column-krater"
    assert thing("Mug", vessel, "Vessel") == "mug" and thing("Dish Decorated with a Floral Pattern", vessel, "Vessel") == "dish"
    assert aic.object_title("incense burner", []) and not aic.object_title("recumbent stag", [])


def test_a_design_object_takes_no_figure_or_scene_from_its_decoration():
    a = _art(title="Plate", artwork_type_title="Ceramics", classification_titles=["plate", "ceramics"], medium_display="Porcelain",
             subject_titles=["men", "horses", "gardens", "walking", "blue (color)", "white (color)"], date_start=1760, date_end=1770)
    seed = aic.build(a, set())
    assert set(seed["spec"]) <= {"thing", "form"} and seed["spec"]["thing"]["name"] == "plate"
    assert seed["spec"]["form"]["palette"] == "blue and white" and "Subjects: men, horses, gardens" in seed["hint"]


def test_gender_and_medium_from_the_catalogue():
    reclining = aic.build(_art(title="Reclining Woman", subject_titles=["girls"]), set())
    assert reclining["spec"].get("person", {}).get("gender") != "girl"                       # a woman is never made a girl
    assert aic.build(_art(medium_display="Oil and tempera on panel"), set())["spec"].get("form", {}).get("medium") is None
    assert aic.build(_art(medium_display="Opaque watercolor on paper", artwork_type_title="Drawing and Watercolor"),
                     set())["spec"]["form"]["medium"] == "gouache"
    touches = _art(medium_display="Transparent watercolor with touches of opaque watercolor", artwork_type_title="Drawing and Watercolor")
    assert aic.build(touches, set())["spec"]["form"]["medium"] == "watercolour"


def test_limit_none_is_all_and_zero_is_none(tmp_path):
    d = tmp_path / "aic"
    d.mkdir()
    (d / "batch-0001.json").write_text(json.dumps(BATCH), encoding="utf-8")
    assert len(list(aic.seeds(str(tmp_path), limit=None))) == 2 and list(aic.seeds(str(tmp_path), limit=0)) == []
    assert len(list(aic.seeds(str(tmp_path), limit=1))) == 1


def test_an_engraving_takes_no_medium_from_its_ink():
    a = {"id": 7004, "title": "Untitled", "date_start": 1520, "date_end": 1520, "medium_display": "Engraving in black on ivory laid paper",
         "artwork_type_title": "Print", "classification_titles": ["print"], "subject_titles": ["horses"], "technique_titles": [],
         "material_titles": ["paper (fiber product)", "ink"], "color": None, "description": None, "is_public_domain": True,
         "place_of_origin": "Germany"}
    seed = aic.build(a, set())
    assert seed["spec"] == {"thing": {"name": "horse"}, "form": {"period": "renaissance"}} and seed["domain"] == "illustration"
