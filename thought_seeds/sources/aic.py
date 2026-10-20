"""thought_seeds.sources.aic - Art Institute of Chicago public API (artworks marked public domain) to seeds.

Only the API's CC0 data reaches a seed. The `description` field is CC BY 4.0 under the Terms and Conditions of artic.edu, and those
Terms bar commercial use of the site's contents beyond what is labelled CC0; so the description is read only to keep names and
explicit words out (its plain words help the name filter) and is never copied. The records come from the catalogue fields: the
style (form style), the medium display and the technique / material terms (form medium), the start and end years (form period),
the artwork type (the domain), the subject terms (person, thing, setting, weather, time, angle, pose; the genre), and the colour
terms with the API's one computed colour (form palette, only when two colours can be named). The hint is built from the same CC0
fields: the medium and the subject terms.

The fetch is polite: one request a second, 100 artworks a request, at most MAX_ARTWORKS (6,000 for now): the public-domain
artworks that carry a description (6,840 on 2026-10-19 of 62,119 public-domain works), in id order. The search API serves at most
1,000 results a query, so the walk goes by id range (keyset), always the first page."""
from __future__ import annotations

import glob
import html
import json
import os
import re
import time

from .. import core, maps
from . import met

DATASET = "aic"
LICENSE = "CC0 1.0"
URL = "https://api.artic.edu/docs/"
TERMS_URL = "https://www.artic.edu/terms"
ATTRIBUTION = ("Art Institute of Chicago, public API (api.artic.edu), artworks endpoint: the artwork data, CC0 1.0 under the Terms "
               f"and Conditions of artic.edu ({TERMS_URL}), as the API's own license notice states; the CC BY 4.0 description "
               "field is not used")
CITATION = """@misc{artic_api,
  author       = {{Art Institute of Chicago}},
  title        = {Art Institute of Chicago Public API},
  year         = {2018},
  howpublished = {\\url{https://api.artic.edu/docs/}},
  note         = {Artwork data under Creative Commons Zero (CC0 1.0) and the Terms and Conditions of artic.edu; artworks with
                  is_public_domain = true; accessed 2026-10-19}
}"""
TAKEN = ("records + hint: public-domain artworks from the search API (style_title, medium_display, technique / material / "
         "classification terms, date_start / date_end, artwork_type_title, subject_titles, color); no artist, title or "
         "description (the artist fields, the title and the description are read only to keep names and explicit words out)")
MODIFIED = ("modified by this dataset: catalogue values mapped to the dataset's closed lists; the hint is built from the CC0 "
            "medium and subject fields")
API = "https://api.artic.edu/api/v1/artworks/search"
ARTWORK_URL = "https://www.artic.edu/artworks/{}"
MAX_ARTWORKS = 6000
PAGE = 100
HEADERS = {"AIC-User-Agent": "thought-seeds (https://huggingface.co/datasets/AbstractPhil/thought-symbolic-image-captions)"}
FIELDS = ("id,title,date_start,date_end,medium_display,artwork_type_title,classification_title,classification_titles,style_title,"
          "style_titles,subject_titles,material_titles,technique_titles,theme_titles,color,description,is_public_domain,"
          "place_of_origin,artist_title,artist_titles,artist_display")
ARTIST_FIELDS = ("artist_title", "artist_display")          # read only for the name filter (a batch fetched without them has none)
COMPUTED_MIN_PERCENT = 3.0      # the computed colour's 'percentage' (a percent: it reaches 4.07 in the fetched data) to name it
LIC_CC0 = "CC0 1.0"

TYPE_DOMAIN = {"painting": "painting", "sculpture": "sculpture", "photograph": "photograph", "print": "illustration",
               "drawing and watercolor": "drawing", "book": "illustration", "architectural drawing": "illustration",
               "miniature painting": "painting", "mask": "sculpture", "vessel": "design", "textile": "design", "furniture": "design",
               "decorative arts": "design", "ceramics": "design", "glass": "design", "metalwork": "design", "jewelry": "design",
               "arms": "design", "armor": "design", "costume and accessories": "design", "coin": "design", "medal": "design",
               "basketry": "design", "design": "design", "architectural fragment": "design", "miniature room": "design",
               "equipment": "design", "funerary object": "design", "religious/ritual object": "design", "musical instrument": "design",
               "lighting": "design", "tool": "design", "toy": "design", "container": "design", "woodwork": "design"}
