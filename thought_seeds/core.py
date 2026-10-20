"""thought_seeds.core - the seed contract of the art thought dataset (AbstractPhil/thought-symbolic-image-captions).

A SEED is the hidden picture spec a generating model writes thought rows from: the FACTS of one picture in the dataset's systems trie
(seal(frac=0.1, seed=2026) over the closed lists), never mood, intent or story (the generating model adds those, the mood with the record
it is read from). One JSON object a line:

    {"seed_id": "<source>:<id>", "domain": "photograph|painting|illustration|sculpture|design", "genre": "<one or two words>",
     "spec": {system: {attribute: value}, "relation": [{"a", "rel", "b"}]}, "hint": "<optional source text, <= 600 bytes>",
     "source": {"dataset", "id", "license", "url"}, "held": true|false}

Every value is plain lower-case ASCII of at most 20 bytes, key + value at most 27 bytes (one 32-byte frame slice); a closed-list key
takes a value of its list; a seed whose records use a sealed value feeds the held split only.

The attribute systems, the vocabularies, the seal, the row validator and the seed gate live in the dataset's own tools file,
`tools/thought_tools.py` of the dataset repo (numpy only). This package carries a verbatim copy, thought_seeds/thought_tools.py
(TOOLS_SHA256 below; THOUGHT_TOOLS names another copy to use instead), and checks on import that its sealed tenth is the dataset's
(SEAL_SHA256), so every build uses the same lists and the same held-out values."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import unicodedata
from collections import Counter

TOOLS_FILE = os.environ.get("THOUGHT_TOOLS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "thought_tools.py")
TOOLS_SOURCE = "AbstractPhil/thought-symbolic-image-captions: tools/thought_tools.py, 'tools 0.1.6'"
TOOLS_SHA256 = "8b2bb52d8926449b4fedef3dd71933c78d221311d5c699f98eb5db317a92862d"     # the vendored copy, byte for byte
SEAL_SHA256 = "c7be2f6e59f53cb752eeb961d2fe1a1a36c374bbc67aaec51a96fb7814c79b7b"      # sha256 of json.dumps(seal(), sort_keys=True)


def _load_tools():
    name = "thought_seeds_tools"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, TOOLS_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


tp = _load_tools()
HELD = tp.seal()                                    # the sealed tenth (73 values; final)
assert hashlib.sha256(json.dumps(HELD, sort_keys=True).encode()).hexdigest() == SEAL_SHA256, \
    f"{TOOLS_FILE}: its sealed values differ from the dataset's; the held split would not match"
KEYS = set(tp.keys())
DOMAINS = tp.DOMAINS
INTERPRETIVE = ("mood", "intent", "story")          # the generating model's systems: never in a seed
SEED_MAX_RECORDS = 24                               # the deep row holds 14-30 records; the model's mood / intent / story fill the rest
MAX_RELATIONS = 6
HINT_MAX = 600
HELD_PERCENT = 10                                   # of the seeds that use a sealed value, the share kept whole for the held split
REJECTED: Counter = Counter()                       # make_seed's rejections by first problem (the build prints them per source)


def clean(s) -> str:
    """A plain lower-case ASCII value: accents folded, punctuation to spaces (hyphen and apostrophe kept), spaces collapsed."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("_", " ")
    s = re.sub(r"[^a-z0-9 '\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -'")


def closed_list(key: str) -> list | None:
    name = tp.KEY_LIST.get(key)
    return tp.VOCAB[name] if name else None


