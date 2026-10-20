"""The Cleveland Museum of Art importer on a tiny data.csv shaped like the real file (no network)."""
import csv

from thought_seeds import core
from thought_seeds.sources import cleveland

COLS = ("id,accession_number,share_license_status,tombstone,current_location,title,title_in_original_language,series,"
        "series_in_original_language,creation_date,creation_date_earliest,creation_date_latest,artists_tags,culture,technique,"
        "support_materials,department,collection,type,measurements,state_of_the_work,edition_of_the_work,copyright,inscriptions,"
        "exhibitions,provenance,find_spot,related_works,former_accession_numbers,did_you_know,early_education_description,"
        "artlens_description,description,external_resources,citations,catalogue_raisonne,url,alternate_images,creditline,"
        "image_credit,sketchfab_id,sketchfab_url,gallery_donor_text,creators,image_web,image_print,image_full,updated_at").split(",")
ROWS = [
    {"id": "11", "accession_number": "1916.1", "share_license_status": "CC0", "title": "Young Woman Reading", "creation_date": "c. 1880",
     "creation_date_earliest": "1878", "creation_date_latest": "1882", "culture": "France, 19th century", "technique": "oil on canvas",
     "department": "European Painting and Sculpture", "type": "Painting", "creators": "Jean Dupont (French, 1840-1900), artist",
     "description": "<p>Dupont painted his sister often. A young woman sits by a window with an open book. "
                    "The light falls from the left.</p>",
     "did_you_know": "Dupont studied in Paris."},
    {"id": "12", "accession_number": "1919.263", "share_license_status": "CC0", "title": "Sword Guard", "creation_date": "1850s",
     "creation_date_earliest": "1850", "creation_date_latest": "1859", "culture": "Japan, Edo period (1615–1868)",
     "technique": "iron", "department": "Japanese Art", "type": "Arms and Armor"},
    {"id": "13", "accession_number": "1950.1", "share_license_status": "Copyrighted", "title": "Woman", "type": "Painting",
     "technique": "oil on canvas", "creation_date_earliest": "1950", "creation_date_latest": "1950"},
    {"id": "14", "accession_number": "1960.1", "share_license_status": "CC0", "title": "Book", "type": "Bound Volume",
     "technique": "ink on paper", "creation_date_earliest": "1500", "creation_date_latest": "1500"},
]