SCULPTURE_TERMS = re.compile(r"\b(sculpture|statue|statuette|figure|figurine|bust|relief)\b", re.I)
# colour terms of the subject list ('blue (color)') to the colour list
COLOUR_TERM = re.compile(r"^([a-z ]+?) \(colou?r\)$")
BASIC_COLOURS = {"black", "white", "red", "blue", "green", "yellow", "brown", "grey", "gray", "purple", "pink", "violet"}
STYLE_GUARD = {"post-impressionism": None, "post impressionism": None, "neo-impressionism": "pointillism",
               "neo-impressionist": "pointillism", "neoclassicism": None, "neo-classicism": None, "neoclassical": None,
               "magic realism": None, "social realism": "realism", "neo-expressionism": "expressionism", "gothic revival": "gothic",
               "neo-gothic": "gothic", "neo-dada": None, "art nouveau": "art nouveau", "art deco": "art deco"}


# the API's own subject terms to the shared museum terms (a name gives only its genre: it never reaches a seed)
ALIAS = {"portraits: male subject": ["portraits", "men"], "portraits: female subject": ["portraits", "women"],
         "portraits: child subject": ["portraits", "children"], "portraits: european subject": ["portraits"],
         "portraits: french subject": ["portraits"], "portraits: african subject": ["portraits"], "male": ["men"],
         "female": ["women"], "bearded man": ["men"], "boatman": ["men"], "mother and child": ["mothers"],
         "woman with children": ["mothers"], "goddesses": ["women", "mythology"], "gods (deities)": ["deities"],
         "greek gods": ["mythology"], "mythological figures": ["mythology"], "mythical": ["mythology"], "greek mythology": ["mythology"],
         "christian subjects": ["religious"], "christianity": ["religious"], "religious scenes": ["religious"],
         "religious figures": ["religious"], "biblical": ["religious"], "bibles": ["religious"], "crucifixions": ["crucifixion"],
         "nativity scenes": ["nativity"], "resurrection scenes": ["resurrection"], "jesus": ["religious"],
         "virgin mary": ["religious"], "virgin and child/madonna and child": ["religious"], "madonna": ["religious"],
         "saint john the baptist": ["religious"], "mary magdalene": ["religious"], "buddha": ["religious"], "martyrs": ["religious"],
         "zeus": ["mythology"], "heracles": ["mythology"], "athena": ["mythology"], "venus": ["mythology"],
         "dionysos": ["mythology"], "pegasus": ["mythology"], "cherubs": ["putti"], "cupids": ["putti"], "night scenes": ["night"],
         "everyday life (genre)": ["genre scene"], "rural life": ["genre scene"], "farm life": ["genre scene"],
         "urban life": ["genre scene"], "horseback riding": ["equestrians"], "rider": ["equestrians"], "sphinxes": ["sphinx"],
         "deers": ["deer"], "pine cones": ["pinecones"], "architechture": ["architecture"], "botanical/floral": ["botanical"],
         "floral motifs": ["flowers"], "floral": ["flowers"], "peasants": ["people"], "families": ["family"], "sons": ["people"],
         "nobility": ["people"], "royalty": ["people"], "rulers (people)": ["people"], "hunter": ["people"], "friars": ["monks"],
         "ballet": ["dancers"], "figures (representations)": ["figures"], "anthropomorphic figure": ["figures"],
         "abstract figures": ["figures"]}
