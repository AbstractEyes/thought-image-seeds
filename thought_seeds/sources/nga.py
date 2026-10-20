"""thought_seeds.sources.nga - National Gallery of Art open data (CC0) to seeds.

The rows: the objects whose primary image is marked open access in published_images.csv (the gallery's public-domain mark). The
records come from the catalogue: the classification and subclassification (the domain; the object itself as the thing for a
decorative art object, a medal, a statuette, or an Index of American Design rendering), the medium (form medium), the begin and
end years (form period; the European era names only for a European or American school), the Style terms (form style), the
Keyword and Theme terms (person, thing, setting, weather, time, pose, angle; the genre) and a title only when every word of it is a
plain generic word. The hint: the medium, the school, a generic title, the subject words, and the primary image's description
(the assistive text of published_images.csv) with every sentence that may hold a name dropped."""
from __future__ import annotations

import csv
import os
import re
import sys

from .. import core, maps
from . import met

DATASET = "nga"
LICENSE = "CC0 1.0"
URL = "https://github.com/NationalGalleryOfArt/opendata"
ATTRIBUTION = "National Gallery of Art, Washington, open data program (CC0 1.0): objects with an open-access image"
CITATION = """@misc{nga_opendata,
  author       = {{National Gallery of Art}},
  title        = {National Gallery of Art Open Data Program: Collection Dataset},
  year         = {2021},
  howpublished = {\\url{https://github.com/NationalGalleryOfArt/opendata}},
  note         = {Released under Creative Commons Zero (CC0 1.0); updated daily; accessed 2026-10-19}
}"""
TAKEN = ("records + hint: objects.csv (classification, subclassification, medium, begin / end year, generic titles), "
         "objects_terms.csv (Keyword, Theme, Style, School, Technique), published_images.csv (open-access mark, the primary "
         "image's assistive text, names dropped); no attribution, inscription, provenance or credit line (the attribution and "
         "the title are read only to find the names a hint must not keep)")
MODIFIED = ("transformed by this dataset, not the gallery's own data: catalogue values mapped to the dataset's closed lists; the "
            "hint is assembled from the catalogue fields and an excerpt of the assistive text, its lead-ins that speak of the image "
            "('The image shows') taken off and every sentence that may hold a name removed")
BASE = "https://raw.githubusercontent.com/NationalGalleryOfArt/opendata/main/data/"
FILES = ("objects.csv", "objects_terms.csv", "published_images.csv")
OBJECT_URL = "https://www.nga.gov/collection/art-object-page.{}.html"

SKIP_CLASS = {"Portfolio", "Volume", "Technical Material", "Time-Based Media Art", "(not assigned)"}
SKIP_SUB = {"Contact Sheet", "Printmaking Matrices", "Archival", "Endpaper"}
SUB_NOUN = {"Medal/Medallion": "medal", "Plaquette": "plaquette", "Small Bronze": "statuette", "Bust": "bust",
            "Statuette": "statuette", "Relief": "relief", "Statue": "statue", "Coin": "coin", "Playing Card": "playing card",
            "Niello Plate": "niello plate", "Ceramic": "ceramic", "Furniture": "furniture", "Textile": "textile"}
TERM_ALIAS = {"female": ["women"], "male": ["men"], "child": ["children"], "girl": ["girls"], "boy": ["boys"],
              "self": ["self-portraits"], "daily life": ["genre scene"], "genre": ["genre scene"], "still": ["still life"],
              "life of christ": ["religious"], "old testament": ["religious"], "new testament": ["religious"], "christ": ["religious"],
              "virgin": ["religious"], "madonna": ["religious"], "saint": ["saints"], "religious": ["religious"],
              "mythology": ["mythology"], "military": ["war"], "animal": ["animals"], "plant": ["plants"], "group": ["figures"],
              "figure": ["figures"], "seated figure": ["seated figures"], "standing figure": ["standing figures"],
              "reclining figure": ["reclining figures"], "male figure": ["male figures"], "female figure": ["female figures"],
              "non-representational": ["abstraction"], "topographical": ["landscape"], "nude": ["nudes"]}
STYLE_ALIAS = {"pop": "pop art", "fauve": "fauvism", "abstraction": "abstract", "abstract expressionist": "abstract",
               "post-impressionist": None, "neoclassic": None, "neo-impressionist": "pointillism"}
