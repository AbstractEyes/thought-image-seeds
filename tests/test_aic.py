"""The Art Institute of Chicago importer on a tiny batch shaped like the search API's JSON (no network)."""
import json

from thought_seeds import core
from thought_seeds.sources import aic

BATCH = {"pagination": {"total": 3, "limit": 100, "offset": 0, "total_pages": 1, "current_page": 1}, "data": [
    {"id": 7001, "title": "Paris Street; Rainy Day", "date_start": 1877, "date_end": 1877,
     "medium_display": "Oil on canvas", "artwork_type_title": "Painting", "classification_title": "oil on canvas",
     "classification_titles": ["oil on canvas", "painting", "european painting"], "style_title": "Impressionism",
     "style_titles": ["Impressionism", "19th century"],
     "subject_titles": ["cityscapes", "umbrellas", "rain", "men", "France", "blue (color)", "Gustave Caillebotte"],
     "material_titles": ["oil paint (paint)", "canvas"], "technique_titles": ["oil painting"], "theme_titles": ["Essentials"],
     "color": {"h": 30, "l": 30, "s": 40, "percentage": 0.05, "population": 300},
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
    assert aic.hsl_name({"h": 220, "s": 60, "l": 50}) == "blue" and aic.hsl_name({"h": 0, "s": 0, "l": 5}) == "black"
    assert aic.palette(["yellow", "green"], "blue") == "yellow and blue"        # 'yellow and green' is over the budget
    assert aic.palette(["red"], None) is None


def test_an_engraving_takes_no_medium_from_its_ink():
    a = {"id": 7004, "title": "Untitled", "date_start": 1520, "date_end": 1520, "medium_display": "Engraving in black on ivory laid paper",
         "artwork_type_title": "Print", "classification_titles": ["print"], "subject_titles": ["horses"], "technique_titles": [],
         "material_titles": ["paper (fiber product)", "ink"], "color": None, "description": None, "is_public_domain": True,
         "place_of_origin": "Germany"}
    seed = aic.build(a, set())
    assert seed["spec"] == {"thing": {"name": "horse"}, "form": {"period": "renaissance"}} and seed["domain"] == "illustration"