class Spec:
    """A seed spec under construction: the first value set for a key wins unless overwrite; values outside a closed list, over the
    budget or past the record cap are dropped and counted (self.dropped)."""

    def __init__(self):
        self.d: dict = {}
        self.rels: list = []
        self.dropped: Counter = Counter()

    def n(self) -> int:
        return sum(len(a) for a in self.d.values()) + len(self.rels)

    def has(self, system: str, attr: str) -> bool:
        return attr in self.d.get(system, {})

    def set(self, system: str, attr: str, value, overwrite: bool = False) -> bool:
        key = f"{system} {attr}"
        if system in INTERPRETIVE:
            raise ValueError(f"{key}: a seed carries facts only (mood, intent, story are the generating model's)")
        if key not in KEYS or system == "relation":
            raise KeyError(f"{key} is not a key of the trie")
        v = clean(value)
        if not v:
            return False
        lst = closed_list(key)
        if lst is not None and v not in lst and v != "none":
            self.dropped[f"not in list: {key}"] += 1
            return False
        if len(v) > tp.VAL_MAX or len(key) + len(v) > tp.REC_MAX:
            self.dropped[f"over budget: {key}"] += 1
            return False
        if self.has(system, attr) and not overwrite:
            return False
        if not self.has(system, attr) and self.n() >= SEED_MAX_RECORDS:
            self.dropped["record cap"] += 1
            return False
        self.d.setdefault(system, {})[attr] = v
        return True

    def relate(self, a, rel: str, b) -> bool:
        a, b, rel = clean(a), clean(b), clean(rel)
        if rel not in tp.RELATIONS:
            self.dropped[f"relation not in list: {rel}"] += 1
            return False
        if not a or not b or a == b:
            return False
        key_len = len("rel9 a")
        if max(len(a), len(b)) > tp.VAL_MAX or key_len + max(len(a), len(b), len(rel)) > tp.REC_MAX:
            self.dropped["over budget: relation"] += 1
            return False
        r = {"a": a, "rel": rel, "b": b}
        if r in self.rels:
            return False
        if len(self.rels) >= MAX_RELATIONS or self.n() >= SEED_MAX_RECORDS:
            self.dropped["relation cap"] += 1
            return False
        self.rels.append(r)
        return True

    def spec(self) -> dict:
        out = {s: dict(a) for s, a in self.d.items() if a}
        if self.rels:
            out["relation"] = [dict(r) for r in self.rels]
        return out


def check_spec(spec: dict) -> list:
    """The spec's problems (empty when it passes): rule 2 of the row validator on the records, no interpretive system, the record
    count. The whole seed then passes the dataset's own gate, validate_seed, in make_seed."""
    p = []
    for system, attrs in spec.items():
        if system in INTERPRETIVE:
            p.append(f"interpretive system {system!r} in a seed")
        elif system == "relation":
            for r in attrs or []:
                if not isinstance(r, dict) or set(r) != {"a", "rel", "b"}:
                    p.append(f"a relation needs exactly a, rel, b: {r!r}")
                elif r["rel"] not in tp.RELATIONS:
                    p.append(f"relation {r['rel']!r} not in the list")
        elif system not in tp.SYSTEMS:
            p.append(f"unknown system {system!r}")
        else:
            for a in attrs:
                if f"{system} {a}" not in KEYS:
                    p.append(f"unknown key {system} {a}")
    for k, v in tp.records(spec):
        if not isinstance(v, str) or not v or v != clean(v):
            p.append(f"value of {k!r} is not plain lower-case ASCII: {v!r}")
        elif len(v) > tp.VAL_MAX or len(k) + len(v) > tp.REC_MAX:
            p.append(f"record {k!r} = {v!r} over the budget")
        if len(k) > tp.KEY_MAX:
            p.append(f"key {k!r} over {tp.KEY_MAX} bytes")
        lst = closed_list(k)
        if lst is not None and v not in lst and v != "none":
            p.append(f"value of {k!r} not in its closed list: {v!r}")
    n = tp.n_records(spec)
    if not 1 <= n <= SEED_MAX_RECORDS:
        p.append(f"{n} records (a seed holds 1-{SEED_MAX_RECORDS})")
    return p


def sealed(spec: dict) -> list:
    return tp.sealed_used(tp.records(spec), HELD)


