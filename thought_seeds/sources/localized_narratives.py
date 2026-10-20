"""thought_seeds.sources.localized_narratives - Localized Narratives on COCO 2017 -> hidden picture specs.

The official captions-only files (coco_val_captions.jsonl, coco_train_captions.jsonl: the narration text without the mouse traces,
the timing or the voice) give one long spoken description per image and annotator. A seed is keyed by the COCO image id; its
records are read from the narration by the word maps, taking a value only when the text gives exactly one value for that key
(and, for an image with several narrations, only when two of them agree); the hint is the image's longest narration without any
sentence that may hold a name. No image, trace or recording is downloaded."""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict

from .. import core, maps
from . import coco as C

DATASET = "localized_narratives"
LICENSE = "CC BY 4.0"
URL = "https://google.github.io/localized-narratives/"
ATTRIBUTION = ("Localized Narratives (Pont-Tuset, Uijlings, Changpinyo, Soricut and Ferrari, ECCV 2020), CC BY 4.0; the COCO 2017 "
               "narration texts only (no traces, voice or images)")
CITATION = r"""@inproceedings{PontTuset_eccv2020,
  author    = {Jordi Pont-Tuset and Jasper Uijlings and Soravit Changpinyo and Radu Soricut and Vittorio Ferrari},
  title     = {Connecting Vision and Language with Localized Narratives},
  booktitle = {ECCV},
  year      = {2020}
}"""
TAKEN = ("records + hint: person, wear, body, scene and shot facts, the first named object (name, count, colour, state, position) "
         "and relations read from the narration where the phrase gives one value (two narrations agree when an image has several); "
         "hint = the image's longest narration without any sentence holding a capitalized name")

BASE = "https://storage.googleapis.com/localized-narratives/annotations/"
FILES = (("coco_val_captions.jsonl", 2492374), ("coco_train_captions.jsonl", 40295105))
EXPLORE = "https://cocodataset.org/#explore?id={}"

STATS: Counter = Counter()


def fetch(raw_dir: str) -> dict:
    """The two captions-only files (2.4 MB + 40 MB) into raw_dir/localized_narratives/; skipped when present at their size."""
    d = os.path.join(raw_dir, DATASET)
    os.makedirs(d, exist_ok=True)
    out = {}
    for name, size in FILES:
        path = os.path.join(d, name)
        if not (os.path.exists(path) and os.path.getsize(path) == size):
            C._download(BASE + name, path)
        out[name] = os.path.getsize(path)
    return out


# ------------------------------------------------------------------ words
SUPER = {"bicycle": "vehicle", "car": "vehicle", "motorcycle": "vehicle", "airplane": "vehicle", "bus": "vehicle", "train": "vehicle",
         "truck": "vehicle", "boat": "vehicle", "traffic light": "outdoor", "fire hydrant": "outdoor", "stop sign": "outdoor",
         "parking meter": "outdoor", "bench": "outdoor", "backpack": "accessory", "umbrella": "accessory", "handbag": "accessory",
         "tie": "accessory", "suitcase": "accessory", "frisbee": "sports", "skis": "sports", "snowboard": "sports",
         "sports ball": "sports", "kite": "sports", "baseball bat": "sports", "baseball glove": "sports", "skateboard": "sports",
         "surfboard": "sports", "tennis racket": "sports", "bottle": "kitchen", "wine glass": "kitchen", "cup": "kitchen",
         "fork": "kitchen", "knife": "kitchen", "spoon": "kitchen", "bowl": "kitchen", "banana": "food", "apple": "food",
         "sandwich": "food", "orange": "food", "broccoli": "food", "carrot": "food", "hot dog": "food", "pizza": "food",
         "donut": "food", "cake": "food", "chair": "furniture", "couch": "furniture", "potted plant": "furniture", "bed": "furniture",
         "dining table": "furniture", "toilet": "furniture", "tv": "electronic", "laptop": "electronic", "mouse": "electronic",
         "remote": "electronic", "keyboard": "electronic", "cell phone": "electronic", "microwave": "appliance",
         "oven": "appliance", "toaster": "appliance", "sink": "appliance", "refrigerator": "appliance", "book": "indoor",
         "clock": "indoor", "vase": "indoor", "scissors": "indoor", "teddy bear": "indoor", "hair drier": "indoor",
         "toothbrush": "indoor"}
