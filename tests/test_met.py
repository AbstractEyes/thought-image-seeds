"""The Met importer on a tiny MetObjects.csv shaped like the real file (no network)."""
import csv

from thought_seeds import core
from thought_seeds.sources import met

HEADER = ("Object Number,Is Highlight,Is Timeline Work,Is Public Domain,Object ID,Gallery Number,Department,AccessionYear,Object Name,"
          "Title,Culture,Period,Dynasty,Reign,Portfolio,Constituent ID,Artist Role,Artist Prefix,Artist Display Name,Artist Display Bio,"
          "Artist Suffix,Artist Alpha Sort,Artist Nationality,Artist Begin Date,Artist End Date,Artist Gender,Artist ULAN URL,"
          "Artist Wikidata URL,Object Date,Object Begin Date,Object End Date,Medium,Dimensions,Credit Line,Geography Type,City,State,"
          "County,Country,Region,Subregion,Locale,Locus,Excavation,River,Classification,Rights and Reproduction,Link Resource,"
          "Object Wikidata URL,Metadata Date,Repository,Tags,Tags AAT URL,Tags Wikidata URL").split(",")
ROWS = [
    {"Is Public Domain": "True", "Object ID": "101", "Department": "European Paintings", "Object Name": "Painting",
     "Title": "Young Woman with a Dog", "Culture": "Dutch", "Artist Display Name": "Johannes Vermeer", "Object Date": "ca. 1665–67",
     "Object Begin Date": "1665", "Object End Date": "1667", "Medium": "Oil on canvas", "Classification": "Paintings",
     "Tags": "Women|Portraits|Dogs|Saint Agnes"},
    {"Is Public Domain": "True", "Object ID": "102", "Department": "Asian Art", "Object Name": "Bowl", "Title": "Bowl with Dragons",
     "Culture": "China", "Object Date": "1700–20", "Object Begin Date": "1700", "Object End Date": "1720",
     "Medium": "Porcelain painted in underglaze cobalt blue", "Classification": "Ceramics-Porcelain", "Tags": "Dragons"},
    {"Is Public Domain": "False", "Object ID": "103", "Department": "Modern and Contemporary Art", "Object Name": "Painting",
     "Title": "Woman", "Object Begin Date": "1950", "Object End Date": "1950", "Medium": "Oil on canvas", "Classification": "Paintings",
     "Tags": "Women"},
    {"Is Public Domain": "True", "Object ID": "104", "Department": "Asian Art", "Object Name": "Illustrated book",
     "Title": "Untitled Book of Erotica (Shunga)", "Object Begin Date": "1780", "Object End Date": "1790",
     "Medium": "Woodblock printed book", "Classification": "Illustrated Books", "Tags": "Men|Women"},
]


def _write(tmp_path):
    d = tmp_path / "met"
    d.mkdir()
    with open(d / "MetObjects.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for r in ROWS:
            w.writerow({k: r.get(k, "") for k in HEADER})
    return str(tmp_path)


def test_met_seeds(tmp_path):
    raw = _write(tmp_path)
    got = {s["seed_id"]: s for s in met.seeds(raw)}
    assert set(got) == {"met:101", "met:102"}                      # not public domain and explicit rows are out
    p = got["met:101"]
    assert p["domain"] == "painting" and p["genre"] == "portrait"
    # the title's 'young' gives no age: no count says the woman is the only figure (core.cohere)
    assert p["spec"] == {"person": {"gender": "woman"}, "thing": {"name": "dog"},
                         "form": {"medium": "oil painting", "period": "baroque"}}
    assert "Vermeer" not in p["hint"] and "Agnes" not in p["hint"] and "Johannes" not in p["hint"]
    assert "Made ca. 1665-67." in p["hint"] and "Culture: Dutch." in p["hint"] and '"young woman with a dog"' in p["hint"]
    assert p["source"] == {"dataset": "met", "id": "101", "license": "CC0 1.0",
                           "url": "https://www.metmuseum.org/art/collection/search/101"}
    b = got["met:102"]
    assert b["domain"] == "design" and b["genre"] == "bowl"
    assert b["spec"] == {"thing": {"name": "bowl"}, "form": {"palette": "blue and white"}}   # no European era for a Chinese bowl
    assert "Subjects: dragons." in b["hint"]
    for s in got.values():
        assert core.check_spec(s["spec"]) == [] and s["held"] is False


def test_met_helpers():
    assert met.title_ok("Portrait of a Man") == "portrait of a man"
    assert met.title_ok("Portrait of Rose") is None                 # a given name that is also a word
    assert met.title_ok("Denis Diderot (1713–1784)") is None
    assert met.medium_of("Pottery fragment with ink inscription") is None
    assert met.medium_of("Albumen silver print from glass negative") == "silver print"
    assert met.medium_of("Engraving; printed in black ink") is None                  # an intaglio print: no list value, not ink
    assert met.medium_of("Etching and drypoint") == "etching" and met.medium_of("Woodcut") == "woodcut"
    assert met.medium_of("Wood engraving") is None and met.medium_blocked("Wood engraving")      # not a woodcut
    assert met.medium_blocked("Engraving; printed in black ink") and not met.medium_blocked("Red chalk")
    assert met.medium_of("One of a set of two woodblock-printed books; ink and color on paper") == "woodcut"
    assert met.object_noun("Kylix fragment") == ("kylix", "fragment")
    assert met.culture_ok("probably French, Paris") == "French" and met.culture_ok("Sasanian") is None


def test_a_date_mark_stays_in_the_hint():
    row = {k: "" for k in met.COLS}
    row.update({"Object ID": "105", "Is Public Domain": "True", "Department": "Greek and Roman Art", "Object Name": "Kylix",
                "Title": "Kylix", "Culture": "Greek, Attic", "Object Date": "ca. 480 BCE", "Object Begin Date": "-490",
                "Object End Date": "-470", "Medium": "Terracotta", "Classification": "Vases"})
    seed = met.build(row)
    assert "Made ca. 480 BCE." in seed["hint"] and "Culture: Greek." in seed["hint"]
    assert seed["spec"] == {"thing": {"name": "kylix"}, "form": {"medium": "clay", "period": "ancient"}}