def strip_sealed(spec: dict) -> dict:
    """The spec without every record whose value is sealed (a relation goes whole when its rel or an end is sealed; the thing goes
    whole when its name is sealed, so no count, colour or position is left without the thing it describes)."""
    out = {}
    for system, attrs in spec.items():
        if system == "thing" and tp.sealed_used([("thing name", attrs.get("name", ""))], HELD):
            continue
        if system == "relation":
            keep = []
            for i, r in enumerate(attrs, 1):
                recs = [(f"rel{i} a", r["a"]), (f"rel{i} rel", r["rel"]), (f"rel{i} b", r["b"])]
                if not tp.sealed_used(recs, HELD):
                    keep.append(r)
            if keep:
                out["relation"] = keep
        else:
            kept = {a: v for a, v in attrs.items() if not tp.sealed_used([(f"{system} {a}", v)], HELD)}
            if kept:
                out[system] = kept
    return out


def held_pick(seed_id: str, percent: int = HELD_PERCENT) -> bool:
    """A stable draw by the seed's id: the seeds that use a sealed value and fall in this share stay whole for the held split."""
    return int(hashlib.sha1(seed_id.encode("utf-8")).hexdigest()[:8], 16) % 100 < percent


def route(seed_id: str, spec: dict, group: str | None = None) -> tuple:
    """-> (spec, held). A spec without sealed values is a training seed; with them, a stable tenth stays whole as a held seed and
    the rest lose the sealed records (a training row never carries a sealed value). `group`: the picture's own id when two sources
    describe the same picture (COCO captions and Localized Narratives), so both make the same held / training choice for it."""
    if not sealed(spec):
        return spec, False
    if held_pick(group or seed_id):
        return spec, True
    return strip_sealed(spec), False


# typographic punctuation to its ASCII form, before the fold drops what has no ASCII form (an en dash in a year span would vanish,
# '188889'; a curly apostrophe would turn "man's" into 'mans')
PUNCT = str.maketrans({**dict.fromkeys(map(chr, (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)), "-"),  # dashes, minus
                       **dict.fromkeys(map(chr, (0x2018, 0x2019, 0x201A, 0x201B)), "'"),                            # single quotes
                       **dict.fromkeys(map(chr, (0x201C, 0x201D, 0x201E, 0x201F)), '"'),                            # double quotes
                       chr(0x00D7): "x", chr(0x00BD): " 1/2", chr(0x00BC): " 1/4", chr(0x00BE): " 3/4"})          # times, fractions