SUPER.update({a: "animal" for a in C.ANIMALS})

# the narration's object words -> (the spec's name, the category it names or '' for a word outside the 80)
OBJ = {}
for _cat, (_name, _ws) in C.CATS.items():
    for _w in C._words(_ws):
        if _w in ("bike", "bikes", "skiing", "snowboarding", "skateboarding", "surfing", "plant", "plants", "screen", "screens",
                  "glove", "gloves", "bat", "bats", "meter", "meters", "sub", "lab", "labs", "calf"):
            continue                  # a bike is a bicycle or a motorcycle; 'plants' outdoors are not potted plants; the rest name acts
        OBJ[_w] = (_name if _cat != "tv" else ("monitor" if _w.startswith("monitor") else "television"), _cat)
OBJ.update({"cycle": ("bicycle", "bicycle"), "cycles": ("bicycle", "bicycle"), "motor bike": ("motorcycle", "motorcycle"),
            "motorbikes": ("motorcycle", "motorcycle"), "mobile": ("phone", "cell phone"), "mobiles": ("phone", "cell phone"),
            "mobile phone": ("phone", "cell phone"), "sofa": ("couch", "couch"), "surfing board": ("surfboard", "surfboard"),
            "surfing boat": ("surfboard", "surfboard"), "surfing boards": ("surfboard", "surfboard"),
            "skating board": ("skateboard", "skateboard"), "baseball glove": ("baseball glove", "baseball glove"),
            "baseball bat": ("baseball bat", "baseball bat"), "parking meter": ("parking meter", "parking meter"),
            "plant": ("plant", ""), "plants": ("plant", ""), "screen": ("screen", ""), "helicopter": ("helicopter", ""),
            "bag": ("bag", ""), "bags": ("bag", ""), "doll": ("doll", ""), "house": ("house", ""), "houses": ("house", "")})
for _w, _n in C.CAPTION_THINGS.items():
    OBJ.setdefault(_w, (_n, ""))
OBJ_M = C._M(OBJ)
PLURAL_OBJ = {w for w in OBJ if w.endswith("s") and (w[:-1] in OBJ or w[:-2] in OBJ or w[:-3] + "y" in OBJ)} | {
    "knives", "geese", "oxen", "calves", "teddies", "ferries", "kitties", "skis", "scissors", "luggage", "cattle", "broccoli"}
PERSON_M = C.PERSON_M
PLURAL_PERSON = {"men", "women", "people", "persons", "boys", "girls", "children", "kids", "babies", "toddlers", "guys", "ladies",
                 "gentlemen", "teens", "teenagers", "adults", "players", "skiers", "surfers", "skateboarders", "snowboarders",
                 "riders", "bikers", "cyclists", "chefs", "cooks", "workers", "officers", "policemen", "soldiers", "students",
                 "athletes", "tourists", "friends", "spectators", "fans", "passengers", "pedestrians", "vendors", "farmers",
                 "musicians", "dancers", "businessmen", "individuals", "couple", "family", "crowd", "team"}
PRONOUNS = {"he", "she", "someone", "somebody"}
COUNT_WORDS = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
               "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8", "9": "9", "10": "10", "a pair of": "2",
               "a couple of": "2", "couple of": "2", "many": "many", "lots of": "many", "a lot of": "many", "lot of": "many",
               "a crowd of": "many", "crowd of": "many", "group of": "several", "a group of": "several", "herd of": "several",
               "a herd of": "several", "flock of": "several", "a flock of": "several", "bunch of": "several",
               "a bunch of": "several", "few": "few", "a few": "few", "several": "several"}
COUNT_M = C._M(COUNT_WORDS)
SINGLE = re.compile(r"\b(?:a|an|one|the single)\s+$")
ANOTHER_PERSON = re.compile(r"\b(?:another|other|second|one more)\s+(?:[a-z]+\s+)?(?:" + "|".join(
    re.escape(w) for w in sorted(C.PERSON_WORDS, key=len, reverse=True)) + r")\b|\bboth of them\b")
ANGLE = {"aerial view": "overhead", "top view": "overhead", "overhead view": "overhead", "bird's eye view": "overhead",
         "birds eye view": "overhead", "top down view": "overhead", "low angle": "low angle", "high angle": "high angle",
         "eye level": "eye level", "worm's eye view": "worm's eye"}       # 'side view' in a narration is a road side, not a profile