VB_GENRE = {"portrait": "portrait", "genre": "genre scene", "landscape": "landscape", "still": "still life", "religious": "religious",
            "mythology": "mythology", "allegory": "allegory", "military": "war", "botanical": "botanical",
            "caricature": "caricature", "architecture": "architecture", "animal": "animal study",
            "non-representational": "abstract"}


def fetch(raw_dir: str) -> dict:
    return {f: met.download(BASE + f, os.path.join(raw_dir, DATASET, f)) for f in FILES}


def _rows(path: str):
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
    with open(path, encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh)


NAME_COLS = ("attribution", "attributioninverted")          # the artists (and 'after' / 'workshop of' forms) of every object


def load(raw_dir: str) -> tuple:
    """-> (objects {id: row}, terms {id: [(type, term)]}, alt {id: assistive text}, the attribution values of every object) for
    the objects with an open-access primary image."""
    d = os.path.join(raw_dir, DATASET)
    alt, open_ids = {}, set()
    best = {}
    for r in _rows(os.path.join(d, "published_images.csv")):
        if r.get("openaccess") != "1":
            continue
        oid = r["depictstmsobjectid"]
        open_ids.add(oid)
        rank = (r.get("viewtype") != "primary", int(r.get("sequence") or 0) if (r.get("sequence") or "0").isdigit() else 99)
        if r.get("assistivetext") and (oid not in best or rank < best[oid]):
            best[oid] = rank
            alt[oid] = r["assistivetext"]
    keep = ("objectid", "title", "beginyear", "endyear", "medium", "classification", "subclassification",
            "visualbrowserclassification", "displaydate") + NAME_COLS
    objects, attributions = {}, set()
    for r in _rows(os.path.join(d, "objects.csv")):
        attributions.update(r.get(c) or "" for c in NAME_COLS)
        if r["objectid"] in open_ids:
            objects[r["objectid"]] = {k: r.get(k) or "" for k in keep}
    terms = {}
    for r in _rows(os.path.join(d, "objects_terms.csv")):
        if r["objectid"] in objects:
            terms.setdefault(r["objectid"], []).append((r["termtype"], r["term"], r.get("visualbrowsertheme") or ""))
    return objects, terms, alt, attributions


def style_of(terms) -> str | None:
    for t in terms:
        t = core.ascii_text(t or "").lower().strip()
        if t in STYLE_ALIAS:
            if STYLE_ALIAS[t]:
                return STYLE_ALIAS[t]
            continue
        if re.search(r"\b(post|neo|proto)[- ]", t):
            continue
        v = maps.first(t, maps.STYLE)
        if v:
            return v
    return None


def domain_of(o: dict, medium: str | None) -> str | None:
    c = o["classification"]
    if c in SKIP_CLASS or o["subclassification"] in SKIP_SUB:
        return None
    if c == "Painting":
        return "painting"
    if c == "Sculpture":
        return "sculpture"
    if c == "Photograph":
        return "photograph"
    if c == "Decorative Art":
        return "design"
    if c == "Index of American Design":
        return "illustration"                          # a documentary rendering of an object, whatever its paint
    if c in ("Drawing", "Print"):
        return "painting" if c == "Drawing" and medium in met.PAINT_MEDIA else "illustration"
    return None