# object nouns the classification terms may give for a design object or a sculpture (the first one found is the thing)
OBJECT_NOUNS = {"paperweight", "bowl", "dish (vessel)", "vase", "jar", "cup", "plate", "statuette", "amulet", "mask", "coin", "medal",
                "chair", "table", "cabinet", "armchair", "settee", "desk", "chest", "helmet", "sword", "dagger", "shield", "ring",
                "necklace", "bracelet", "brooch", "earring", "teapot", "pitcher", "jug", "ewer", "bottle", "box", "fan", "dress",
                "robe", "shoe", "hat", "tile", "lamp", "mirror", "clock", "goblet", "beaker", "tankard", "spoon", "candlestick",
                "textile", "tapestry", "quilt", "coverlet", "rug", "carpet", "shawl", "kimono", "figurine", "bust", "relief", "stela",
                "urn", "basin", "tray", "platter", "tureen", "sugar bowl", "creamer", "salt cellar", "inkstand", "snuff box", "beaker",
                "kylix", "amphora", "lekythos", "krater", "oinochoe", "hydria", "skyphos", "aryballos", "alabastron", "pyxis",
                "drinking vessel", "miniature room"}
TYPE_NOUN = {"coin": "coin", "vessel": "vessel", "textile": "textile", "miniature room": "miniature room", "armor": "armour",
             "mask": "mask", "basketry": "basket", "medals": "medal", "jewelry": "jewelry"}


def style_of(texts) -> str | None:
    """form style from the style terms: the guard first (post-impressionism is not impressionism), then the shared map."""
    for t in texts:
        t = core.ascii_text(t or "").lower().strip()
        if not t:
            continue
        if t in STYLE_GUARD:
            if STYLE_GUARD[t]:
                return STYLE_GUARD[t]
            continue
        if re.search(r"\b(post|neo|proto|late|anti)[- ]", t):
            continue
        v = maps.first(t, maps.STYLE)
        if v:
            return v
    return None


def hsl_name(c: dict) -> str | None:
    """The API's computed colour (h 0-360, s and l 0-100) to a plain colour of the list, or None when it is not clear or covers
    under COMPUTED_MIN_PERCENT of the picture by the API's own 'percentage' (a speck is no colour of the palette)."""
    try:
        h, s, l = float(c["h"]), float(c["s"]), float(c["l"])
        if float(c.get("percentage") or 0) < COMPUTED_MIN_PERCENT:
            return None
    except (TypeError, KeyError, ValueError, AttributeError):
        return None
    if l <= 12:
        return "black"
    if l >= 92:
        return "white"
    if s <= 12:
        return "grey" if 25 <= l <= 80 else None
    if 15 <= h < 50 and (l < 38 or (s < 45 and l < 55)):
        return "brown"
    for lo, hi, name in ((0, 12, "red"), (12, 40, "orange"), (40, 68, "yellow"), (68, 165, "green"), (165, 195, "teal"),
                         (195, 255, "blue"), (255, 290, "purple"), (290, 340, "pink"), (340, 361, "red")):
        if lo <= h < hi:
            return name
    return None


def palette(subject_colours: list, computed: str | None) -> str | None:
    """'a and b' from the named colours (the catalogue's words first, then the computed one), the first pair in the budget."""
    names = []
    for c in subject_colours + ([computed] if computed else []):
        if c and c not in names:
            names.append(c)
    budget = core.tp.REC_MAX - len("form palette")
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            v = f"{names[i]} and {names[j]}"
            if len(v) <= min(budget, core.tp.VAL_MAX):
                return v
    return None


def query(after_id: int) -> dict:
    """The search body: public-domain artworks that carry a description, id after `after_id`, in id order (the API serves at most
    1,000 results a query, so the walk goes by id, one first page at a time)."""
    return {"query": {"bool": {"must": [{"term": {"is_public_domain": True}}, {"exists": {"field": "description"}},
                                        {"range": {"id": {"gt": int(after_id)}}}]}},
            "sort": [{"id": "asc"}], "limit": PAGE, "page": 1, "fields": FIELDS.split(",")}