ROLE_ACTS = dict(C.ROLE_ACTS)
ROLE_ACTS.update({"playing a tennis game": "athlete", "playing tennis game": "athlete", "playing a baseball game": "athlete",
                  "playing baseball game": "athlete", "playing a football game": "athlete", "riding the horse": "rider",
                  "riding a cycle": "rider", "riding the bicycle": "rider", "riding the motorcycle": "rider",
                  "sitting on a horse": "rider", "sitting on the horse": "rider", "on the horse": "rider", "on a horse": "rider"})
ACCESSORY = dict(C.ACCESSORY)
ACCESSORY.update({"spectacles": "glasses", "spectacle": "glasses", "specs": "glasses", "sunglasses": "glasses", "goggles": "glasses",
                  "cap": "cap", "caps": "cap", "watch": "watch"})            # 'wearing a watch' is how the narrations say it
FOCUS = dict(maps.FOCUS)
FOCUS.update({"blurred background": "shallow", "background is blurred": "shallow", "blurry background": "shallow",
              "background is blurry": "shallow", "blur background": "shallow", "background is blur": "shallow",
              "background is in blur": "shallow", "background is slightly blurred": "shallow"})
PALETTE = dict(C.PALETTE)
PALETTE.update({"black and white image": "black and white", "black and white picture": "black and white",
                "black and white photo": "black and white", "this is a black and white": "black and white"})
SPATIAL = {"behind": "behind", "in front of": "in front of", "beside": "beside", "next to": "beside", "under": "under",
           "below": "below", "beneath": "under", "underneath": "under", "above": "above", "to the left of": "left of",
           "on the left of": "left of", "to the right of": "right of", "on the right of": "right of", "inside": "inside",
           "inside of": "inside", "leaning on": "leaning on", "leaning against": "leaning on", "holding": "holding",
           "looking at": "looking at", "watching": "looking at"}
SPATIAL_M = C._M(SPATIAL)
DET = {"a", "an", "the", "this", "that", "these", "those", "his", "her", "their", "its", "some", "two", "three", "few", "many",
       "white", "black", "small", "big", "large", "little", "tall", "red", "blue", "green", "brown", "yellow", "grey", "gray"}
BRIDGE = {"is", "are", "standing", "sitting", "placed", "kept", "parked", "lying", "which", "who", "that", "there", "and", "also",
          "visible", "present", "seen", "located", "it", "they", "walking", "moving", "hanging", "attached", "stands", "sits"}
INTRO = re.compile(r"^,?\s*(?:there (?:is|are)|we can (?:also )?see|i can (?:also )?see|we (?:can )?see|i see|we have|i can find|"
                   r"we can find|it is|is|are)\s+(?:(?:a|an|the|one|two|three|four|some|few|many)\s+)?")
POS_BEFORE = re.compile(r"\b(?:on|at|to|in) the (left|right)(?: side| corner| bottom| top| bottom corner| top corner| hand side| most)?"
                        r"(?: side| corner)?(?: of (?:the|this) (?:image|picture|photo|photograph|frame))?,?\s*(?:there (?:is|are)\s+|"
                        r"we can (?:also )?see\s+|i can (?:also )?see\s+|we see\s+|i see\s+|we have\s+)?"
                        r"(?:(?:a|an|the|one|two|three|some|few)\s+)?(?:[a-z]+\s+)?$")
POS_AFTER = re.compile(r"^(?:\s+(?:is|are))?(?:\s+(?:visible|present|seen|placed|kept|parked|standing|sitting|located))?"
                       r"\s+(?:on|at|to|in) the (left|right)(?: side| corner| bottom| top| hand side)?"
                       r"(?: side| corner)?(?:(?: of (?:the|this) (?:image|picture|photo|photograph|frame))|(?=\s*[.,]|\s*$))")
POS_CENTRE = re.compile(r"\b(?:in|at) the (?:middle|centre|center) of (?:the|this) (?:image|picture|photo|photograph|frame),?\s*(?:there (?:is|are)"
                        r"\s+|we can (?:also )?see\s+|i can (?:also )?see\s+|we see\s+|i see\s+)?(?:(?:a|an|the|one|two)\s+)?"
                        r"(?:[a-z]+\s+)?$")


