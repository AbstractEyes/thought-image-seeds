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


def _row(**kw):
    row = {k: "" for k in met.COLS}
    row.update({"Object ID": "201", "Is Public Domain": "True", "Department": "European Paintings", "Object Name": "Painting",
                "Title": "Untitled", "Object Date": "1880", "Object Begin Date": "1880", "Object End Date": "1880",
                "Medium": "Oil on canvas", "Classification": "Paintings", "Tags": "Horses"})
    row.update(kw)
    return row


def test_the_title_wins_over_the_tags_gender():
    girl = met.build(_row(Title="Reclining Woman", Tags="Girls|Horses"))
    assert girl["spec"].get("person", {}).get("gender") != "girl"          # a woman is never made a girl
    men = met.build(_row(Title="Figurine of a Female (?) Seated Personage", Tags="Men|Horses"))
    assert men["spec"].get("person", {}).get("gender") is None


def test_european_eras_only_for_european_works():
    pueblo = met.build(_row(**{"Department": "The American Wing", "Culture": "Ancestral Pueblo", "Object Name": "Bowl",
                               "Title": "Bowl", "Object Begin Date": "1100", "Object End Date": "1200", "Medium": "Earthenware",
                               "Classification": "Ceramics", "Tags": ""}))
    assert pueblo["spec"] == {"thing": {"name": "bowl"}, "form": {"medium": "clay"}}         # no 'medieval'
    aztec = met.build(_row(**{"Department": "Arts of Africa, Oceania, and the Americas", "Culture": "Mexica",
                              "Object Begin Date": "1500", "Object End Date": "1520"}))
    assert "period" not in aztec["spec"].get("form", {})


def test_a_design_objects_decoration_gives_no_figure_or_scene():
    plate = met.build(_row(**{"Department": "European Sculpture and Decorative Arts", "Object Name": "Plate", "Title": "Plate",
                              "Medium": "Hard-paste porcelain", "Classification": "Ceramics-Porcelain",
                              "Tags": "Men|Horses|Gardens|Walking"}))
    assert set(plate["spec"]) <= {"thing", "form"} and plate["spec"]["thing"] == {"name": "plate"}
    assert "Subjects: men, horses, gardens, walking." in plate["hint"]


def test_mediums_read_only_when_stated_plainly():
    for doubtful in ("Oil and tempera (?) on wood", "Woodcut (?wood engraving matrix)"):
        assert met.medium_of(doubtful) is None and met.medium_blocked(doubtful), doubtful
    assert met.medium_of("Oil and tempera on canvas") is None and met.medium_of("Tempera and oil on panel") is None
    assert met.medium_of("Opaque watercolor and gold on paper") == "gouache"
    assert met.medium_of("Watercolor and gouache") == "watercolour"


def test_a_title_gives_no_scene_from_a_noun_a_provenance_or_the_verso():
    assert met.recto("Battle Scene (recto); Two Seated Women (verso)") == "Battle Scene"
    assert met.title_ok("Study of a Man (recto); Woman Bathing (verso)") == "study of a man"
    for title in ("the morning star", "evening dress", "plaque probably from a garden shrine", "design for a garden"):
        s = core.Spec()
        met.title_records(s, title, "painting")
        assert not s.has("scene", "time") and not s.has("scene", "setting"), title
    s = core.Spec()
    met.title_records(s, "temple hanging with a woman walking in a garden", "design")    # an object's title: no record
    assert s.spec() == {}


def test_object_names():
    assert met.object_noun("one of a pair of shawls") == ("shawl", None)           # (a generic title, as title_ok gives it)
    assert met.object_noun("Chest of drawers") == ("chest of drawers", None)
    assert met.object_noun("Proper right arm", armour=True) == (None, None)          # an arm defence, not an arm
    assert met.object_noun("Six spoons") == ("spoons", None) and met.object_noun("one") == (None, None)
    assert met.object_noun("Three lengths of woven silk") == ("woven silk", None)
    assert met.object_noun("Dish decorated with a floral pattern") == ("dish", None)
    assert met.object_noun("Basin depicting a cistern, tower and domed building") == ("basin", None)
    assert met.object_noun("Hand painted wall") == ("hand painted wall", None)       # not 'hand'
    assert met.object_noun("Three leaf gaming table") == (None, None)               # a compound, over the budget: left out


def test_the_name_lists_keep_a_maker_out_of_the_hint(tmp_path):
    d = tmp_path / "met"
    d.mkdir()
    rows = [_row(**{"Object ID": "301", "Department": "European Sculpture and Decorative Arts", "Object Name": "Plaque",
                    "Title": "Plaque", "Medium": "Jasperware, wedgwood type", "Classification": "Ceramics",
                    "Artist Display Name": "Josiah Wedgwood and Sons|Thomas Bentley", "Tags": "Horses"}),
            _row(**{"Object ID": "302", "Object Name": "Drawing", "Title": "Horse", "Department": "Drawings and Prints",
                    "Medium": "Pen and ink, after bentley", "Classification": "Drawings", "Tags": "Horses"})]
    with open(d / "MetObjects.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in HEADER})
    got = {s["seed_id"]: s for s in met.seeds(str(tmp_path))}
    assert "wedgwood" not in got["met:301"]["hint"].lower()             # the row's own maker
    assert "bentley" not in got["met:302"]["hint"].lower()              # a maker of another row, in lower case
    assert list(met.seeds(str(tmp_path), limit=0)) == [] and len(list(met.seeds(str(tmp_path), limit=1))) == 1


def test_a_row_draws_by_its_own_seed_id():
    # (the Wikidata seed of a work the Met holds routes with the Met seed's id, so both draw alike; the row keeps its own draw)
    held = next(str(i) for i in range(400, 3000) if core.held_pick(f"met:{i}"))
    kept = next(str(i) for i in range(400, 3000) if not core.held_pick(f"met:{i}"))
    for oid, want in ((held, True), (kept, False)):                       # the sealed pose: the seed's own draw decides
        row = _row(**{"Object ID": oid, "Tags": "Men|Walking", "Object Wikidata URL": "https://www.wikidata.org/wiki/Q42"})
        assert met.build(row)["held"] is want, oid


def test_a_date_mark_stays_in_the_hint():
    row = {k: "" for k in met.COLS}
    row.update({"Object ID": "105", "Is Public Domain": "True", "Department": "Greek and Roman Art", "Object Name": "Kylix",
                "Title": "Kylix", "Culture": "Greek, Attic", "Object Date": "ca. 480 BCE", "Object Begin Date": "-490",
                "Object End Date": "-470", "Medium": "Terracotta", "Classification": "Vases"})
    seed = met.build(row)
    assert "Made ca. 480 BCE." in seed["hint"] and "Culture: Greek." in seed["hint"]
    assert seed["spec"] == {"thing": {"name": "kylix"}, "form": {"medium": "clay", "period": "ancient"}}