def build(o: dict, tl: list, alt_text: str, vocab: set, names: core.NameList | None = None):
    """One object to a seed, or None. `vocab`: the plain words of the assistive texts (core.corpus_vocab); `names`: the name words
    of every object's attribution beside the ordinary words of the assistive texts (core.plain_words; seeds builds both)."""
    oid = o["objectid"]
    title = o["title"]
    words = [t for _, t, _ in tl]
    if met.EXPLICIT.search(" ".join([title, alt_text] + words)):      # the assistive text becomes the hint: it is checked too
        return None
    plain = names.plain if names is not None else vocab | met.TITLE_WORDS | met.CULTURE_WORDS
    own = core.NameList(core.name_tokens([o.get(c) or "" for c in NAME_COLS], met.CULTURE_WORDS), plain,
                        openers=met.title_names(title, plain))         # a title's name words: a sitter, a place
    medium = met.medium_of(o["medium"])
    techniques = [t for k, t, _ in tl if k == "Technique"]
    if not medium and techniques and not met.medium_blocked(o["medium"]):
        medium = met.medium_of(" ; ".join(techniques))
    domain = domain_of(o, medium)
    if not domain:
        return None
    subj = []
    for k, t, _ in tl:
        if k in ("Keyword", "Theme"):
            subj.extend(TERM_ALIAS.get(core.ascii_text(t or "").lower().strip(), [t]))
    terms = met.norm_terms(subj)
    schools = [t for k, t, _ in tl if k == "School"]
    western = not met.NON_WESTERN.search(" ".join(schools))
    s = core.Spec()
    gtitle = met.title_ok(title, vocab)
    sub = met.apply_subjects(s, terms, domain, thing_from_tags=domain not in ("design",))
    noun = SUB_NOUN.get(o["subclassification"])
    if domain in ("design", "illustration") and o["classification"] in ("Decorative Art", "Index of American Design") and gtitle:
        n2, state = met.object_noun(gtitle)
        if n2 and not maps.find(n2, maps.GENDER) and not maps.find(n2, maps.AGE):
            noun = n2
    if noun and (domain == "design" or o["classification"] == "Index of American Design" or
                 (domain == "sculpture" and not sub["thing"])):
        s.set("thing", "name", noun, overwrite=True)
    if gtitle and o["classification"] != "Index of American Design":
        met.title_records(s, gtitle, domain)
    met.title_disagrees(s, title)
    met.fix_person(s)
    if medium:
        s.set("form", "medium", medium)
    styles = [t for k, t, _ in tl if k == "Style"]
    st = style_of(styles)
    if st:
        s.set("form", "style", st)
    per = maps.period_of(o["beginyear"], o["endyear"], western)
    if per and met.era_agrees(per, styles):              # a work styled 'Gothic' is not renaissance by its dates
        s.set("form", "period", per)
    genre = sub["genre"]
    if not genre:
        vb = [v.lower() for _, _, v in tl if v]
        genre = next((VB_GENRE[v] for v in vb if v in VB_GENRE), None)
    if o["classification"] == "Index of American Design":
        genre = "object study"
    elif domain == "design" or (domain == "sculpture" and not genre):
        genre = noun or genre or ("object" if domain == "design" else "sculpture")
    if not genre:
        genre = {"painting": "painting", "photograph": "photograph"}.get(domain, o["classification"].lower())
    parts = []
    med = met.plain_phrase(o["medium"], 160)
    if med and not core.holds_name(med, names, own, opening=False):
        parts.append(f"Medium: {med}.")
    cul = next((c for c in (met.culture_ok(x) for x in schools) if c), None)
    if cul:
        parts.append(f"School: {cul}.")
    ss = met.subject_sentence(terms)
    if ss:
        parts.append(ss)
    if gtitle and not core.holds_name(gtitle, names, own, opening=False):
        parts.append(f'Title: "{gtitle}".')
    allow = (set(cul.split()) if cul else set()) | core.DATE_MARKS
    parts = [core.drop_named(p, allow=allow) for p in parts]
    head = core.make_hint(parts)
    # the assistive text without its image talk ('The image shows a jug' -> 'A jug'), then without a sentence that may hold a
    # name, a signature or an inscription
    desc = core.drop_named_strict(core.without_image_talk(alt_text), vocab, names=names, own=own)
    if desc:
        desc = met.fit(desc, core.HINT_MAX - len(head) - 1)
    hint = core.make_hint([head, desc] if desc else [head])
    return core.make_seed(DATASET, oid, domain, genre, s, hint, LICENSE, OBJECT_URL.format(oid),
                          min_records=1 if len(hint) >= 100 else 2)


def name_list(objects: dict, alt: dict, attributions) -> core.NameList:
    """The source's NameList: the words of every object's attribution, beside the ordinary words of the assistive texts and the
    media ('chine colle' is a medium's words, not a name)."""
    texts = list(alt.values()) + [o.get("medium") or "" for o in objects.values()]
    return core.NameList(core.name_tokens(attributions, met.CULTURE_WORDS),
                         core.plain_words(texts) | met.TITLE_WORDS | met.CULTURE_WORDS)


def seeds(raw_dir: str, limit: int | None = None):
    """Seeds of the open-access objects in a stable spread order; `limit`: at most that many (None: all, 0: none)."""
    if limit is not None and limit <= 0:
        return
    objects, terms, alt, attributions = load(raw_dir)
    vocab = core.corpus_vocab(alt.values())
    names = name_list(objects, alt, attributions)
    n = 0
    for oid in met.stable_order(objects):
        seed = build(objects[oid], terms.get(oid, []), alt.get(oid, ""), vocab, names)
        if seed:
            yield seed
            n += 1
            if limit is not None and n >= limit:
                return