def _sentences(text: str) -> list:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


_CLAUSE = re.compile(r"[.!?;,]+|\band\b(?= (?:in|on|at|to|behind|there|we|i|here|this|these|beside|near|above|below)\b)")


def _clauses(text: str) -> list:
    """(start, end) of each clause: the narrations run one sentence for a whole picture, joined by commas and 'and in the ...'."""
    out, last = [], 0
    for m in _CLAUSE.finditer(text):
        out.append((last, m.start()))
        last = m.end()
    out.append((last, len(text)))
    return [(s, e) for s, e in out if text[s:e].strip()]


class _Text(C._Cap):
    """One narration: the COCO caption reader (scrubbed text, person words, category words) plus the narration's object words."""

    def __init__(self, text: str):
        super().__init__(text)
        self.objs = OBJ_M.iter(self.t)                         # [(start, end, (name, category))]
        nouns = [n for n in self.nouns if n[2] == "person"] + [(s, e, ("obj", v)) for s, e, v in self.objs]
        nouns.sort(key=lambda n: n[0])
        self.nouns = nouns
        self.starts = [n[0] for n in nouns]


def _one(values) -> str | None:
    vals = set(values)
    return vals.pop() if len(vals) == 1 else None


def _bound(x: _Text, mapping: dict) -> list:
    return [v for p, _, v in C._m(mapping).iter(x.t) if x.subject(p) == "person"]


def _end_name(x: _Text, s: int, e: int, kind):
    if kind == "person":
        w = x.t[s:e]
        return None if w in PRONOUNS else C.GENDER.get(w, "person")
    return kind[1][0]