def fetch(raw_dir: str) -> dict:
    """Batches of 100 artworks (batch-NNNN.json) up to MAX_ARTWORKS, one request a second; a present batch is kept and the walk
    resumes after its last id."""
    import requests
    d = os.path.join(raw_dir, DATASET)
    os.makedirs(d, exist_ok=True)
    out, after, last, n = {}, 0, 0.0, 0
    for b in range(1, (MAX_ARTWORKS + PAGE - 1) // PAGE + 1):
        path = os.path.join(d, f"batch-{b:04d}.json")
        if not (os.path.exists(path) and os.path.getsize(path) > 0):
            wait = 1.05 - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            for attempt in range(5):
                last = time.time()
                r = requests.post(API, json=query(after), headers=HEADERS, timeout=60)
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                break
            with open(path + ".part", "w", encoding="utf-8") as fh:
                json.dump(r.json(), fh, ensure_ascii=True)
            os.replace(path + ".part", path)
        out[os.path.basename(path)] = os.path.getsize(path)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh).get("data") or []
        n += len(data)
        if len(data) < PAGE or n >= MAX_ARTWORKS:
            break
        after = max(int(a["id"]) for a in data)
    return out


def artworks(raw_dir: str) -> list:
    """The fetched artworks, each once, public domain only, in id order."""
    seen, out = set(), []
    for path in sorted(glob.glob(os.path.join(raw_dir, DATASET, "batch-*.json"))):
        with open(path, encoding="utf-8") as fh:
            for a in json.load(fh).get("data") or []:
                if a.get("is_public_domain") is True and a.get("id") not in seen:
                    seen.add(a["id"])
                    out.append(a)
    return out[:MAX_ARTWORKS]


def western(a: dict) -> bool:
    """A work of the European tradition (its styles, place and classifications name no other: 'Pre-Columbian', 'americas',
    'Islamic (culture or style)' in style_titles are not): the European era names apply."""
    text = " ".join([a.get("style_title") or "", a.get("place_of_origin") or ""] + list(a.get("style_titles") or []) +
                    list(a.get("classification_titles") or []))
    return not met.NON_WESTERN.search(core.ascii_text(text))


def strip_html(t: str) -> str:
    t = re.sub(r"<[^>]+>", " ", t or "")
    return html.unescape(t)


def domain_of(a: dict, medium: str | None) -> str:
    t = (a.get("artwork_type_title") or "").lower()
    d = TYPE_DOMAIN.get(t)
    if d == "drawing":
        return "painting" if medium in met.PAINT_MEDIA else "illustration"
    if d:
        return d
    cls = " ".join(a.get("classification_titles") or []).lower()
    if "photograph" in cls:
        return "photograph"
    if "painting" in cls and "vase painting" not in cls:
        return "painting"
    if SCULPTURE_TERMS.search(cls):
        return "sculpture"
    if any(k in cls for k in ("print", "drawing", "book", "watercolor")):
        return "painting" if medium in met.PAINT_MEDIA else "illustration"
    return "design"


# the head words of object names: a design object's title gives its thing only when it ends in one of them or in a word of the
# artwork's own classification terms (a tapestry's title names its scene: 'The Lovers', 'A Falconer with Two Ladies')
# catalogue words for an object (the last word of a design object's title noun must be one: a vessel shape, a garment, a fitting;
# never a figure, a scene or a material word: 'lovers', 'falconer', 'stag hunt', 'striped silk', 'salt' for a salt cellar)
OBJECT_WORDS = frozenset((
    "vessel furniture jewelry pendant ornament costume garment panel hanging cover case stand screen frame chest saucer dish pot "
    "flask canteen lid spoon fork knife container stamnos kantharos kalpis pelike olpe psykter dinos lebes lekanis loutrophoros "
    "rhyton mug cup chalice flagon decanter carafe teacup coffeepot sauceboat salver charger bucket pail cauldron tripod censer "
    "burner brazier lantern candelabrum chandelier sconce monstrance reliquary ciborium paten cross crucifix casket coffer bureau "
    "commode drawer stool bench bed cradle kesa cope chasuble dalmatic stole orphrey mantle cloak tunic coat jacket vest skirt scarf "
    "headcloth turban cap bonnet glove slipper sandal boot belt sash apron blanket bedcover valance curtain mat towel napkin "
    "tablecloth cushion pillow border sampler suzani sarape poncho shroud veil pectoral comb hairpin buckle clasp button hook "
    "weight seal plaque plaquette mold mould finial mount harness spur cuirass gauntlet pillar column lintel monument naiskos "
    "sarcophagus ossuary tusk bell drum rattle whistle doll centerpiece epergne cistern cloth").split())
