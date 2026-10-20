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
         "credit line (the creators and the title are read only to find the names a hint must not keep); no row of one part "
         "of an object")
MODIFIED = ("transformed by this dataset, not the museum's own data: catalogue values mapped to the dataset's closed lists; the "
            "hint is an excerpt of the description and did_you_know texts, every sentence that may hold a name or speaks of the "
            "image as an image removed and the rest shortened, with technique, culture and title lines built from the fields")
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
        "technique", "department", "type", "description", "did_you_know", "url", "accession_number", "creators")
# a row of one part of an object ('Teapot (lid)', 'Koto (plectrum)', 'Inkwell (top to bottle)', 'Table (marble top)'): its title and
# type name the whole object while the row shows the part, so the row is left out
PART = re.compile(r"\(\s*(?:the\s+)?(?:(?:inner|outer|marble|left|right|center|central)\s+)?(?:lid|cover|stopper|stand|base|top|"
                  r"plectrum|scabbard|sheath|case|pole|frame|tray|head|bottle|blank|saucer|liner|handle|finial|spout|mount|plinth|"
                  r"pedestal|cap|box|drawer|door|wing|panel|predella|leg|foot)(?:\s+(?:lid|cover))?(?:\s+(?:of|to|for)\b[^)]*)?\s*\)"
                  r"\s*$", re.I)


def creator_names(creators: str) -> list:
    """The names of a creators field ('Frederic Edwin Church (American, 1826-1900), artist; Tyler Graphics Ltd., printer'):
    each part's text before its bracket or first comma."""
    return [re.split(r"\s*\(|,", p)[0].strip(" :") for p in (creators or "").split(";")]


def fetch(raw_dir: str) -> dict:
    return {"data.csv": met.download(CSV_URL, os.path.join(raw_dir, DATASET, "data.csv"))}


def rows(raw_dir: str):
    yield from load(raw_dir)[0].values()


def clean_html(t: str) -> str:
    import html
    return html.unescape(re.sub(r"<[^>]+>", " ", t or ""))


# a sentence about the maker's life rather than the object ('He considered this composition among his very best works', 'His
# family may have commissioned it', 'she continued to show her graphic work')
BIOGRAPHY = re.compile(r"\b(?:he|she)\s+(?:considered|lived|moved|studied|trained|exhibited|continued|worked|travell?ed|was born|"
                       r"died|spent|returned|settled|became|retired|married|taught|joined|left)\b|\b(?:his|her)\s+(?:career|family|"
                       r"life|late works|early works|work found|reputation|death|birth|patrons?|students?|pupils?|apprentices?)\b")


def without_biography(text: str) -> str:
    """The text without the sentences about the maker's life."""
    return " ".join(s for s in re.split(r"(?<=[.!?])\s+", text or "") if s and not BIOGRAPHY.search(s.lower()))


def build(r: dict, vocab: set, names: core.NameList | None = None):
    """One CC0 row to a seed, or None. `vocab`: the plain words of the description texts (core.corpus_vocab); `names`: the name
    words of every row's creators beside the ordinary words of the description texts (core.plain_words; seeds builds both)."""
    rid = r["id"].strip()
    title = r["title"]
    desc_raw = texts_of(r)
    if met.EXPLICIT.search(" ".join((title, desc_raw))):
        return None
    t = r["type"]
    if t in SKIP_TYPES or PART.search(title or ""):
        return None
    plain = names.plain if names is not None else vocab | met.TITLE_WORDS | met.CULTURE_WORDS
    own = core.NameList(core.name_tokens(creator_names(r.get("creators")), met.CULTURE_WORDS), plain,
                        openers=met.title_names(title, plain))         # a title's name words: a sitter, a place
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
            n2, state = met.object_noun(gtitle, armour=t == "Arms and Armor")
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
    met.title_disagrees(s, title)
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
    if med and not core.holds_name(med, names, own, opening=False):
        parts.append(f"Medium: {med}.")
    cul = met.culture_ok(culture)
    if cul:
        parts.append(f"Culture: {cul}.")
    if gtitle and not core.holds_name(gtitle, names, own, opening=False):
        parts.append(f'Title: "{gtitle}".')
    allow = (set(cul.split()) if cul else set()) | core.DATE_MARKS
    head = core.make_hint([core.drop_named(p, allow=allow) for p in parts])
    # the texts without image talk ('This image depicts', 'In this image'), then without a sentence that may hold a name
    desc = without_biography(core.drop_named_strict(core.without_image_talk(desc_raw), vocab, names=names, own=own))
    if desc:
        desc = met.fit(desc, core.HINT_MAX - len(head) - 1)
    hint = core.make_hint([desc, head] if desc else [head])
    return core.make_seed(DATASET, rid, domain, genre, s, hint, LICENSE, OBJECT_URL.format(r["accession_number"] or rid),
                          min_records=1 if len(hint) >= 100 else 2)


def texts_of(r: dict) -> str:
    """The prose of a row: its description and its 'did you know' text."""
    return clean_html(r["description"]) + " " + clean_html(r["did_you_know"])


def load(raw_dir: str) -> tuple:
    """-> (the CC0 rows by id, the creators' names of every row, CC0 or not, for the name list)."""
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
    table, creators = {}, set()
    with open(os.path.join(raw_dir, DATASET, "data.csv"), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            creators.update(creator_names(r.get("creators")))
            if (r.get("share_license_status") or "").strip() == "CC0":
                table[r["id"]] = {k: (r.get(k) or "") for k in COLS}
    return table, creators


def name_list(table: dict, creators) -> core.NameList:
    """The source's NameList: the words of every creator's name, beside the ordinary words of the rows' prose and techniques
    ('petit point', 'chine colle' are a technique's words, not names)."""
    texts = [texts_of(r) for r in table.values()] + [r["technique"] for r in table.values()]
    return core.NameList(core.name_tokens(creators, met.CULTURE_WORDS),
                         core.plain_words(texts) | met.TITLE_WORDS | met.CULTURE_WORDS)


def seeds(raw_dir: str, limit: int | None = None):
    """Seeds of the CC0 rows in a stable spread order; `limit`: at most that many (None: all, 0: none)."""
    if limit is not None and limit <= 0:
        return
    table, creators = load(raw_dir)
    vocab = core.corpus_vocab(texts_of(r) for r in table.values())
    names = name_list(table, creators)
    n = 0
    for rid in met.stable_order(table):
        seed = build(table[rid], vocab, names)
        if seed:
            yield seed
            n += 1
            if limit is not None and n >= limit:
                return