def facts(text: str, may_hold: bool) -> dict:
    """The records one narration gives: {(system, attr): value} and 'relation': [(a, rel, b)], each where the text is unambiguous."""
    x = _Text(text)
    f = {}
    if C.EXPLICIT.search(x.t):
        return {"explicit": True}
    t = x.t
    pmentions = [(s, e, t[s:e]) for s, e, k in x.nouns if k == "person"]
    words = [w for _, _, w in pmentions]
    # --- the person: an explicit number, or one single person named throughout
    count = gender = None
    if pmentions:
        counted, at = [], set()                 # 'two men', 'three persons', 'two man' (the narrations' own grammar)
        for s, e, w in pmentions:
            window = t[max(0, s - 24):s]
            pre = COUNT_M.iter(window)
            if pre and window[pre[-1][1]:].strip() in ("", *C.HUE, "young", "old", "little", "small"):
                counted.append((pre[-1][2], w))
                at.add(s)
        singular = [(s, w) for s, e, w in pmentions if s not in at and w not in PLURAL_PERSON and w not in PRONOUNS]
        loose_plural = [w for s, e, w in pmentions if s not in at and w in PLURAL_PERSON]
        introduced = Counter(w for s, w in singular if re.search(r"\b(?:a|an)\s+(?:[a-z]+\s+)?$", t[max(0, s - 20):s]))
        if counted:
            nums = {n for n, _ in counted}
            if len(nums) == 1 and not singular:           # 'the woman ... two people' may be three: no count
                count = nums.pop()
                g = {C.GENDER.get(w) for _, w in counted}
                others = {C.GENDER.get(w) for w in words if C.GENDER.get(w)}
                if len(g) == 1 and None not in g and others <= g:
                    gender = g.pop()
        elif "crowd" in words:
            count = "many"
        elif singular and not loose_plural and not ANOTHER_PERSON.search(t) and max(introduced.values(), default=0) <= 1:
            g = {C.GENDER.get(w, "person") for _, w in singular}
            if len(g - {"person"}) <= 1:
                count = "1"
                gender = _one(g - {"person"})
    if count:
        f[("person", "count")] = count
    if gender:
        f[("person", "gender")] = gender
    if pmentions:
        age = _one(v for p, e, v in C._m(C.AGE).iter(t) if not (x.animal and any(w in C.ANIMAL_SHARED for w in t[p:e].split())))
        role = _one([v for p, e, v in C._m(C.ROLE).iter(t) if not (x.animal and t[p:e] in C.ANIMAL_SHARED)]
                    + _bound(x, ROLE_ACTS))
        if age:
            f[("person", "age")] = age
        if role:
            f[("person", "role")] = role
        if count == "1":
            for key, mapping in ((("body", "pose"), C.POSE), (("body", "gesture"), C.GESTURE), (("wear", "clothing"), C.CLOTHING),
                                 (("wear", "accessory"), ACCESSORY), (("look", "expression"), C.EXPRESSION),
                                 (("look", "hair"), C.HAIR)):
                v = _one(_bound(x, mapping))
                if v:
                    f[key] = v
            garments = [(s, e, v) for s, e, v in C.GARMENT_M.iter(t) if x.subject(s) == "person"]
            wc = _one(_hue_of(x, garments))
            if wc:
                f[("wear", "colour")] = wc
    # --- the scene and the shot
    for key, mapping in ((("scene", "setting"), C.SETTING), (("scene", "time"), C.TIME), (("scene", "weather"), C.WEATHER),
                         (("shot", "framing"), C.FRAMING), (("shot", "angle"), ANGLE), (("shot", "light"), C.LIGHT),
                         (("shot", "focus"), FOCUS), (("form", "palette"), PALETTE)):
        v = _one(v for _, _, v in C._m(mapping).iter(t))
        if v:
            f[key] = v
    # --- the main object: the first object word of the first clause that is not about the background (a category first)
    main = None
    for start, end in _clauses(t):
        if re.search(r"\b(?:background|behind it|behind them|at the back)\b", t[start:end]):
            continue
        objs = [o for o in x.objs if start <= o[0] < end and (may_hold or not C._sealed_name(o[2][0]))]
        if objs:
            main = next((o for o in objs if o[2][1]), objs[0])
            break
    f["_food"] = any(SUPER.get(c) == "food" for _, _, (_, c) in x.objs)
    if main:
        name, cat = main[2]
        f[("thing", "name")] = name
        f["_cat"] = cat
        spans = [o for o in x.objs if o[2][0] == name]
        nums = []
        for s, e, _ in spans:
            pre = t[max(0, s - 24):s]
            cm = COUNT_M.iter(pre)
            if cm and pre[cm[-1][1]:].strip() in ("", *C.HUE, "small", "big", "large", "little"):
                nums.append(cm[-1][2])
            elif SINGLE.search(pre) and t[s:e] not in PLURAL_OBJ:
                nums.append("1")
        plural_seen = any(t[s:e] in PLURAL_OBJ for s, e, _ in spans)
        twice = nums.count("1") > 1                       # 'a car ... a car': two cars, each said of once
        n = _one(nums)
        if n and not (n == "1" and plural_seen) and not twice:
            f[("thing", "count")] = n
        if twice:
            spans = []                                    # which car is red, which is on the left: unknown; the name only
        elif n and n != "1":
            spans = [sp_ for sp_ in spans if t[sp_[0]:sp_[1]] in PLURAL_OBJ]    # 'a red car ... many cars': not many red cars
        col = _one(_hue_of(x, spans))
        if col and name != "orange":
            f[("thing", "colour")] = col
        kind = "animal" if cat in C.ANIMALS else "vehicle" if cat in C.VEHICLES else "object"
        st = _one(v for v in _states(x, spans, C.STATE_BY_KIND[kind]) if not any(v in vals for vals in core.HELD.values()))
        if st:
            f[("thing", "state")] = st
        p = []
        for s, e, _ in spans:
            m1 = POS_BEFORE.search(t[max(0, s - 90):s])
            m2 = POS_AFTER.match(t[e:e + 60])
            if m1:
                p.append(m1.group(1))
            if m2:
                p.append(m2.group(1))
            if POS_CENTRE.search(t[max(0, s - 90):s]):
                p.append("centre")
        v = _one(p)
        if v:
            f[("thing", "position")] = v
    if f.get(("wear", "accessory")) and f.get(("wear", "accessory")) == f.get(("thing", "name")):
        del f[("wear", "accessory")]                       # the umbrella is the picture's object already
    # --- relations the narration states between two named ends
    rels = []
    for rs, re_, rel in SPATIAL_M.iter(t):
        a = b = None
        i = next((k for k in range(len(x.nouns) - 1, -1, -1) if x.nouns[k][1] <= rs), None)
        if i is not None:
            gap = t[x.nouns[i][1]:rs].split()
            if len(gap) <= 3 and all(w in BRIDGE for w in gap) and not re.search(r"[,.;:]", t[x.nouns[i][1]:rs]):
                a = x.nouns[i]
        j = next((k for k in range(len(x.nouns)) if x.nouns[k][0] >= re_), None)
        if j is not None:
            gap = t[re_:x.nouns[j][0]].split()
            if len(gap) <= 2 and all(w in DET for w in gap) and not re.search(r"[,.;:]", t[re_:x.nouns[j][0]]):
                b = x.nouns[j]
        if b is not None and a is None and rel not in ("holding", "looking at"):
            m = INTRO.match(t[b[1]:])                         # 'behind the man there is a car' -> car behind man
            if m:
                k = next((k for k in range(len(x.nouns)) if x.nouns[k][0] == b[1] + m.end()), None)
                if k is not None:
                    a = x.nouns[k]
        if a is None or b is None:
            continue
        if rel in ("holding", "looking at") and a[2] != "person":
            continue
        na, nb = _end_name(x, *a), _end_name(x, *b)
        if not na or not nb or na == nb:
            continue
        if not may_hold and (C._sealed_name(na) or C._sealed_name(nb)):
            continue
        rels.append((na, rel, nb))
    if rels:
        f["relation"] = list(dict.fromkeys(rels))
    return f