OBJECT_HEADS = ({re.sub(r"\s*\([^)]*\)", "", n).split()[-1] for n in OBJECT_NOUNS} | set(TYPE_NOUN.values()) | OBJECT_WORDS)


def object_title(noun: str, cls: list) -> bool:
    """Whether a design object's title noun names an object: its last word (or that word's singular, or the last part of a
    hyphenated word: 'column-krater') is an object word (OBJECT_HEADS) or the last word of one of its classification terms
    ('covered jar', 'pair of vases', 'incense burner'; not 'lovers', 'falconer', 'stag hunt', 'recumbent stag', 'woven silk')."""
    heads = OBJECT_HEADS | {re.sub(r"\s*\([^)]*\)", "", c).split()[-1] for c in cls if re.sub(r"\s*\([^)]*\)", "", c).split()}
    last = noun.split()[-1]
    return noun in OBJECT_NOUNS or any(w in heads for w in (last, met._singular(last) or "", last.rsplit("-", 1)[-1]))


def own_names(a: dict, plain: set) -> core.NameList:
    """The name words of one artwork: its artist fields (when the batch holds them; any case), and as openers (core.NameList)
    the words of its title that are not plain words (a sitter, a place) and of its capitalized subject terms ('Napoleon', 'Saint
    Margaret'; 'Chariots', 'Bread' are capitalized there too, so in lower case these words are ordinary words)."""
    vals = [a.get(f) or "" for f in ARTIST_FIELDS] + [t for t in (a.get("artist_titles") or []) if t]
    caps = [t for t in (a.get("subject_titles") or []) if t and t[:1].isupper()]
    return core.NameList(core.name_tokens(vals, met.CULTURE_WORDS), plain,
                         openers=met.title_names(a.get("title") or "", plain) | (core.name_tokens(caps, met.CULTURE_WORDS) - plain))