def ascii_text(s: str) -> str:
    """Plain ASCII text: typographic dashes and quotes to their ASCII forms (PUNCT), then accents folded, any other non-ASCII
    character dropped, spaces collapsed."""
    s = unicodedata.normalize("NFKD", str(s).translate(PUNCT)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip()


_SENT = re.compile(r"(?<=[.!?])\s+")
_CAP = re.compile(r"\b[A-Z][a-z]+")
COMMON_CAPS = {"I", "The", "A", "An", "In", "On", "At", "This", "That", "These", "Those", "It", "Its", "He", "She", "They", "We",
               "His", "Her", "Their", "There", "Here", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
               "Behind", "Above", "Below", "To", "From", "With", "Without", "Under", "Over", "Near", "Next", "Left", "Right", "Front",
               "Back", "Top", "Bottom", "Center", "Centre", "Middle", "Several", "Many", "Some", "Each", "Both", "All", "Most",
               "Inside", "Outside", "Beside", "Between", "Along", "Across", "Around", "As", "And", "But", "Or", "If", "When",
               "While", "After", "Before", "During", "For", "Of", "By", "Is", "Are", "Was", "Were", "Be", "No", "Not", "Only",
               "Also", "Then", "Now", "Today", "Close", "Far", "Large", "Small", "Big", "Little", "Old", "New", "Young",
               "Black", "White", "Red", "Blue", "Green", "Yellow", "Brown", "Grey", "Gray", "Orange", "Pink", "Purple"}


_SHOUT = re.compile(r"\b[A-Z]{2,}\b")
COMMON_ACRONYMS = {"TV", "DVD", "CD", "PC", "ATM", "USB", "LED", "LCD", "UFO", "SUV", "BBQ", "OK", "ID", "AM", "PM", "DJ"}


def _shouting(s: str) -> bool:
    """A sentence written all in capitals (a caption typed in capitals): its names cannot be told from its words."""
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 8 and sum(c.isupper() for c in letters) > 0.8 * len(letters)


def _unnamed(s: str, ok: set) -> bool:
    """drop_named's test of one sentence: no capitalized word past its first word and no all-capitals word outside `ok`, and the
    sentence not written all in capitals."""
    if _shouting(s):
        return False
    words = s.split()
    caps = _CAP.findall(" ".join(words[1:]))
    shout = [w for w in _SHOUT.findall(s) if w not in COMMON_ACRONYMS and w != "I" and w not in ok]
    return all(c in ok for c in caps) and not shout


def drop_named(text: str, allow: set | None = None) -> str:
    """The text without every sentence that may hold a name: a capitalized word past its first word, or an all-capitals word that
    is not a common acronym (OMNI HOTELS, BNSF), or the whole sentence in capitals. The dataset carries no real person's name, so a
    sentence that may hold one is dropped whole. `allow`: extra capitalized or all-capitals words that are not names in this source
    (a culture word, a date mark such as BCE)."""
    ok = COMMON_CAPS | (allow or set())
    return " ".join(s for s in _SENT.split(str(text).strip()) if _unnamed(s, ok))


# ------------------------------------------------------------------ the strict name filter (opt in: the prose of a catalogue)
DATE_MARKS = {"BCE", "CE", "BC", "AD", "AH"}         # all-capitals words of a date, never a name
# words that are capitalized inside a name more than in plain prose: never taken for a plain word of a corpus
PARTICLES = {"de", "van", "von", "da", "di", "del", "della", "der", "den", "du", "le", "la", "el", "al", "ibn", "bin", "mac", "mc",
             "st", "saint", "san", "santa", "sir", "mr", "mrs", "ms", "dr", "madame", "monsieur", "mademoiselle", "signor", "don",
             "dona", "fra", "ser", "lord", "pope", "emperor", "empress", "king", "queen", "prince", "princess", "duke", "duchess",
             "count", "countess", "bishop", "cardinal", "father", "brother", "sister", "mother", "general", "captain", "colonel"}
# given names that are also plain words: a title or a corpus word list never takes them as plain
GIVEN_NAMES = {"rose", "lily", "violet", "daisy", "iris", "ivy", "holly", "hazel", "olive", "pearl", "ruby", "amber", "jasmine",
               "grace", "joy", "hope", "faith", "may", "june", "april", "august", "mark", "bill", "frank", "will", "jack", "guy",
               "dawn", "eve", "carol", "rob", "victor", "victoria", "georgia", "virginia", "florence", "sydney", "chase", "summer",
               "autumn"}
_ALLCAPS = re.compile(r"\b[A-Z]{2,}\b")
_ROMAN = re.compile(r"[IVXLC]+")
# a colour or plain adjective capitalized in the middle of a sentence is a name ('White', 'Brown', 'Young') or a place ('Black Sea')
_NAMEISH = re.compile(r"(?<![:\"'(/-] )(?<![:\"'(/-])\b(Black|White|Red|Blue|Green|Yellow|Brown|Grey|Gray|Orange|Pink|Purple|Young|"
                      r"Old|Little|Small|Large|Big|New|Close|Far)\b")


# a full stop after an initial or an abbreviation ends no sentence of catalogue prose: a split there would leave the name as a
# fragment of its own ('J. M. W. Turner', 'h. schulze', 'St. Francis', 'Mt. Fuji', 'ca. 1850')
ABBREVIATIONS = ("st", "ste", "mr", "mrs", "ms", "messrs", "mme", "mlle", "dr", "mt", "jr", "sr", "rev", "prof", "fr", "gen", "col",
                 "capt", "lt", "sgt", "hon", "ca", "no", "nos", "vol", "fig", "figs", "pl", "cat", "inv", "cf", "vs", "approx")
_NO_SPLIT = re.compile(r"(?:(?<![A-Za-z])[A-Za-z]|\b(?:" + "|".join(ABBREVIATIONS) + r"))\.$", re.I)
# words of a signature or an inscription: a sentence about one may hold the name it reads
INSCRIPTION = re.compile(r"\b(?:signatures?|signed|inscribed|inscriptions?|monogram(?:s|med)?|initial(?:l)?ed|initials)\b", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def sentences(text: str) -> list:
    """The sentences of a text: split after '.', '!' or '?' and a space, but not after an initial or an abbreviation
    (ABBREVIATIONS), so a name stays whole in the sentence it belongs to."""
    out = []
    for piece in _SENT.split(str(text or "").strip()):
        if out and _NO_SPLIT.search(out[-1]):
            out[-1] = f"{out[-1]} {piece}"
        elif piece:
            out.append(piece)
    return out


def _words(text: str) -> list:
    """The words of a text, a possessive "'s" taken off ("Church's" -> 'Church')."""
    return [re.sub(r"'s$", "", w) for w in _WORD.findall(text)]


def corpus_vocab(texts) -> set:
    """The plain words of a corpus, for drop_named_strict: a word seen in lower case at least twice and more often in lower case
    than capitalized in the middle of a sentence ('perhaps', 'potter'), never a particle, a title of address or a given name."""
    low, cap = Counter(), Counter()
    for t in texts:
        for sent in sentences(ascii_text(t or "")):
            for w in _words(sent)[1:]:
                if w[0].isupper():
                    cap[w.lower()] += 1
                elif w.islower():
                    low[w] += 1
    return {w for w, n in low.items() if n >= 2 and n > cap[w] and w not in PARTICLES and w not in GIVEN_NAMES}


# words of a name field that name no one: particles and titles of address ('King', 'Saint'), roles, firms, ordinals ('Workshop
# of', 'and Sons', '19th Century')
NAME_SKIP = frozenset((
    "and of the a an to by for in on at with after from or as de del della dei degli van von der den ten ter du le la les el al "
    "da di dos das do st ste saint san santa jr sr ii iii iv vi vii viii artist artists attributed workshop studio circle follower "
    "followers school manner style possibly probably perhaps unknown anonymous master masters maker makers company co inc ltd llc "
    "corp sons son brothers bros published publisher publishers printed printer printers designed designer engraved engraver "
    "etched etcher lithographer issued active born died dated century th nd rd press manufactory manufacturing factory works "
    "gallery editions edition copy copyist imitator imitation pupil assistant shop").split()) | frozenset(PARTICLES)


def lower_words(text: str) -> list:
    """The words a text writes in lower case, anywhere in it ('may', 'church'; a possessive "'s" taken off)."""
    return [re.sub(r"'s$", "", w) for w in re.findall(r"\b[a-z][a-z'-]*", ascii_text(text or ""))]


def plain_words(texts, min_count: int = 2) -> set:
    """The ordinary words of a source: every word it writes in lower case (lower_words) at least `min_count` times. A name is
    written capitalized ('Wedgwood', 'Chippendale' are never lower case in a catalogue), so a name word of the source's list
    that is also one of these ('church', 'may', 'wood') is an ordinary word as well (NameList)."""
    low = Counter()
    for t in texts:
        low.update(lower_words(t))
    return {w for w, n in low.items() if n >= min_count}


_NAME_WORD = re.compile(r"(?<![\w'-])[A-Za-z][A-Za-z'-]*")      # a whole word ('18th-century' holds none)


def name_tokens(values, skip=frozenset()) -> set:
    """The lower-case words of name fields (artist, maker, constituent, sitter) that may stand for a person in a text: every
    word of three letters or more and each part of a hyphenated one, without NAME_SKIP and `skip` (culture words)."""
    out = set()
    for v in values:
        for w in (re.sub(r"'s$", "", w) for w in _NAME_WORD.findall(ascii_text(v or ""))):
            w = w.lower().strip("'-")
            for t in [w] + (w.split("-") if "-" in w else []):
                if len(t) > 2 and t not in NAME_SKIP and t not in skip:
                    out.add(t)
    return out


class NameList:
    """The name words of a source's own artist / maker / constituent / sitter fields (name_tokens), held for the hint test in two
    parts by the source's plain words (plain_words): a word that is not one of them ('schulze', 'chippendale') counts in any
    case; a word that is also an ordinary word ('church', 'wood', 'may') counts, with `opening`, only as a sentence's capitalized
    first word (in lower case it is the ordinary word, and capitalized past the first word drop_named takes it already).
    `openers`: words that count only that way whatever they are, the words of a record's title or subject terms that may name
    someone or somewhere ('Adirondacks', 'Napoleon'; in lower case they are ordinary words: 'guardhouse', 'chariots')."""

    def __init__(self, tokens, plain=frozenset(), openers=()):
        self.plain = plain
        self.rare = frozenset(t for t in tokens if t not in plain)
        self.common = frozenset(t for t in tokens if t in plain) | frozenset(openers)

    def __bool__(self) -> bool:
        return bool(self.rare or self.common)

    def hits(self, text: str, opening: bool = True) -> bool:
        """Whether `text` holds a name word (with `opening`, also a plain-word name as the capitalized first word)."""
        words = _words(text)
        if any(w.lower() in self.rare for w in words):
            return True
        return opening and bool(words) and words[0][0].isupper() and words[0] not in COMMON_CAPS and \
            words[0].lower() in self.common


def holds_name(text: str, names: NameList | None = None, own: NameList | None = None, opening: bool = True) -> bool:
    """Whether `text` holds a name of the source's list (`names`: a word that is not an ordinary word of the source) or of the
    record's own names (`own`: its artist, maker or sitter, the name words of its title; with `opening`, an ordinary-word name
    as the capitalized first word too: 'Church's considerable skills ...' of a painting by Church)."""
    return (names is not None and names.hits(text, False)) or (own is not None and own.hits(text, opening))


def _text_names(sents: list, ok: set) -> set:
    """The words a text writes as names: capitalized past a sentence's first word ('Gabriel Salmon', 'Although Church ...') or
    in capitals ('F. E. CHURCH'), other than the common capitals and the allowed words."""
    named = set()
    for s in sents:
        rest = " ".join(s.split()[1:])
        named.update(w for w in _CAP.findall(rest) if w not in COMMON_CAPS and w not in ok)
        named.update(m.group(1) for m in _NAMEISH.finditer(rest))                # 'Mr. Brown', 'Mrs. White'
        named.update(w.title() for w in _ALLCAPS.findall(s) if w not in ok and w not in COMMON_ACRONYMS)
    return named


def drop_named_strict(text: str, vocab: set, allow: set | None = None, names: NameList | None = None,
                      own: NameList | None = None) -> str:
    """drop_named for catalogue prose, where a sentence often opens with a name, on the sentences of `sentences` (an initial or
    'St.' keeps its name in its sentence). Dropped besides drop_named's: every sentence whose first word is capitalized and not a
    plain word of the corpus (`vocab`, from corpus_vocab; '<Name> painted the street.' passes drop_named) or is a word the same text
    writes as a name ('Gabriel Salmon ... Salmon emphasized'); every sentence that opens in lower case (a fragment); every sentence
    ending on an initial ('J.'); every sentence with a colour or plain adjective capitalized past its first word; every sentence
    with an all-capitals word (an inscription or a signature) other than a date mark or a Roman numeral; every sentence holding
    quoted text or the words of a signature or an inscription; and every sentence holding a name of the source's own name fields
    (`names`) or of this record's own names (`own`), both NameLists (holds_name)."""
    t = ascii_text(text or "")
    ok = (allow or set()) | DATE_MARKS | {w for w in _ALLCAPS.findall(t) if _ROMAN.fullmatch(w)}
    sents = sentences(t)
    named = _text_names(sents, ok)
    keep = []
    for sent in sents:
        if not _unnamed(sent, COMMON_CAPS | ok):
            continue
        w = re.match(r"\W*([A-Za-z][\w'-]*)", sent)
        if not w:
            continue
        base = re.sub(r"'s$", "", w.group(1))
        if base[0].islower() or base in named:
            continue
        if base not in COMMON_CAPS and base.lower() not in vocab:
            continue
        if re.search(r"\b[A-Z]\.\s*$", sent):
            continue
        if _NAMEISH.search(sent[w.end():]):
            continue
        if any(c not in DATE_MARKS and not _ROMAN.fullmatch(c) for c in _ALLCAPS.findall(sent)):
            continue
        if '"' in sent or INSCRIPTION.search(sent) or holds_name(sent, names, own):
            continue
        keep.append(sent.strip())
    return " ".join(k for k in keep if k)


# ------------------------------------------------------------------ text that speaks of the picture as an image (opt in)
_IMG = r"(?:image|picture)"
_IMG_VERB = r"(?:shows|depicts|displays|features|portrays|illustrates|presents|captures|contains|showcases|reveals)"
# a lead-in that names the image as the subject ('The image shows a jug', 'In this image, a man ...', 'An image of a kitten ...'):
# it goes, the rest stays
IMAGE_LEAD = re.compile(rf"^(?:in (?:the|this) {_IMG},? |(?:the|this) {_IMG} {_IMG_VERB} |(?:the|this) {_IMG} is (?=an? )|"
                        rf"an? {_IMG} (?:of|showing) (?=an?\b|the\b|two\b|three\b|four\b|five\b|several\b|many\b|some\b))", re.I)
# what still speaks of the image or its file after that: the sentence goes whole
IMAGE_TALK = re.compile(rf"\bthis {_IMG}\b|\b(?:the|this) {_IMG} (?:{_IMG_VERB}|consists)\b|^(?:the|an?) {_IMG}\b|"
                        rf"\bin this {_IMG}\b|\b(?:high|low|full)[- ]resolution\b|\bresolution (?:image|scan|file|photo\w*|version)\b|"
                        r"\bimage (?:file|resolution)\b|\bdigital (?:image|file|scan)\b", re.I)


def without_image_talk(text: str) -> str:
    """The text with a sentence's lead-in that speaks of the image as an image taken off ('The image shows a jug with a lid.' ->
    'A jug with a lid.') and every sentence that still speaks of the image or its file dropped ('In this image the artist ...' after
    its lead-in is fine; 'This image is one of a set.', 'a high resolution scan' and the dataset gate's phrases, 'the pixels of
    the sky', are not: the sentence goes, not the seed)."""
    out = []
    for s in sentences(text):
        m = IMAGE_LEAD.match(s)
        if m:
            rest = s[m.end():].lstrip()
            s = rest[:1].upper() + rest[1:]
        if s and not IMAGE_TALK.search(s) and not tp.speaks_of_the_file(s):
            out.append(s)
    return " ".join(out)


def make_hint(parts, limit: int = HINT_MAX) -> str:
    """The hint: source sentences, each once, ASCII, joined and cut at a sentence boundary within `limit` bytes."""
    out, seen = [], set()
    for p in parts:
        t = ascii_text(p)
        if not t:
            continue
        if t[-1] not in ".!?":
            t += "."
        key = t.lower()
        if key in seen:
            continue
        if len(" ".join(out + [t])) > limit:
            if not out:                                     # a single long text: cut at the last sentence end inside the limit
                cut = t[:limit]
                j = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
                if j > limit // 3:
                    out.append(cut[:j + 1])
            break
        seen.add(key)
        out.append(t)
    return " ".join(out)


ADULT_AGES = {"20s", "30s", "40s", "50s", "60s", "elderly", "young adult"}
YOUNG_AGES = {"child", "baby", "teen"}
COHERED: Counter = Counter()                        # cohere()'s removals by reason (the build prints them per source)


def cohere(spec: dict) -> dict:
    """Facts that cannot all be true of ONE picture's subject, removed (every source): an age needs exactly one person (an age of
    'someone in the picture' says nothing of the subject: 'two men ... one of them is a kid'), and an age must fit the gender word."""
    p = spec.get("person")
    if not p or "age" not in p:
        return spec
    g, a = p.get("gender"), p["age"]
    why = None
    if p.get("count") != "1":
        why = "age without exactly one person"
    elif (g in ("boy", "girl") and a in ADULT_AGES) or (g in ("man", "woman") and a in YOUNG_AGES):
        why = "age against the gender word"
    if why:
        COHERED[why] += 1
        spec = {k: dict(v) if isinstance(v, dict) else v for k, v in spec.items()}
        del spec["person"]["age"]
        if not spec["person"]:
            del spec["person"]
    return spec


def make_seed(dataset: str, sid: str, domain: str, genre: str, spec: Spec | dict, hint: str, license: str, url: str,
              min_records: int = 1, group: str | None = None) -> dict | None:
    """The seed object (the contract's fields), routed by the seal; None when the spec is empty or fails the checks. `group`: the
    picture's own id when another source describes the same picture (route)."""
    if domain not in DOMAINS:
        raise ValueError(f"domain {domain!r}")
    seed_id = f"{dataset}:{sid}"
    raw = cohere(spec.spec() if isinstance(spec, Spec) else spec)
    s, held = route(seed_id, raw, group)
    if tp.n_records(s) < min_records:
        REJECTED["too few records"] += 1
        return None
    probs = check_spec(s)
    if probs:
        REJECTED[f"spec: {probs[0]}"[:90]] += 1
        return None
    out = {"seed_id": seed_id, "domain": domain, "genre": clean(genre)[:24] or domain, "spec": s}
    if hint:
        out["hint"] = hint[:HINT_MAX]
    out["source"] = {"dataset": dataset, "id": str(sid), "license": license, "url": url}
    out["held"] = held
    if hasattr(tp, "validate_seed"):                 # the dataset's gate: the contract, the license, the seal
        probs = list(tp.validate_seed(out, HELD))
        if probs:
            REJECTED[f"gate: {probs[0]}"[:90]] += 1
            return None
    return out


class Shards:
    """seeds/<source>/<source>-NNNNN.jsonl under `root`, `size` lines a shard, plus seeds/<source>/stats.json on close."""

    def __init__(self, root: str, source: str, size: int = 10000):
        self.dir = os.path.join(root, "seeds", source)
        os.makedirs(self.dir, exist_ok=True)
        self.source, self.size = source, size
        self.n, self.fh, self.shard = 0, None, -1
        self.stats = dict(seeds=0, held=0, by_domain=Counter(), by_genre=Counter(), records=Counter(), keys=Counter(),
                          with_hint=0, relations=0)

    def add(self, seed: dict) -> None:
        if self.n % self.size == 0:
            if self.fh:
                self.fh.close()
            self.shard += 1
            self.fh = open(os.path.join(self.dir, f"{self.source}-{self.shard:05d}.jsonl"), "w", encoding="utf-8", newline="\n")
        self.fh.write(json.dumps(seed, ensure_ascii=True, separators=(",", ":")) + "\n")
        self.n += 1
        st = self.stats
        st["seeds"] += 1
        st["held"] += bool(seed["held"])
        st["by_domain"][seed["domain"]] += 1
        st["by_genre"][seed["genre"]] += 1
        st["records"][tp.n_records(seed["spec"])] += 1
        st["with_hint"] += bool(seed.get("hint"))
        st["relations"] += len(seed["spec"].get("relation", []))
        for k, _ in tp.records(seed["spec"]):
            st["keys"][re.sub(r"^rel\d+ ", "rel ", k)] += 1

    def close(self, extra: dict | None = None) -> dict:
        if self.fh:
            self.fh.close()
        st = dict(self.stats)
        for k in ("by_domain", "records", "keys"):
            st[k] = dict(sorted(st[k].items(), key=lambda kv: (-kv[1], str(kv[0])) if k != "records" else (kv[0], 0)))
        st["by_genre"] = dict(st["by_genre"].most_common(40))
        st["shards"] = self.shard + 1
        st["tools"] = tp.VERSION
        if extra:
            st.update(extra)
        with open(os.path.join(self.dir, "stats.json"), "w", encoding="utf-8") as fh:
            json.dump(st, fh, indent=1)
        return st