def _hue_of(x: _Text, spans: list) -> list:
    """The colours said of the spans: right before the word ('a red car', 'a white color cap') or after it ('a bag of a brown color',
    'the car is red in color'); never a 'black and white' pair."""
    out = []
    t = x.t
    tint = ("color", "colour", "colored", "coloured")
    for s, e, _ in spans:
        w = t[max(0, s - 50):s].split()[-5:]
        w = [""] * (5 - len(w)) + w                       # w[-1] is the word right before the noun

        def paired(i):                                    # 'black and white': a colour joined to another colour
            return w[i - 1] in ("and", "or", "&") and w[i - 2] in C.HUE

        hue = None
        if w[-1] in C.HUE and not paired(-1):
            hue = w[-1]                                   # a red car
        elif w[-1] in tint and w[-2] in C.HUE and not paired(-2):
            hue = w[-2]                                   # a white color cap
        elif w[-2] in C.HUE and w[-1] not in C.STOP and w[-1] not in C.HUE and not paired(-2):
            hue = w[-2]                                   # a red sports car
        if hue:
            out.append(C.HUE[hue])
            continue
        m = re.match(r"^\s+(?:is |are )?(?:in |of )?(?:a |an )?([a-z]+) (?:in )?colou?r\b", t[e:e + 40])
        if m and m.group(1) in C.HUE:
            out.append(C.HUE[m.group(1)])                 # a bag of a brown color, the car is red in color
    return out


def _states(x: _Text, spans: list, states: dict) -> list:
    out = []
    t = x.t
    for s, e, v in C._m(states).iter(t):
        for ns, ne, _ in spans:
            if ns >= e and t[e:ns].split() == []:
                out.append(v)
            elif s >= ne and all(w in ("is", "are", "that", "which", "being", "all") for w in t[ne:s].split()) and \
                    len(t[ne:s].split()) <= 2:
                out.append(v)
    return out


GENRE = {"vehicle": "vehicle", "outdoor": "street", "animal": "animal", "accessory": "people", "sports": "sport", "kitchen": "food",
         "food": "food", "furniture": "interior", "electronic": "interior", "appliance": "interior", "indoor": "still life"}
NAME_GENRE = {"building": "architecture", "house": "architecture", "tower": "architecture", "clock tower": "architecture",
              "church": "architecture", "castle": "architecture", "lighthouse": "architecture", "bridge": "architecture",
              "barn": "architecture", "tree": "landscape", "flower": "botanical", "plant": "botanical", "sign": "street",
              "street sign": "street", "road sign": "street", "pole": "street", "statue": "street", "fountain": "street",
              "graffiti": "street", "mural": "street", "helicopter": "vehicle", "fire truck": "vehicle"}


