"""The National Gallery of Art importer on tiny CSVs shaped like the open-data files (no network)."""
import csv

from thought_seeds import core
from thought_seeds.sources import nga

OBJ_COLS = ("objectid,uuid,accessioned,accessionnum,locationid,title,displaydate,beginyear,endyear,visualbrowsertimespan,medium,"
            "dimensions,inscription,markings,attributioninverted,attribution,provenancetext,creditline,classification,"
            "subclassification,visualbrowserclassification,parentid,isvirtual,departmentabbr,portfolio,series,volume,watermarks,"
            "lastdetectedmodification,wikidataid,customprinturl").split(",")
TERM_COLS = ["termid", "objectid", "termtype", "term", "visualbrowsertheme", "visualbrowserstyle"]
IMG_COLS = ["uuid", "iiifurl", "iiifthumburl", "viewtype", "sequence", "width", "height", "maxpixels", "openaccess", "created",
            "modified", "depictstmsobjectid", "assistivetext"]
OBJECTS = [
    {"objectid": "1", "title": "Woman Seated in a Garden", "beginyear": "1872", "endyear": "1872", "medium": "oil on canvas",
     "classification": "Painting", "attribution": "Claude Monet", "inscription": "signed Claude Monet"},
    {"objectid": "2", "title": "Weather Vane", "beginyear": "1935", "endyear": "1942", "medium": "watercolor and graphite on paper",
     "classification": "Index of American Design"},
    {"objectid": "3", "title": "Portrait of a Man", "beginyear": "1650", "endyear": "1650", "medium": "oil on canvas",
     "classification": "Painting"},
]
TERMS = [("1", "Keyword", "Woman", ""), ("1", "Keyword", "Garden", ""), ("1", "Keyword", "Umbrella", ""),
         ("1", "Style", "Impressionist", "Impressionist"), ("1", "School", "French", ""), ("1", "Theme", "landscape", "landscape"),
         ("2", "School", "American", ""), ("2", "Keyword", "Horse", "")]
IMAGES = [
    {"viewtype": "primary", "sequence": "0", "openaccess": "1", "depictstmsobjectid": "1",
     "assistivetext": "The image shows a woman seated under a green parasol in a garden. Monet signed it at lower right. "
                      "Two bright flowers fill the foreground. The signature reads CLAUDE MONET in red."},
    {"viewtype": "primary", "sequence": "0", "openaccess": "1", "depictstmsobjectid": "2",
     "assistivetext": "The image shows a copper weather vane in the shape of a running horse. The weather vane is on a rod."},
    {"viewtype": "primary", "sequence": "0", "openaccess": "0", "depictstmsobjectid": "3", "assistivetext": "A man."},
]


def _write(path, cols, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


def test_nga_seeds(tmp_path):
    d = tmp_path / "nga"
    d.mkdir()
    _write(d / "objects.csv", OBJ_COLS, OBJECTS)
    _write(d / "objects_terms.csv", TERM_COLS,
           [{"termid": str(i), "objectid": o, "termtype": k, "term": t, "visualbrowsertheme": v} for i, (o, k, t, v) in
            enumerate(TERMS)])
    _write(d / "published_images.csv", IMG_COLS, IMAGES)
    got = {s["seed_id"]: s for s in nga.seeds(str(tmp_path))}
    assert set(got) == {"nga:1", "nga:2"}                            # object 3 has no open-access image
    p = got["nga:1"]
    assert p["domain"] == "painting" and p["genre"] == "landscape"
    assert p["spec"] == {"person": {"gender": "woman"}, "body": {"pose": "sitting"}, "scene": {"setting": "garden"},
                         "thing": {"name": "umbrella"},
                         "form": {"medium": "oil painting", "style": "impressionism", "period": "19th century"}}
    assert "Monet" not in p["hint"] and "MONET" not in p["hint"] and "School: French." in p["hint"]
    assert "Two bright flowers fill the foreground." in p["hint"]
    v = got["nga:2"]
    assert v["domain"] == "illustration" and v["genre"] == "object study"
    assert v["spec"]["thing"] == {"name": "weather vane"} and v["spec"]["form"]["medium"] == "watercolour"
    for s in got.values():
        assert core.check_spec(s["spec"]) == [] and s["source"]["license"] == "CC0 1.0"