def build(a: dict, vocab: set, names: core.NameList | None = None):
    """One artwork to a seed, or None. `vocab`: the plain words of the descriptions (core.corpus_vocab); `names`: the name words
    of every artwork's artist fields beside the ordinary words of the descriptions (core.plain_words; seeds builds both)."""
    aid = str(a["id"])
    title = a.get("title") or ""
    subjects = a.get("subject_titles") or []
    if met.EXPLICIT.search(" ".join([title, strip_html(a.get("description") or "")] + subjects + (a.get("theme_titles") or []))):
        return None
    plain = names.plain if names is not None else vocab | met.TITLE_WORDS | met.CULTURE_WORDS
    own = own_names(a, plain)
    medium_text = a.get("medium_display") or ""
    medium = met.medium_of(medium_text)
    if medium is None and not met.medium_blocked(medium_text):        # an engraving is not read again from its 'ink' material
        medium = met.medium_of(" ; ".join((a.get("technique_titles") or []) + (a.get("material_titles") or [])))
    domain = domain_of(a, medium)
    colours, other = [], []
    for t in subjects:
        t = core.ascii_text(t or "").lower().strip()
        m = COLOUR_TERM.match(t)
        bare = t in BASIC_COLOURS                          # 'wine', 'orange', 'gold' as a bare subject are things, not colours
        if m or bare:
            v = maps.first(m.group(1) if m else t, maps.COLOUR)
            if v and v not in maps.HAIR_COLOUR_ONLY:
                colours.append(v)
        else:
            other.extend(ALIAS.get(t, [t]))
    terms = met.norm_terms(other)
    s = core.Spec()
    gtitle = met.title_ok(title, vocab)
    sub = met.apply_subjects(s, terms, domain, thing_from_tags=domain != "design")
    noun = None
    cls = [core.ascii_text(c or "").lower() for c in (a.get("classification_titles") or [])]
    if domain in ("design", "sculpture") and gtitle:
        noun, state = met.object_noun(gtitle, armour=(a.get("artwork_type_title") or "").lower() in ("armor", "arms"))
        if noun and (maps.find(noun, maps.GENDER) or maps.find(noun, maps.AGE) or
                     (domain == "sculpture" and not met.SCULPT_NAME.search(noun)) or
                     (domain == "design" and not object_title(noun, cls))):
            noun = None                                   # a title naming the figure or the scene is not the object's name
        if noun and (domain == "design" or not sub["thing"]):
            s.set("thing", "name", noun, overwrite=domain == "design")
            if state:
                s.set("thing", "state", state)
    if domain in ("design", "sculpture") and not noun and not (domain == "sculpture" and sub["thing"]):
        noun = next((re.sub(r" \(vessel\)$", "", c) for c in cls if c in OBJECT_NOUNS), None)
        if not noun and domain == "design":
            noun = TYPE_NOUN.get((a.get("artwork_type_title") or "").lower())
        if noun:
            s.set("thing", "name", noun, overwrite=domain == "design")
            if "fragment" in cls:
                s.set("thing", "state", "fragment")
    if gtitle:
        met.title_records(s, gtitle, domain)
    met.title_disagrees(s, title)
    met.fix_person(s)
    if medium:
        s.set("form", "medium", medium)
    if domain in ("design", "sculpture") and s.has("thing", "name"):
        metal = met.COLOUR_METAL.get(core.clean(medium_text))
        if metal:
            s.set("thing", "colour", metal)
    styles = [a.get("style_title") or ""] + list(a.get("style_titles") or [])
    st = style_of(styles)
    if st:
        s.set("form", "style", st)
    pal = palette(colours, hsl_name(a.get("color") or {}))
    if pal:
        s.set("form", "palette", pal)
    per = maps.period_of(a.get("date_start"), a.get("date_end"), western(a))
    if per and met.era_agrees(per, styles):              # a work styled 'medieval' is not renaissance by its dates
        s.set("form", "period", per)
    genre = sub["genre"]
    if domain == "design" or (domain == "sculpture" and not genre):
        genre = noun or genre or (a.get("artwork_type_title") or domain).lower()
    if not genre:
        kind = (a.get("artwork_type_title") or "print").lower()
        genre = {"painting": "painting", "photograph": "photograph", "sculpture": "sculpture"}.get(
            domain, "drawing" if kind.startswith("drawing") else kind)
    parts = []
    med = met.plain_phrase(medium_text, 160)
    if med and not core.holds_name(med, names, own, opening=False):
        parts.append(f"Medium: {med}.")
    ss = met.subject_sentence(terms)
    if ss:
        parts.append(ss)
    hint = core.make_hint(parts)                          # CC0 fields only: the CC BY description is never copied
    return core.make_seed(DATASET, aid, domain, genre, s, hint, LIC_CC0, ARTWORK_URL.format(aid),
                          min_records=1 if len(hint) >= 100 else 2)


def name_list(arts: list) -> core.NameList:
    """The source's NameList: every artwork's artist names (the batches fetched before the artist fields were asked for hold
    none: then the list is empty), beside the ordinary words of the descriptions and the media."""
    artists = core.name_tokens((v for a in arts for v in [a.get(f) or "" for f in ARTIST_FIELDS] + list(a.get("artist_titles") or [])
                                if v), met.CULTURE_WORDS)
    texts = [strip_html(a.get("description") or "") for a in arts] + [a.get("medium_display") or "" for a in arts]
    return core.NameList(artists, core.plain_words(texts) | met.TITLE_WORDS | met.CULTURE_WORDS)


def seeds(raw_dir: str, limit: int | None = None):
    """Seeds of the fetched artworks in id order; `limit`: at most that many (None: all, 0: none)."""
    if limit is not None and limit <= 0:
        return
    arts = artworks(raw_dir)
    vocab = core.corpus_vocab(strip_html(a.get("description") or "") for a in arts)
    names = name_list(arts)
    n = 0
    for a in arts:
        seed = build(a, vocab, names)
        if seed:
            yield seed
            n += 1
            if limit is not None and n >= limit:
                return