def _genre(spec: dict, cat: str, food: bool) -> str:
    name = spec.get("thing", {}).get("name")
    has_people = "person" in spec
    if cat:
        g = GENRE.get(SUPER.get(cat, ""), "scene")
        if cat in C.WILD:
            return "wildlife"
        if cat == "kite":
            return "leisure"
        if SUPER.get(cat) == "sports" and has_people:
            return "sport"
        if SUPER.get(cat) == "kitchen" and not food:
            return "still life"
        if SUPER.get(cat) == "indoor" and has_people:
            return "interior"
        return g
    if name:
        return NAME_GENRE.get(name, "people" if has_people else "scene")
    return "people" if has_people else "scene"


# ------------------------------------------------------------------ the source
def build(image_id, narrations: list) -> dict | None:
    """The seed of one COCO image from its narrations (one or several annotators)."""
    narrations = [n for n in narrations if n and n.strip()]
    if not narrations:
        return None
    sid = str(image_id)
    seed_id = f"{DATASET}:{sid}"
    may_hold = core.held_pick(f"coco-image:{sid}")   # by the picture, as coco does
    fs = [facts(n, may_hold) for n in narrations]
    if any(f.get("explicit") for f in fs):
        STATS["explicit words"] += 1
        return None
    keys = [k for k in dict.fromkeys(k for f in fs for k in f if isinstance(k, tuple))]
    sp = core.Spec()
    order = [("person", "count"), ("thing", "name"), ("person", "gender"), ("person", "age"), ("person", "role"), ("thing", "count"),
             ("thing", "position"), ("thing", "colour"), ("thing", "state"), ("body", "pose"), ("body", "gesture"),
             ("wear", "clothing"), ("wear", "colour"), ("wear", "accessory"), ("look", "expression"), ("look", "hair")]
    keys = [k for k in order if k in keys] + [k for k in keys if k not in order]
    if len(fs) == 1:
        chosen = {k: fs[0][k] for k in keys}
        rels = fs[0].get("relation", [])
    else:                                                  # several annotators: a value two of them agree on, no tie
        chosen = {}
        name = C._vote([{f[("thing", "name")]} if ("thing", "name") in f else set() for f in fs])
        same = [f for f in fs if f.get(("thing", "name")) == name] if name else []
        for k in keys:
            pool = same if k[0] == "thing" else fs        # a thing's count, colour, state from the narrations that name it
            v = C._vote([{f[k]} if k in f else set() for f in pool])
            if v:
                chosen[k] = v
        rv = Counter(r for f in fs for r in set(f.get("relation", [])))
        rels = [r for r, n in rv.most_common() if n >= 2]
    thing_keys = [k for k in chosen if k[0] == "thing"]
    if thing_keys and ("thing", "name") not in chosen:
        for k in thing_keys:
            del chosen[k]                                  # a thing's count or colour without its name says nothing
    for (system, attr), v in chosen.items():
        sp.set(system, attr, v)
    for a, rel, b in rels[:4]:
        sp.relate(a, rel, b)
    name = chosen.get(("thing", "name"))
    cat = next((f["_cat"] for f in fs if name and f.get(("thing", "name")) == name and f.get("_cat")), "")
    longest = max(narrations, key=len)
    hint = core.make_hint(_sentences(core.drop_named(C.unshout(longest))))
    genre = _genre(sp.spec(), cat, any(f.get("_food") for f in fs))
    seed = core.make_seed(DATASET, sid, "photograph", genre, sp, hint, LICENSE, EXPLORE.format(sid), group=f"coco-image:{sid}")
    if seed is None:
        STATS["empty or failed check"] += 1
        return None
    for k, v in sp.dropped.items():
        STATS[f"dropped {k}"] += v
    return seed


def _read(path: str) -> dict:
    """{image_id: [narration, ...]} in file order; only the image id and the caption of each line are kept."""
    out = defaultdict(list)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[str(r["image_id"])].append(r.get("caption", ""))
    return out


def seeds(raw_dir: str, limit: int | None = None):
    """The seeds of the COCO narrations, val2017 first, then train2017 (an image whose narration holds an explicit word is skipped)."""
    STATS.clear()
    n = 0
    for name, _ in FILES:
        path = os.path.join(raw_dir, DATASET, name)
        if not os.path.exists(path):
            continue
        for image_id, narrations in _read(path).items():
            if limit is not None and n >= limit:
                return
            STATS["images"] += 1
            s = build(image_id, narrations)
            if s is not None:
                n += 1
                STATS["seeds"] += 1
                yield s