def test_cleveland_seeds(tmp_path):
    d = tmp_path / "cleveland"
    d.mkdir()
    with open(d / "data.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in ROWS:
            w.writerow({k: r.get(k, "") for k in COLS})
    got = {s["seed_id"]: s for s in cleveland.seeds(str(tmp_path))}
    assert set(got) == {"cleveland:11", "cleveland:12"}             # copyrighted and bound-volume rows are out
    p = got["cleveland:11"]
    assert p["domain"] == "painting" and p["genre"] == "painting"
    assert p["spec"] == {"person": {"gender": "woman", "role": "reader"},           # no age without a count of one (core.cohere)
                         "form": {"medium": "oil painting", "period": "19th century"}}
    assert "Dupont" not in p["hint"] and "Paris" not in p["hint"]
    assert p["hint"].startswith("A young woman sits by a window with an open book. The light falls from the left.")
    assert "Culture: France." in p["hint"] and p["source"]["url"] == "https://clevelandart.org/art/1916.1"
    g = got["cleveland:12"]
    assert g["domain"] == "design" and g["genre"] == "sword guard"
    assert g["spec"] == {"thing": {"name": "sword guard"}, "form": {"period": "19th century"}}   # no 'guard' role
    for s in got.values():
        assert core.check_spec(s["spec"]) == [] and s["source"]["license"] == "CC0 1.0"


def _r(**kw):
    r = {k: "" for k in COLS}
    r.update({"id": "21", "accession_number": "1921.1", "share_license_status": "CC0", "title": "Bowl", "type": "Ceramic",
              "creation_date_earliest": "1850", "creation_date_latest": "1860", "technique": "porcelain", "culture": "France",
              "department": "Decorative Art and Design",
              "description": "A round bowl with a wide rim and a low foot, glazed in a pale tone and painted with plain bands."})
    r.update(kw)
    return r


def test_a_row_of_one_part_of_an_object_is_left_out():
    for title in ("Teapot (lid)", "Koto (plectrum)", "Inkwell (top to bottle)", "Table (marble top)", "Ewer (stand)"):
        assert cleveland.PART.search(title) and cleveland.build(_r(title=title), set()) is None, title
    assert cleveland.build(_r(title="Covered Box (Kogo)"), set()) is not None        # a bracket that names no part


def test_object_names_cut_at_of_and_armour_parts():
    names = {t: (cleveland.build(_r(title=t, type=ty), set(t.lower().replace("(", " ").replace(")", " ").split())) or {})
             .get("spec", {}).get("thing", {}).get("name") for t, ty in
             (("One of a pair of shawls (Lamba Landy Fotsy)", "Textile"), ("Chest of Drawers (Commode)", "Furniture"),
              ("Proper Right Arm (Vambrace, Rerebrace and Couter)", "Arms and Armor"))}
    assert names["One of a pair of shawls (Lamba Landy Fotsy)"] == "shawl"
    assert names["Chest of Drawers (Commode)"] == "chest of drawers"
    assert names["Proper Right Arm (Vambrace, Rerebrace and Couter)"] not in ("proper right arm", "arm")


def test_the_hint_drops_the_artist_image_talk_and_the_file():
    desc = ("Church's considerable technical skills made him famous. This image depicts the falls at dawn. A high resolution scan "
            "of the sheet is online. In this image, a man and a woman sit facing one another. The falls roar below a rainbow.")
    r = _r(title="Niagara", type="Painting", technique="oil on canvas", department="American Painting and Sculpture",
           culture="America", creators="Frederic Edwin Church (American, 1826-1900), artist", description=desc)
    vocab = core.corpus_vocab([desc, "the church on a hill. the church bells."])
    h = cleveland.build(r, vocab)["hint"]
    assert h.startswith("The falls at dawn. A man and a woman sit facing one another. The falls roar below a rainbow.")
    assert "Church" not in h and "image" not in h.lower() and "resolution" not in h


def test_mediums_eras_and_the_verso():
    assert "medium" not in (cleveland.build(_r(technique="wood engraving"), set())["spec"].get("form", {}))   # not a woodcut
    assert "medium" not in (cleveland.build(_r(technique="oil and tempera (?) on panel"), set())["spec"].get("form", {}))
    for culture, dept in (("Peru, Nasca", "Art of the Americas"), ("Ancestral Pueblo", "Art of the Americas"),
                          ("Honduras, Ulua Valley", "Art of the Americas")):
        r = _r(culture=culture, department=dept, **{"creation_date_earliest": "1100", "creation_date_latest": "1200"})
        assert "period" not in cleveland.build(r, set())["spec"].get("form", {}), culture
    sheet = _r(title="Mother and Child (recto); Profile Bust of a Man (verso)", type="Drawing", technique="black chalk",
               department="Drawings")
    spec = cleveland.build(sheet, set())["spec"]
    assert spec.get("person", {}).get("gender") != "man"            # the verso's figure is not the recto's
    plate = _r(title="Plate with a Woman Walking in a Garden", type="Ceramic")
    assert set(cleveland.build(plate, set(plate["title"].lower().split()))["spec"]) <= {"thing", "form"}


def test_limit_none_is_all_and_zero_is_none(tmp_path):
    d = tmp_path / "cleveland"
    d.mkdir()
    with open(d / "data.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for r in ROWS:
            w.writerow({k: r.get(k, "") for k in COLS})
    assert len(list(cleveland.seeds(str(tmp_path), limit=None))) == 2 and list(cleveland.seeds(str(tmp_path), limit=0)) == []
    assert len(list(cleveland.seeds(str(tmp_path), limit=1))) == 1


def test_period_european_eras_only_for_the_european_tradition():
    r = {k: "" for k in COLS}
    r.update({"id": "15", "accession_number": "1920.1", "share_license_status": "CC0", "title": "Bowl", "type": "Ceramic",
              "creation_date_earliest": "1650", "creation_date_latest": "1680", "technique": "porcelain",
              "description": "A round bowl with a wide rim and a low foot, glazed in a pale tone and painted with plain bands."})
    western = cleveland.build(dict(r, culture="France, 17th century", department="Decorative Art and Design"), set())
    japanese = cleveland.build(dict(r, culture="Japan, Edo period", department="Japanese Art"), set())
    assert western["spec"]["form"] == {"period": "baroque"} and "form" not in japanese["spec"]
