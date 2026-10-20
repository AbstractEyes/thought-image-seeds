"""thought_seeds.sources.cleveland - The Cleveland Museum of Art Open Access (data.csv, CC0) to seeds.

The rows marked share_license_status = CC0 (the public-domain works). The dataset carries no subject terms, so the records are
fewer: the type (the domain; the object itself as the thing for a decorative art object, from a generic title or the type), the
technique (form medium), the earliest and latest creation years (form period; the European era names only for a European or
American culture), and the words of a title when every word of it is a plain generic word (person, setting, time, weather, pose).
The hint: the description and the 'did you know' text (CC0 like the rest of the data) with every sentence that may hold a name
dropped, then the technique, the culture and a generic title."""
from __future__ import annotations

import csv
import os
import re
import sys

from .. import core, maps
from . import met

DATASET = "cleveland"
LICENSE = "CC0 1.0"
URL = "https://github.com/ClevelandMuseumArt/openaccess"
ATTRIBUTION = "The Cleveland Museum of Art Open Access, data.csv (CC0 1.0), rows with share_license_status CC0"
CITATION = """@misc{cma_openaccess,
  author       = {{The Cleveland Museum of Art}},
  title        = {The Cleveland Museum of Art Open Access Dataset},
  year         = {2019},
  howpublished = {\\url{https://github.com/ClevelandMuseumArt/openaccess}},
  note         = {Released under Creative Commons Zero (CC0 1.0); accessed 2026-10-19}
}"""
TAKEN = ("records + hint: the CC0 rows of data.csv (type, technique, creation_date_earliest / latest, culture, department, "
         "generic titles; description and did_you_know as the hint, names dropped); no creator, inscription, provenance or "
         "credit line")
CSV_URL = "https://media.githubusercontent.com/media/ClevelandMuseumArt/openaccess/master/data.csv"
OBJECT_URL = "https://clevelandart.org/art/{}"

TYPE_DOMAIN = {"Print": "illustration", "Painting": "painting", "Photograph": "photograph", "Sculpture": "sculpture",
               "Portrait Miniature": "painting", "Manuscript": "illustration", "Calligraphy": "illustration", "Drawing": "drawing",
               "Mask": "sculpture"}
SKIP_TYPES = {"Bound Volume", "Portfolio", "Miscellaneous", "Book Binding", "Time-based Media", "Film", "Digital Art"}
TYPE_NOUN = {"Coins": "coin", "Garment": "garment", "Textile": "textile", "Lace": "lace", "Embroidery": "embroidery",
             "Velvet": "velvet textile", "Tapestry": "tapestry", "Sampler": "sampler", "Spindle Whorl": "spindle whorl",
             "Amulets": "amulet", "Musical Instrument": "instrument", "Mask": "mask", "Basketry": "basket", "Vessels": "vessel"}
TYPE_FORM = {"Velvet": ("texture", "velvet"), "Tapestry": ("medium", "tapestry"), "Stained Glass": ("medium", "stained glass")}
COLS = ("id", "share_license_status", "title", "creation_date", "creation_date_earliest", "creation_date_latest", "culture",
        "technique", "department", "type", "description", "did_you_know", "url", "accession_number")


def fetch(raw_dir: str) -> dict:
    return {"data.csv": met.download(CSV_URL, os.path.join(raw_dir, DATASET, "data.csv"))}


def rows(raw_dir: str):
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
    with open(os.path.join(raw_dir, DATASET, "data.csv"), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if (r.get("share_license_status") or "").strip() == "CC0":
                yield {k: (r.get(k) or "") for k in COLS}


def clean_html(t: str) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", " ", t or ""))


def build(r: dict, vocab: set):
    rid = r["id"].strip()
    title = r["title"]
    desc_raw = clean_html(r["description"]) + " " + clean_html(r["did_you_know"])
    if met.EXPLICIT.search(" ".join((title, desc_raw))):
        return None
    t = r["type"]
    if t in SKIP_TYPES:
        return None
    medium = met.medium_of(r["technique"])
    domain = TYPE_DOMAIN.get(t, "design")
    if domain == "drawing":
        domain = "painting" if medium in met.PAINT_MEDIA else "illustration"
    culture = r["culture"]
    western = not met.NON_WESTERN.search(culture + " " + r["department"])
    s = core.Spec()
    gtitle = met.title_ok(title, vocab)
    noun = None
    if domain in ("design", "sculpture"):
        if gtitle:
            n2, state = met.object_noun(gtitle)
            if n2 and not maps.find(n2, maps.GENDER) and not maps.find(n2, maps.AGE) and (
                    domain == "design" or met.SCULPT_NAME.search(n2)):
                noun = n2
                if state:
                    s.set("thing", "state", state)
        noun = noun or TYPE_NOUN.get(t)
        if noun:
            s.set("thing", "name", noun)
            metal = met.COLOUR_METAL.get(core.clean(r["technique"]))
            if metal:
                s.set("thing", "colour", metal)
    if gtitle:
        met.title_records(s, gtitle, domain)
        g = next((g for keys, g in met.GENRES if any(re.search(rf"\b{re.escape(k)}\b", gtitle) for k in keys)
                  and g in ("portrait", "self portrait", "landscape", "still life", "seascape", "interior", "cityscape")), None)
    else:
        g = None
    met.fix_person(s)
    if medium:
        s.set("form", "medium", medium)
    if t in TYPE_FORM:
        a, v = TYPE_FORM[t]
        s.set("form", a, v)
    per = maps.period_of(r["creation_date_earliest"], r["creation_date_latest"], western)
    if per:
        s.set("form", "period", per)
    if domain == "design" or (domain == "sculpture" and not g):
        genre = noun or t.lower()
    else:
        genre = g or {"painting": "painting", "photograph": "photograph", "illustration": "print" if t == "Print" else
                      t.lower()}.get(domain, domain)
    parts = []
    med = met.plain_phrase(r["technique"], 160)
    if med:
        parts.append(f"Medium: {med}.")
    cul = met.culture_ok(culture)
    if cul:
        parts.append(f"Culture: {cul}.")
    if gtitle:
        parts.append(f'Title: "{gtitle}".')
    allow = (set(cul.split()) if cul else set()) | core.DATE_MARKS
    head = core.make_hint([core.drop_named(p, allow=allow) for p in parts])
    desc = core.drop_named_strict(desc_raw, vocab)
    if desc:
        desc = met.fit(desc, core.HINT_MAX - len(head) - 1)
    hint = core.make_hint([desc, head] if desc else [head])
    return core.make_seed(DATASET, rid, domain, genre, s, hint, LICENSE, OBJECT_URL.format(r["accession_number"] or rid),
                          min_records=1 if len(hint) >= 100 else 2)


def seeds(raw_dir: str, limit: int | None = None):
    table = {r["id"]: r for r in rows(raw_dir)}
    vocab = core.corpus_vocab(clean_html(r["description"]) + " " + clean_html(r["did_you_know"]) for r in table.values())
    n = 0
    for rid in met.stable_order(table):
        seed = build(table[rid], vocab)
        if seed:
            yield seed
            n += 1
            if limit and n >= limit:
                return
