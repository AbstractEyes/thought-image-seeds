"""thought_seeds.sources.wikidata - paintings and sculptures from Wikidata (structured data, CC0 1.0) as hidden picture specs.

The works: paintings (instance of Q3305213) with at least four depicts (P180) statements and sculptures (Q860861) with at least two,
the richest first, at most 20,000 in all. The facts: what each work depicts (with the quantity P1114, colour P462 and relative
position P2677 qualifiers), its genre (P136), movement (P135), material (P186) and inception (P571), English labels only.

Names never enter a seed: the creator is never queried; a depicted value whose English label holds a capital letter is a name and is
dropped; a depicted human individual (instance of Q5 or of Q20643955, a human biblical figure) is kept only as an anonymous figure,
'a woman' or 'a man' from its sex (P21), a girl or a boy only when its label says child; no age is read from a birth date (P569),
which serves only to withhold the gender of a sitter under 18 at the work's inception. Deities, mythological and fictional figures
are dropped whole. Works whose depicted labels or genres speak of sex, genitals or prostitution are left out, and so are works
that pair nudity with a child figure (a child, a putto, a sitter under 18 by the birth year). Typing of the
depicted values (person, animal, plant, artifact, clothing, body part, landscape feature, food, creature) comes from their subclass
and parent-taxon paths (P279 | P171) to a fixed set of roots; an activity, an event or an idea that this typing calls an artifact
('ice skating', 'prayer', 'philosophy') is never the thing.

The person count is set only when the source states it: one when exactly one person is depicted and nothing else depicted
suggests more (a group, a crowd, another figure), or the quantity (P1114) of the one depicted person class; the depicts statements
are never summed. The European era names (medieval, renaissance, baroque) are given only to a work whose country of origin (P495)
or culture (P2596) is European; without those statements a work gets no era name. A work held by a museum that is a source of its
own (the Met, the Art Institute of Chicago, the National Gallery of Art, the Cleveland Museum of Art) is routed with that museum's
seed id as its group, so the two seeds of one artwork land on the same side of the held split; the link comes from the museum
ids that Wikidata states (P3634, P4610, P4683) or from the Wikidata ids that the museums' own open data states.

fetch() runs paged SPARQL queries against the Wikidata Query Service (each a few seconds, well under its 60 s limit) and keeps every
result as JSON under raw/wikidata/; seeds() reads those files only (and, for the routing links, the museums' raw files when they
are present beside them)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import defaultdict
from typing import Iterator

from .. import core, maps, textspec

DATASET = "wikidata"
LICENSE = "CC0 1.0"
URL = "https://www.wikidata.org/wiki/Wikidata:Main_Page"
ATTRIBUTION = ("Wikidata, the free knowledge base of the Wikimedia Foundation and its contributors; structured data under CC0 1.0, "
               "read through the Wikidata Query Service (query.wikidata.org)")
CITATION = """@article{vrandecic2014wikidata,
  title   = {Wikidata: A Free Collaborative Knowledgebase},
  author  = {Vrande{\\v{c}}i{\\'c}, Denny and Kr{\\"o}tzsch, Markus},
  journal = {Communications of the ACM},
  volume  = {57},
  number  = {10},
  pages   = {78--85},
  year    = {2014},
  doi     = {10.1145/2629489}
}"""
TAKEN = ("records + hint: the depicts statements (P180, with quantity, colour and relative-position qualifiers), genre (P136), "
         "movement (P135), material (P186), inception (P571), country of origin (P495) and culture (P2596) of paintings and "
         "sculptures, English labels; never the creator; named people only as an anonymous woman / man / nonbinary figure (sex "
         "P21), a girl or a boy only when the label says child, no age from a birth date; a person count only when stated, never "
         "summed; no names")

SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = ("thought-seeds/0.1 (seed importer for the public dataset AbstractPhil/thought-symbolic-image-captions; "
              "https://huggingface.co/datasets/AbstractPhil/thought-symbolic-image-captions) python-requests")
CLASSES = {"painting": ("Q3305213", 4, 16000), "sculpture": ("Q860861", 2, 4000)}   # kind: (class, min depicts, works taken)
MAX_WORKS = 20000
BATCH_WORKS = 500
BATCH_VALUES = 300
PAUSE = 1.0
ROOTS = {"Q5": "human", "Q215627": "person", "Q729": "animal", "Q756": "plant", "Q16686448": "artifact", "Q11460": "clothing",
         "Q4936952": "body", "Q618123": "geo", "Q2095": "food", "Q2239243": "creature"}
HUMAN_CLASSES = ("Q5", "Q20643955")                 # human; human biblical figure
SEX = {"Q6581097": "man", "Q6581072": "woman", "Q2449503": "man", "Q1052281": "woman", "Q48270": "nonbinary"}

Q_WORKS = "SELECT ?item (COUNT(?d) AS ?n) WHERE {{ ?item wdt:P31 wd:{cls} ; wdt:P180 ?d . }} GROUP BY ?item HAVING (COUNT(?d) >= {k})"
Q_DEPICTS = """SELECT ?item ?st ?d ?dLabel ?qty ?colLabel ?posLabel ?nature ?human ?sex ?birth WHERE {
 VALUES ?item { %s }
 ?item p:P180 ?st . ?st ps:P180 ?d ; wikibase:rank ?rank . FILTER(?rank != wikibase:DeprecatedRank)
 OPTIONAL { ?st pq:P1114 ?qty }
 OPTIONAL { ?st pq:P462 ?col . ?col rdfs:label ?colLabel . FILTER(LANG(?colLabel) = "en") }
 OPTIONAL { ?st pq:P2677 ?pos . ?pos rdfs:label ?posLabel . FILTER(LANG(?posLabel) = "en") }
 OPTIONAL { ?st pq:P5102 ?nature }
 OPTIONAL { ?d rdfs:label ?dLabel . FILTER(LANG(?dLabel) = "en") }
 BIND(EXISTS { ?d wdt:P31 wd:Q5 } || EXISTS { ?d wdt:P31 wd:Q20643955 } AS ?human)
 OPTIONAL { ?d wdt:P21 ?sex }
 OPTIONAL { ?d wdt:P569 ?birth }
}"""
Q_PROPS = """SELECT ?item (GROUP_CONCAT(DISTINCT ?gl; separator="|") AS ?genres) (GROUP_CONCAT(DISTINCT ?ml; separator="|") AS ?moves)
 (GROUP_CONCAT(DISTINCT ?al; separator="|") AS ?mats) (MIN(?inc) AS ?inception) (MAX(?prec) AS ?precision) WHERE {
 VALUES ?item { %s }
 OPTIONAL { ?item wdt:P136 ?g . ?g rdfs:label ?gl . FILTER(LANG(?gl) = "en") }
 OPTIONAL { ?item wdt:P135 ?m . ?m rdfs:label ?ml . FILTER(LANG(?ml) = "en") }
 OPTIONAL { ?item wdt:P186 ?a . ?a rdfs:label ?al . FILTER(LANG(?al) = "en") }
 OPTIONAL { ?item p:P571/psv:P571 ?iv . ?iv wikibase:timeValue ?inc ; wikibase:timePrecision ?prec }
} GROUP BY ?item"""
# a work's country of origin and culture (English labels), and the object ids the museums among the sources give it: the Met
# (P3634), the Art Institute of Chicago (P4610), the National Gallery of Art (P4683)
Q_ORIGIN = """SELECT ?item (GROUP_CONCAT(DISTINCT ?ol; separator="|") AS ?countries) (GROUP_CONCAT(DISTINCT ?cl; separator="|") AS ?cultures)
 (GROUP_CONCAT(DISTINCT ?met; separator="|") AS ?met) (GROUP_CONCAT(DISTINCT ?aic; separator="|") AS ?aic)
 (GROUP_CONCAT(DISTINCT ?nga; separator="|") AS ?nga) WHERE {
 VALUES ?item { %s }
 OPTIONAL { ?item wdt:P495 ?o . ?o rdfs:label ?ol . FILTER(LANG(?ol) = "en") }
 OPTIONAL { ?item wdt:P2596 ?c . ?c rdfs:label ?cl . FILTER(LANG(?cl) = "en") }
 OPTIONAL { ?item wdt:P3634 ?met }
 OPTIONAL { ?item wdt:P4610 ?aic }
 OPTIONAL { ?item wdt:P4683 ?nga }
} GROUP BY ?item"""
Q_TYPES = "SELECT ?d ?root WHERE { VALUES ?d { %s } VALUES ?root { %s } ?d (wdt:P279|wdt:P171)* ?root . }"
Q_DEATHS = "SELECT ?d (MIN(?death) AS ?dd) WHERE { VALUES ?d { %s } ?d wdt:P570 ?death . } GROUP BY ?d"

# ------------------------------------------------------------------ word maps of this source (Wikidata's English labels)
# a depicted label or a genre holding one of these words or phrases leaves the work out (matched inside a label: 'erotic dance',
# 'human sexuality', 'The Rape of ...')
EXPLICIT = re.compile(r"\b(sex|sexual\w*|\w*sexuality|lesbianism|erotic\w*|eroticism|porn\w*|masturbat\w*|fellatio|cunnilingus|orgy|orgies|"
                      r"penis\w*|vulva\w*|vagina\w*|genital\w*|erection|coitus|copulation|intercourse|phall\w*|rape|raped|"
                      r"brothel\w*|prostitut\w*|courtesan\w*|seduction|seduc\w*|testicle\w*|scrotum|shunga|sex toy|dildo\w*|"
                      r"vibrator|butt plug|bondage|bdsm|fetish\w*|lingerie|striptease|stripper)\b")
# nudity beside a child figure leaves the work out: no seed pairs a nude with a child, a putto or a sitter whom the birth year puts
# under 18 at the work's date
NUDITY = re.compile(r"\b(nude|nudes|nudity|naked|nakedness|topless|toplessness|bare-breasted|nude swimming|bathers?|bathing)\b")
YOUNG = re.compile(r"\b(child|children|girl|girls|boy|boys|infant|infants|baby|babies|kid|kids|toddler|teen|teens|teenager|"
                   r"teenagers|youth|youths|adolescent|adolescents|putto|putti|cherub|cherubs|cupid|cupids|amor|amorino|amorini)\b")
ANATOMY = {"breast", "navel", "hip", "toe", "back", "buttocks", "nipple", "belly", "abdomen", "thigh", "knee", "leg", "foot", "hand",
           "arm", "shoulder", "neck", "face", "eye", "ear", "nose", "mouth", "lip", "lips", "finger", "chest", "torso", "skin", "head",
           "pubic hair", "armpit", "human body", "body", "human head", "human eye", "human hand", "human leg", "human face",
           "human mouth", "human nose", "human ear", "human foot", "human arm", "human back", "human hair", "hair", "tooth",
           "teeth", "tongue", "eyebrow", "forehead", "cheek", "chin", "wrist", "ankle", "heel", "elbow", "waist", "bosom",
           "fingernail", "nail", "dimples of venus", "human skin", "human skeleton", "skeleton", "bone", "muscle", "palm", "sole",
           "beard", "moustache", "mustache", "sideburns", "stubble"}
DETAIL_KEEP = {"beard", "moustache", "mustache", "nudity", "barefoot"}        # body words that read as plain details in the hint
CONCEPT = {"portrait", "landscape", "landscape painting", "gaze towards the viewer", "clothing", "work", "family", "death", "gift",
           "group of humans", "allegory", "love", "light", "shadow", "light source", "vegetation", "part", "still life", "seascape",
           "cityscape", "self-portrait", "genre art", "nudity", "costume", "human", "person", "people", "figure", "scene", "view",
           "interior", "interior view", "religious art", "history painting", "symbol", "iconography", "nature", "time",
           "fabric", "textile", "object", "thing", "decoration", "ornament", "pattern", "motif", "color", "colour", "air",
           "darkness", "reflection", "space", "nude", "female nude", "male nude"}
# activities, events, disciplines and ideas that the subclass tree types as artifacts (a game, a dance, a science): never the thing;
# an activity is kept as a plain detail of the hint ('Also shown: ice skating')
ACTIVITIES = {"prayer", "crucifixion", "old age", "profile", "game", "contre-jour", "folk dance", "blessing", "decapitation",
              "interior space", "stripe", "arabesque", "donor portrait", "history", "poetry", "ancient history", "philosophy",
              "ballet", "religion", "beauty", "chess", "empire", "card game", "medicine", "comedy", "paganism", "astronomy",
              "court decision", "genre painting", "order", "magic", "rugby", "tennis", "diplomacy", "boxing", "sport", "satire",
              "hygiene", "sale", "melancholia", "stoning", "gallantry", "ice hockey", "curling", "archaeology", "achievement",
              "sledding", "flaying", "art collection", "ethnography", "waltz", "combined driving", "literature", "art",
              "performance", "hiking", "state visit", "diving", "tragedy", "skating", "dengaku", "winter sport", "number theory",
              "strife", "cycling", "snowball fight", "minuet", "creation myth", "water jousting", "cockfight", "gender identity",
              "surgery", "benevolence", "vaccination", "animal husbandry", "greyhound racing", "quest", "hirsutism",
              "acrobatics", "radiesthesia", "death by burning", "iconoclasm", "military science", "constitution", "palmistry",
              "human rights", "independence", "play", "public lecture", "anatomy", "nursing", "raqs sharqi", "will", "idealism",
              "treaty", "oath", "gymnastics", "salah", "pardon", "pedicure", "economics", "sheep herding", "snakebite", "fado",
              "body painting", "autopsy", "lottery", "kermesse", "statute", "grammar", "flamenco", "bocce", "rock music", "opera",
              "proverb", "supplication", "rowing", "transparency", "marine art", "back portrait", "profil perdu", "orans",
              "tonsure", "hair tying styles", "recovery position", "fist", "signature", "motto", "thought bubble", "zodiac",
              "cuneiform", "calligraphic work", "dance", "music", "hunting", "fishing", "war", "battle", "work", "trade",
              "commerce", "education", "science", "mathematics", "geometry", "arithmetic", "rhetoric", "logic", "law", "justice",
              "charity", "vanity", "virtue", "vice", "sin", "faith", "hope", "temperance", "prudence", "fortitude", "wisdom",
              "knowledge", "truth", "fame", "victory", "peace", "fortune", "time", "eternity", "life", "youth", "childhood",
              "motherhood", "marriage", "wedding", "funeral", "burial", "baptism", "martyrdom", "resurrection", "annunciation",
              "nativity", "assumption", "lamentation", "deposition", "adoration", "visitation", "flight", "pilgrimage",
              "procession", "celebration", "festival", "feast", "party", "meal", "breakfast", "dinner", "supper", "conversation",
              "lecture", "lesson", "concert", "theatre", "theater", "carnival", "masquerade", "market", "auction", "harvest",
              "agriculture", "industry", "transport", "travel", "navigation", "exploration", "colonialism", "slavery", "poverty",
              "wealth", "power", "love", "death", "sleep", "dream", "memory", "emotion", "solitude", "loneliness", "joy", "grief",
              "sorrow", "mourning", "fear", "anger", "pain", "illness", "disease", "plague", "famine", "flood", "fire safety"}
CONCRETE_ING = {"building", "painting", "drawing", "clothing", "ceiling", "railing", "ring", "string", "wing", "earring",
                "stocking", "stockings", "bedding", "carving", "engraving", "etching", "awning", "siding", "dwelling", "pudding",
                "icing", "offering", "sibling", "duckling", "gosling", "seedling", "sapling", "herring", "whiting", "king",
                "sling", "swing", "spring", "lightning", "lining", "molding", "moulding", "flooring", "roofing", "mooring",
                "piping", "tubing", "wiring", "frosting", "filling", "stuffing", "dumpling", "gelding", "yearling", "fledgling",
                "starling", "bunting", "landing", "farthing", "shilling", "darling", "evening", "morning", "fitting",
                "covering", "planking", "printing press", "sewing needle", "fishing net", "fishing rod", "fishing vessel",
                "sailing ship", "drawing room", "dining room", "living room", "wedding cake", "knitting needle", "spinning wheel",
                "writing case", "rowing boat", "rocking horse", "hunting dog", "herding dog", "pointing dog", "milking stool",
                "dressing table", "bathing site", "bathing machine", "steering wheel", "folding chair", "hanging lamp",
                "church building", "city building", "office building", "farm building", "covered building"}
_NOT_A_THING = re.compile(r"(?:ing|ism|ics|ology|osophy|graphy|ness|ity|hood|ation|ition|ution|ance|ence)$")


def _not_a_thing(low: str) -> bool:
    """An activity, an event, a discipline or an idea the typing calls an artifact: never the picture's thing."""
    if low in ACTIVITIES:
        return True
    if low in CONCRETE_ING:
        return False
    last = low.split()[-1]
    m = _NOT_A_THING.search(last)
    return last not in CONCRETE_ING and bool(m) and len(last) > len(m.group(0)) + 2 and last not in (
        "fortification", "foundation", "station", "decoration", "illustration", "installation", "construction", "plantation",
        "habitation", "fence", "lance", "residence", "ambulance", "balance", "appliance", "pittance", "entrance", "nuance",
        "furnace", "palace", "terrace", "license", "fortress", "dress", "harness", "mattress", "press", "city", "university",
        "facility", "commodity", "antiquity", "nativity scene", "trinity")
NATURE = {"sky", "cloud", "clouds", "sea", "water", "fire", "smoke", "rock", "moon", "star", "rainbow", "wave", "wind wave", "horizon",
          "sun", "sunlight", "drapery", "flame", "lightning", "ice", "sand", "grass"}     # untyped or landscape words kept for the hint
GENDER_EXTRA = {"mother": "woman", "father": "man", "nun": "woman", "monk": "man", "king": "man", "queen": "woman", "bride": "woman",
                "groom": "man", "bridegroom": "man", "shepherdess": "woman", "milkmaid": "woman", "widow": "woman", "wife": "woman",
                "husband": "man", "fisherman": "man", "knight": "man", "priest": "man", "bishop": "man", "nobleman": "man",
                "noblewoman": "woman", "maid": "woman", "maidservant": "woman", "housewife": "woman", "gentleman": "man",
                "old man": "man", "old woman": "woman", "young man": "man", "young woman": "woman", "female nude": "woman",
                "male nude": "man", "lady": "woman", "princess": "woman", "prince": "man", "peasant woman": "woman",
                "fisherwoman": "woman", "washerwoman": "woman", "servant girl": "girl", "schoolgirl": "girl", "schoolboy": "boy"}
PERSON_LABELS = {"female human": "woman", "male human": "man", "pregnant person": None, "human figure": None}   # typed as animals
# depicted labels (a name's too) and genres that suggest more persons than the depicts list names: no person count
MORE_PEOPLE = re.compile(r"\b(crowds?|groups?|famil(?:y|ies)|couples?|people|persons|humans|children|men|women|boys|girls|armies|"
                         r"army|troops|soldiers|regiment|procession|assembly|congregation|audience|spectators|choir|orchestra|"
                         r"band|team|crew|council|congress|senate|parliament|court|apostles|disciples|saints|magi|kings|"
                         r"evangelists|brothers|sisters|sons|daughters|twins|lovers|dancers|musicians|players|riders|hunters|"
                         r"knights|monks|nuns|shepherds|virgins|martyrs|innocents|battle|siege|massacre|wedding|feast|banquet|"
                         r"meeting|gathering|market|concert|mob|riot|parade|group portrait|family portrait|conversation piece|"
                         r"militia|schutterstuk)\b")
# an untyped depicted label that names a person ('postilion'): one more figure than the typed persons
PERSON_ROLE_WORDS = {"postilion", "coachman", "servant", "page", "horseman", "huntsman", "hunter", "shepherd", "peasant",
                     "fisherman", "sailor", "musician", "beggar", "merchant", "pilgrim", "traveller", "traveler", "farmer", "maid",
                     "cook", "saint", "apostle", "disciple", "martyr", "monk", "nun", "priest", "bishop", "pope", "cardinal",
                     "king", "queen", "prince", "princess", "knight", "warrior", "soldier", "rider", "jockey", "groom", "valet",
                     "footman", "guard", "sentry", "porter", "vendor", "seller", "child", "infant", "baby", "youth", "elder",
                     "worker", "labourer", "laborer", "miner", "smith", "blacksmith", "carpenter", "painter", "sculptor", "artist",
                     "model", "dancer", "singer", "player", "actor", "actress", "clown", "jester", "dwarf", "slave", "prisoner",
                     "executioner", "nurse", "doctor", "scholar", "student", "teacher", "philosopher", "poet", "writer", "reader"}


def _names_a_person(low: str) -> bool:
    return (low in PERSON_ROLE_WORDS or low in GENDER_EXTRA or low in maps.GENDER or low in maps.AGE or low in maps.ROLE or
            low in textspec.PERSON_WORDS or bool(re.search(r"(man|men|woman|women)$", low)))
HAIR = {"long hair": "long", "waist-length hair": "long", "shoulder-length hair": "long", "short hair": "short", "curly hair": "curly",
        "straight hair": "straight", "wavy hair": "wavy", "braid": "braided", "braids": "braided", "braided hair": "braided",
        "hair bun": "bun", "bun": "bun", "chignon": "bun", "ponytail": "ponytail", "bangs": "bangs", "fringe": "bangs", "afro": "afro",
        "pigtails": "pigtails", "dreadlocks": "locs", "messy hair": "messy", "bob cut": "bob", "shaved head": "shaved",
        "crew cut": "buzzed", "buzz cut": "buzzed", "undercut": "undercut"}
EXPRESSION = {"smile": "smile", "smiling": "smile", "laughter": "laughing", "laughing": "laughing", "crying": "crying",
              "tears": "tears", "tear": "tears", "frown": "frown", "gaze towards the viewer": "gaze", "eye contact": "gaze",
              "grin": "grin", "closed eyes": "closed eyes", "open mouth": "open mouth", "sadness": "sad", "anger": "angry",
              "surprise": "surprised", "fear": "scared", "wink": "wink", "pensiveness": "pensive", "sleep": "closed eyes",
              "sleeping": "closed eyes"}
POSE_EXTRA = {"reclining": "lying", "reclining figure": "lying", "seated": "sitting", "sitting": "sitting", "standing": "standing",
              "lying": "lying", "lying down": "lying", "kneeling": "kneeling", "walking": "walking", "dancing": "dancing", "dance": "dancing",
              "running": "running", "leaning": "leaning", "crouching": "crouching", "squatting": "crouching", "jumping": "jumping",
              "climbing": "climbing", "reaching": "reaching", "bowing": "bowing", "resting": "resting", "contrapposto": "standing",
              "crossed arms": "crossed arms", "arms raised": "arms raised", "raised arms": "arms raised", "hands in pockets": "hands in pockets"}
GESTURE_EXTRA = {"pointing": "pointing", "pointing gesture": "pointing", "waving": "waving", "salute": "saluting",
                 "clapping": "clapping", "praying hands": "hands clasped", "clasped hands": "hands clasped", "shrug": "shrug",
                 "thumbs up": "thumbs up", "covering face": "covering face", "beckoning": "beckoning"}
SETTING_EXTRA = {"artist's studio": "studio", "studio": "studio", "harbor": "harbour", "harbour": "harbour", "port": "harbour",
                 "seashore": "beach", "beach": "beach", "marketplace": "market street", "market": "market street",
                 "kitchen": "kitchen", "library": "library", "garden": "garden", "forest": "forest", "woods": "forest",
                 "woodland": "forest", "jungle": "forest", "rainforest": "forest", "desert": "desert", "farm": "farm",
                 "farmyard": "farm", "barnyard": "farm", "bridge": "bridge", "cliff": "cliff", "meadow": "meadow", "ruins": "ruins",
                 "ruin": "ruins", "temple": "temple", "shrine": "temple", "cathedral": "cathedral", "courtyard": "courtyard",
                 "cave": "cave", "grotto": "cave", "swamp": "swamp", "marsh": "swamp", "vineyard": "vineyard", "pier": "pier",
                 "jetty": "pier", "wharf": "pier", "lighthouse": "lighthouse", "alley": "alley", "attic": "attic",
                 "ballroom": "ballroom", "greenhouse": "greenhouse", "laboratory": "laboratory", "classroom": "classroom",
                 "riverbank": "river bank", "river bank": "river bank", "snowfield": "snowfield", "stadium": "stadium",
                 "workshop": "workshop", "rooftop": "rooftop", "cafe": "cafe", "mountain pass": "mountain pass",
                 "hospital": "hospital ward", "bus stop": "bus stop", "subway": "subway"}
TIME_EXTRA = {"night": "night", "sunset": "dusk", "dusk": "dusk", "twilight": "dusk", "sunrise": "dawn", "dawn": "dawn",
              "morning": "morning", "evening": "late evening", "noon": "noon", "midnight": "midnight", "afternoon": "afternoon",
              "golden hour": "golden hour", "blue hour": "blue hour"}
WEATHER_EXTRA = {"snow": "snow", "snowfall": "snow", "rain": "rain", "fog": "fog", "mist": "fog", "storm": "storm",
                 "thunderstorm": "storm", "tempest": "storm", "drizzle": "drizzle", "frost": "frost", "hoarfrost": "frost",
                 "haze": "haze", "sleet": "sleet", "wind": "wind", "overcast": "overcast"}
LIGHT_EXTRA = {"moonlight": "moonlight", "candlelight": "candle", "firelight": "firelight", "silhouette": "silhouette",
               "lamplight": "lantern", "backlighting": "backlit", "spotlight": "spotlight"}
LAYOUT_EXTRA = {"crowd": "crowd"}
# accessories by depicted label: the shared map, plus the nouns it leaves out because free text uses them in other senses
ACCESSORY = {**maps.ACCESSORY, "watch": "watch", "ring": "ring", "belt": "belt"}
POSITION = {"left": "left", "right": "right", "center": "centre", "centre": "centre", "foreground": "foreground",
            "background": "background", "middle ground": "centre", "lower left": "left", "upper left": "left", "lower right": "right",
            "upper right": "right", "bottom left": "left", "top left": "left", "bottom right": "right", "top right": "right",
            "left side": "left", "right side": "right"}
GENRE = [("self-portrait", "self portrait"), ("self portrait", "self portrait"), ("portrait", "portrait"), ("bust", "portrait"),
         ("vanitas", "still life"), ("still life", "still life"), ("flower painting", "still life"), ("fruit painting", "still life"),
         ("breakfast piece", "still life"), ("banquet piece", "still life"), ("marine art", "seascape"), ("marine painting", "seascape"),
         ("seascape", "seascape"), ("cityscape", "cityscape"), ("veduta", "cityscape"), ("townscape", "cityscape"),
         ("landscape", "landscape"), ("church interior", "interior"), ("interior view", "interior"), ("interior", "interior"),
         ("architectural", "architecture"), ("genre art", "genre scene"), ("genre painting", "genre scene"),
         ("battle painting", "war"), ("battle", "war"), ("history painting", "history piece"), ("mythological", "mythological"),
         ("nude", "nude study"), ("allegory", "allegory"), ("allegorical", "allegory"), ("animal", "animal art"),
         ("equine art", "animal art"), ("hunting", "hunting scene"), ("botanical", "botanical"), ("religious", "religious art"),
         ("christian art", "religious art"), ("marian art", "religious art"), ("capriccio", "capriccio"), ("figure painting", "figure"),
         ("figurative", "figure"), ("caricature", "caricature"), ("abstract", "abstract"), ("floral", "still life"),
         ("military", "war")]
NUMBER = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
          11: "eleven", 12: "twelve"}
PLURAL = {"man": "men", "woman": "women", "child": "children", "ox": "oxen", "sheep": "sheep", "deer": "deer", "fish": "fish",
          "mouse": "mice", "goose": "geese", "foot": "feet", "person": "people", "cattle": "cattle", "swine": "swine",
          "putto": "putti", "knife": "knives", "wolf": "wolves", "leaf": "leaves", "calf": "calves", "loaf": "loaves"}
BODY_OK = {"flower", "skull", "leaf", "feather", "shell", "seashell", "egg", "horn", "antler", "branch", "seed", "bone", "rose",
           "blossom", "petal", "thorn", "tusk", "fruit", "nest", "pearl"}
MASS = {"bread", "beef", "meat", "cattle", "fire", "smoke", "grass", "water", "sky", "sea", "snow", "ice", "food", "wine", "cookware",
        "fog", "mist", "rain", "sand", "gold", "silver", "money", "fur", "hay", "straw", "foliage", "vegetation", "game", "poultry",
        "fish", "livestock", "laundry", "furniture", "jewelry", "jewellery", "armor", "armour", "clothing", "drapery", "music"}
SEALED_THINGS = set(core.HELD.get("thing", ()))
CONCRETE = {w for w, _, kind in textspec.NOUNS.values() if kind != "place"}   # common concrete nouns: preferred as the thing
MASS |= {"ruins", "bread", "fruit"}


def _qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _year(ts: str | None) -> int | None:
    m = re.match(r"^([+-]?)(\d{1,6})-", ts or "")
    if not m:
        return None
    y = int(m.group(2))
    return -y if m.group(1) == "-" else y


# ------------------------------------------------------------------ where a work comes from
# the English labels of the countries, states and cultures of the European tradition (a country of origin or a culture statement)
EUROPEAN = re.compile(
    r"\b(europe|european|italy|italian|france|french|netherlands|dutch|holland|flanders|flemish|belgium|belgian|spain|spanish|"
    r"castile|aragon|portugal|portuguese|germany|german|prussia|bavaria|saxony|holy roman empire|austria|austrian|habsburg|"
    r"bohemia|czech|czechia|poland|polish|hungary|hungarian|switzerland|swiss|england|english|great britain|united kingdom|"
    r"british|scotland|scottish|wales|welsh|ireland|irish|denmark|danish|norway|norwegian|sweden|swedish|finland|finnish|"
    r"iceland|icelandic|russia|russian|ukraine|ukrainian|greece|greek|byzantine|venice|venetian|republic of venice|florence|"
    r"florentine|genoa|milan|naples|papal states|siena|sienese|tuscany|lombardy|burgundy|burgundian|savoy|serbia|croatia|"
    r"romania|bulgaria|lithuania|latvia|estonia|slovakia|slovenia|luxembourg|monaco|malta|lorraine|brabant|limousin|"
    r"rhineland|westphalia|franconia|swabia|tyrol|catalonia|catalan|navarre|sicily|sardinia|corsica|crete)\b")
NON_EUROPEAN = re.compile(
    r"\b(china|chinese|japan|japanese|korea|korean|india|indian|mughal|persia|persian|iran|ottoman|turkey|turkish|egypt|egyptian|"
    r"syria|iraq|arab|islamic|tibet|tibetan|nepal|thai|thailand|cambodia|khmer|vietnam|indonesia|java|burma|mexico|mexican|aztec|"
    r"maya|inca|peru|peruvian|brazil|argentina|colombia|chile|united states|american|canada|canadian|australia|australian|"
    r"new zealand|maori|africa|african|ethiopia|nigeria|congo|hawaii|philippines|mongol|mongolia|asia|asian|oceania|"
    r"pre-columbian|native american|qing|ming|edo|joseon|safavid|seljuk|mamluk|fatimid|abbasid|umayyad|nasrid)\b")


def _european(origin: dict | None) -> bool:
    """Whether the work's country of origin or culture statements place it in the European tradition (and none outside it)."""
    labels = core.clean(" | ".join((origin or {}).get("countries", []) + (origin or {}).get("cultures", [])))
    return bool(EUROPEAN.search(labels)) and not NON_EUROPEAN.search(labels)


# ------------------------------------------------------------------ the same artwork in a museum source: one routing group
MUSEUMS = ("met", "aic", "nga", "cleveland")                  # the museum sources, in the order a link is chosen


def museum_group(origin: dict | None, links: dict | None, qid: str) -> str | None:
    """The museum seed id ('met:<Object ID>', 'aic:<id>', 'nga:<objectid>', 'cleveland:<id>') of the work, when Wikidata gives the
    museum's object id (`origin`) or the museum's own data gives the work's Wikidata id (`links`); the first museum in MUSEUMS and
    its smallest object id when there are several."""
    for museum in MUSEUMS:
        ids = [i for i in (origin or {}).get(museum, []) if re.fullmatch(r"\d+", i)]
        ids += [i for i in (links or {}).get(qid, {}).get(museum, [])]
        if ids:
            return f"{museum}:{min(ids, key=int)}"
    return None


def museum_links(raw_dir: str) -> dict:
    """{qid: {museum: [object id]}}: the Wikidata ids that the museums' own open data gives their objects (the Met's 'Object
    Wikidata URL', the National Gallery of Art's 'wikidataid', the Cleveland Museum of Art's 'external_resources'), read from
    their raw files when they are present under raw_dir; an empty map otherwise."""
    import csv
    csv.field_size_limit(2 ** 31 - 1)
    out: dict = {}

    def add(qid, museum, oid):
        if re.fullmatch(r"Q\d+", qid or "") and re.fullmatch(r"\d+", oid or ""):
            out.setdefault(qid, {}).setdefault(museum, []).append(oid)

    for museum, name, oid_col, link_col in (("met", os.path.join("met", "MetObjects.csv"), "Object ID", "Object Wikidata URL"),
                                            ("nga", os.path.join("nga", "objects.csv"), "objectid", "wikidataid"),
                                            ("cleveland", os.path.join("cleveland", "data.csv"), "id", "external_resources")):
        path = os.path.join(raw_dir, name)
        if not os.path.exists(path):
            continue
        pat = re.compile(r"wikidata\.org/(?:wiki|entity)/(Q\d+)\b" if museum != "nga" else r"^\s*(Q\d+)\s*$")
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                for qid in pat.findall(row.get(link_col) or ""):
                    add(qid, museum, (row.get(oid_col) or "").strip())
    return out


# ------------------------------------------------------------------ fetching (SPARQL, kept as JSON; idempotent by file)
def _post(query: str) -> bytes:
    import requests
    for attempt in range(6):
        try:
            r = requests.post(SPARQL, data={"query": query}, timeout=90,
                              headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"})
        except requests.RequestException:
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.content
        if r.status_code in (429, 500, 502, 503, 504):
            wait = int(r.headers.get("Retry-After", "0") or 0) or 15 * (attempt + 1)
            time.sleep(min(wait, 120))
            continue
        raise RuntimeError(f"WDQS {r.status_code}: {r.text[:400]}")
    raise RuntimeError("WDQS: no answer after six tries")


def _cached(path: str, query: str, got: dict) -> dict:
    if not os.path.exists(path):
        body = _post(query)
        json.loads(body)                                    # a broken answer fails here, before it is kept
        with open(path + ".part", "wb") as fh:
            fh.write(body)
        os.replace(path + ".part", path)
        time.sleep(PAUSE)
    got[os.path.basename(path)] = os.path.getsize(path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _rows(j: dict) -> list:
    return [{k: v["value"] for k, v in b.items()} for b in j["results"]["bindings"]]


def _select(raw: str, got: dict) -> list:
    """The works taken: per class the most-depicting works (ties by the item number), ordered by a stable hash of the id so any
    prefix of the list mixes both classes."""
    path = os.path.join(raw, "selection.json")
    if os.path.exists(path):
        got["selection.json"] = os.path.getsize(path)
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    sel, seen = [], set()
    for kind, (cls, k, n_take) in CLASSES.items():
        rows = _rows(_cached(os.path.join(raw, f"works_{kind}.json"), Q_WORKS.format(cls=cls, k=k), got))
        rows = sorted(((_qid(r["item"]), int(r["n"])) for r in rows), key=lambda t: (-t[1], int(t[0][1:])))
        for q, n in rows[:n_take]:
            if q not in seen:
                seen.add(q)
                sel.append({"id": q, "kind": kind, "n": n})
    sel = sorted(sel, key=lambda w: hashlib.sha1(w["id"].encode()).hexdigest())[:MAX_WORKS]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sel, fh)
    got["selection.json"] = os.path.getsize(path)
    return sel


def fetch(raw_dir: str) -> dict:
    """The works list, then per batch of 500 works their depicts, their genre / movement / material / inception, and their
    country of origin / culture / museum object ids (origin_NNNN.json), then the typing of every lower-case depicted value.
    -> {file: bytes}. Every answer is kept; a run fetches only the files that are missing."""
    raw = os.path.join(raw_dir, DATASET)
    os.makedirs(raw, exist_ok=True)
    got: dict = {}
    sel = _select(raw, got)
    ids = [w["id"] for w in sel]
    batches = [ids[i:i + BATCH_WORKS] for i in range(0, len(ids), BATCH_WORKS)]
    t0 = time.time()
    values, humans = {}, {}
    for b, chunk in enumerate(batches):
        vals = " ".join("wd:" + q for q in chunk)
        dep = _cached(os.path.join(raw, f"depicts_{b:04d}.json"), Q_DEPICTS % vals, got)
        _cached(os.path.join(raw, f"props_{b:04d}.json"), Q_PROPS % vals, got)
        _cached(os.path.join(raw, f"origin_{b:04d}.json"), Q_ORIGIN % vals, got)
        for r in _rows(dep):
            lab = r.get("dLabel", "")
            if r.get("human") == "true":
                humans[_qid(r["d"])] = 1
            elif lab and lab == lab.lower():
                values[_qid(r["d"])] = 1
        if b % 5 == 4 or b == len(batches) - 1:
            el = time.time() - t0
            print(f"[wikidata] works batch {b + 1}/{len(batches)}, {el:.0f} s spent, about "
                  f"{el / (b + 1) * (len(batches) - b - 1):.0f} s left", flush=True)
    vpath = os.path.join(raw, "values.json")
    if os.path.exists(vpath):
        with open(vpath, encoding="utf-8") as fh:
            vlist = json.load(fh)
    else:
        vlist = sorted(values, key=lambda q: int(q[1:]))
        with open(vpath, "w", encoding="utf-8") as fh:
            json.dump(vlist, fh)
    got["values.json"] = os.path.getsize(vpath)
    roots = " ".join("wd:" + r for r in ROOTS)
    vb = [vlist[i:i + BATCH_VALUES] for i in range(0, len(vlist), BATCH_VALUES)]
    t0 = time.time()
    for b, chunk in enumerate(vb):
        _cached(os.path.join(raw, f"types_{b:04d}.json"), Q_TYPES % (" ".join("wd:" + q for q in chunk), roots), got)
        if b % 10 == 9 or b == len(vb) - 1:
            el = time.time() - t0
            print(f"[wikidata] typing batch {b + 1}/{len(vb)}, {el:.0f} s spent, about {el / (b + 1) * (len(vb) - b - 1):.0f} s left",
                  flush=True)
    hpath = os.path.join(raw, "humans.json")                 # the depicted human individuals and their death year (P570), kept
    if os.path.exists(hpath):                                # with the answers (no age is read from a birth or a death date)
        with open(hpath, encoding="utf-8") as fh:
            hlist = json.load(fh)
    else:
        hlist = sorted(humans, key=lambda q: int(q[1:]))
        with open(hpath, "w", encoding="utf-8") as fh:
            json.dump(hlist, fh)
    got["humans.json"] = os.path.getsize(hpath)
    hb = [hlist[i:i + BATCH_VALUES] for i in range(0, len(hlist), BATCH_VALUES)]
    t0 = time.time()
    for b, chunk in enumerate(hb):
        _cached(os.path.join(raw, f"deaths_{b:04d}.json"), Q_DEATHS % " ".join("wd:" + q for q in chunk), got)
        if b % 10 == 9 or b == len(hb) - 1:
            el = time.time() - t0
            print(f"[wikidata] death-date batch {b + 1}/{len(hb)}, {el:.0f} s spent, about "
                  f"{el / (b + 1) * (len(hb) - b - 1):.0f} s left", flush=True)
    return got


# ------------------------------------------------------------------ reading the kept answers
def _load(raw: str):
    with open(os.path.join(raw, "selection.json"), encoding="utf-8") as fh:
        sel = json.load(fh)
    stmts = defaultdict(dict)                    # item -> statement -> fields
    props = {}
    types = defaultdict(set)
    deaths: dict = {}
    names = sorted(os.listdir(raw))
    for name in names:
        path = os.path.join(raw, name)
        if name.startswith("depicts_") and name.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                for r in _rows(json.load(fh)):
                    item = _qid(r["item"])
                    st = stmts[item].setdefault(r["st"], {"d": _qid(r["d"]), "label": r.get("dLabel", ""), "qty": None,
                                                         "colour": None, "pos": None, "nature": False, "human": False,
                                                         "sex": set(), "birth": set()})
                    if r.get("qty"):
                        try:
                            st["qty"] = int(float(r["qty"]))
                        except ValueError:
                            pass
                    st["colour"] = st["colour"] or r.get("colLabel")
                    st["pos"] = st["pos"] or r.get("posLabel")
                    st["nature"] = st["nature"] or bool(r.get("nature"))
                    st["human"] = st["human"] or r.get("human") == "true"
                    if r.get("sex", "").startswith("http://www.wikidata.org/entity/"):
                        st["sex"].add(_qid(r["sex"]))
                    y = _year(r.get("birth"))
                    if y is not None:
                        st["birth"].add(y)
        elif name.startswith("props_") and name.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                for r in _rows(json.load(fh)):
                    props.setdefault(_qid(r["item"]), {}).update(r)
        elif name.startswith("origin_") and name.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                for r in _rows(json.load(fh)):
                    props.setdefault(_qid(r["item"]), {})["origin"] = {
                        k: [x for x in (r.get(k) or "").split("|") if x] for k in ("countries", "cultures", "met", "aic", "nga")}
        elif name.startswith("types_") and name.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                for r in _rows(json.load(fh)):
                    types[_qid(r["d"])].add(ROOTS[_qid(r["root"])])
        elif name.startswith("deaths_") and name.endswith(".json"):
            with open(path, encoding="utf-8") as fh:
                for r in _rows(json.load(fh)):
                    y = _year(r.get("dd"))
                    if y is not None:
                        deaths[_qid(r["d"])] = y
    for item in stmts.values():
        for st in item.values():
            st["death"] = deaths.get(st["d"])
    return sel, stmts, props, types


# ------------------------------------------------------------------ one work -> one seed
def _already_plural(last: str) -> bool:
    return bool(re.search(r"[^sui]s$", last))            # stairs, pincers, high heels (not glass, chorus, iris, axis)


def _article(word: str) -> str:
    last = word.split()[-1]
    if last in MASS or _already_plural(last):
        return word
    return ("an " if word[:1] in "aeiou" else "a ") + word


def _plural(word: str) -> str:
    head, _, last = word.rpartition(" ")
    if last in PLURAL:
        p = PLURAL[last]
    elif _already_plural(last):
        p = last
    elif re.search(r"(s|x|z|ch|sh)$", last):
        p = last + "es"
    elif re.search(r"[^aeiou]y$", last):
        p = last[:-1] + "ies"
    else:
        p = last + "s"
    return (head + " " + p).strip()


def _counted(word: str, n: int | None) -> str:
    if not n or n == 1:
        return _article(word)
    return f"{NUMBER.get(n, str(n))} {_plural(word)}"


def _period(year: int | None, precision: int | None, western: bool = False) -> str | None:
    """The period of the work's inception; the European era names (medieval, renaissance, baroque) only for a work of the
    European tradition (`western`, from its country of origin or culture statements: _european)."""
    if year is None or precision is None:
        return None
    if precision >= 8:
        return maps.period_of(year, western=western)
    if precision == 7 and year > 0 and year % 100:            # a century: kept only when the whole century falls in one period
        lo = (year // 100) * 100 + 1
        a, b = maps.period_of(lo, western=western), maps.period_of(lo + 98, western=western)
        return a if a == b else None
    return None


def _style(label: str) -> str | None:
    t = core.clean(label)
    if re.search(r"\bpost-?impression", t) or "harlem renaissance" in t or "gothic revival" in t or "magic" in t:
        return None
    if re.search(r"\bneo-?impressionism\b", t):
        return "pointillism"
    if re.match(r"neo-?", t):
        return None
    return maps.first(t, maps.STYLE)


def _medium(materials: list) -> str | None:
    found = [v for m in materials for v in maps.find(core.clean(m), maps.MEDIUM)]
    for pref in ("oil painting", "tempera", "watercolour", "gouache", "acrylic", "fresco", "pastel", "ink", "charcoal", "pencil",
                 "bronze", "marble", "clay", "mosaic", "stained glass", "tapestry"):
        if pref in found:
            return pref
    return found[0] if found else None


def _genre(labels: list, domain: str) -> str:
    every = [core.clean(g) for g in labels if g]
    for phrase, g in GENRE:
        if any(phrase in x for x in every):
            return g
    low = [core.clean(g) for g in labels if g and g == g.lower()]
    short = [x for x in low if x and len(x.split()) <= 2 and len(x) <= 24]
    return short[0] if short else domain


def _person_of(st: dict, year: int | None) -> dict | None:
    """A depicted value as a person: an anonymous figure for a human individual, the label's words for a person class. A human
    individual's gender is its sex (P21): a woman, a man; a girl or a boy only when its label says child. No age is read from a
    birth date; a birth date that puts the sitter under 18 at the work's date (or after it) withholds the gender, as neither
    'man' nor 'boy' is then stated."""
    lab = st["label"]
    low = core.clean(lab)
    if st["human"]:
        sexes = {SEX[s] for s in st["sex"] if s in SEX}
        gender = sexes.pop() if len(sexes) == 1 else None
        age = None
        if re.search(r"\b(child|infant|baby)\b", low):
            age = "baby" if re.search(r"\b(infant|baby)\b", low) else "child"
            if gender in ("man", "woman"):
                gender = "boy" if gender == "man" else "girl"
        elif year is not None and any(year - b < 18 for b in st["birth"]):
            gender = None
        return {"gender": gender, "age": age, "role": None, "qty": 1, "word": gender or "figure", "st": st}
    if low in PERSON_LABELS:
        return {"gender": PERSON_LABELS[low], "age": None, "role": None, "qty": st["qty"], "word": PERSON_LABELS[low] or "figure",
                "st": st}
    gender = GENDER_EXTRA.get(low) or maps.first(low, maps.GENDER)
    age = maps.first(low, maps.AGE)
    if low in ("infant", "baby", "newborn"):
        age = "baby"
    role = maps.first(low, maps.ROLE) if low not in ("player",) else None
    return {"gender": gender, "age": age, "role": role, "qty": st["qty"], "word": low, "st": st}


def _thing_rank(ty: set) -> int | None:
    if "animal" in ty:
        return 0
    if "artifact" in ty and "geo" not in ty:
        return 1
    if "food" in ty:
        return 2
    if "plant" in ty:
        return 3
    if "body" in ty:
        return 4
    if "creature" in ty:
        return 5
    if "artifact" in ty:
        return 6
    return None


def build(qid: str, kind: str, stmts: dict, prop: dict, types: dict, group: str | None = None) -> dict | None:
    """One work's seed, or None (no subject facts, a sexual act or genitals depicted, nudity beside a child figure, or too few
    records). `group`: the museum seed id of the same artwork (museum_group), so both seeds make the same held / training choice."""
    domain = kind
    year = _year(prop.get("inception"))
    try:
        precision = int(prop.get("precision")) if prop.get("precision") else None
    except ValueError:
        precision = None
    year_known = year if precision is not None and precision >= 9 else None
    sts = sorted((s for s in stmts.values() if not s["nature"] and s["label"]), key=lambda s: int(s["d"][1:]))
    genres = [g for g in (prop.get("genres") or "").split("|") if g]
    if any(EXPLICIT.search(core.clean(s["label"])) for s in sts) or any(EXPLICIT.search(core.clean(g)) for g in genres):
        return None
    words = [core.clean(s["label"]) for s in sts] + [core.clean(g) for g in genres]
    minor = any(s["human"] and year_known is not None and any(year_known - b < 18 for b in s["birth"]) for s in sts)
    if any(NUDITY.search(w) for w in words) and (minor or any(YOUNG.search(w) for w in words)):
        return None
    persons, things, wear, details, depicted = [], [], [], [], []
    more = any(MORE_PEOPLE.search(core.clean(g)) for g in genres)      # something depicted suggests more persons than listed
    more = more or any(not s["label"] and not s["nature"] and (s["human"] or {"human", "person"} & types.get(s["d"], set()))
                       for s in stmts.values())          # a depicted person without an English label is one more figure
    hair = expr = pose = gesture = setting = tod = weather = light = layout = camera_angle = camera_frame = None
    for st in sts:
        lab = st["label"]
        low = core.clean(lab)
        if st["human"]:
            p = _person_of(st, year_known)
            if p:
                persons.append(p)
            continue
        if MORE_PEOPLE.search(low):
            more = True                                   # 'crowd', 'family', 'Second Continental Congress'
        if lab != lab.lower() or not low:                 # a capital letter: a name of a figure, place, work or event
            continue
        ty = types.get(st["d"], set())
        low = re.sub(r"\s*\([^)]*\)", "", lab).strip().lower()
        low = core.clean(low)
        if low in ANATOMY:
            if low in DETAIL_KEEP:
                details.append(low)
            continue
        if low.endswith(" hair") or low in HAIR:
            if low in HAIR:
                hair = hair or HAIR[low]
            details.append(low)
            continue
        if low in EXPRESSION:
            expr = expr or EXPRESSION[low]
            details.append(low)
            continue
        if low in POSE_EXTRA or low in GESTURE_EXTRA:
            pose = pose or POSE_EXTRA.get(low)
            gesture = gesture or GESTURE_EXTRA.get(low)
            details.append(low)
            continue
        if low in SETTING_EXTRA:
            setting = setting or SETTING_EXTRA[low]
            depicted.append(_counted(low, st["qty"]))
            continue
        if re.search(r"\b(shot|view|angle|perspective)\b", low) and (maps.first(low, maps.ANGLE) or maps.first(low, maps.FRAMING)):
            camera_angle = camera_angle or maps.first(low, maps.ANGLE)
            camera_frame = camera_frame or maps.first(low, maps.FRAMING)
            continue
        if low in TIME_EXTRA or low in WEATHER_EXTRA or low in LIGHT_EXTRA or low in LAYOUT_EXTRA:
            tod = tod or TIME_EXTRA.get(low)
            weather = weather or WEATHER_EXTRA.get(low)
            light = light or LIGHT_EXTRA.get(low)
            layout = layout or LAYOUT_EXTRA.get(low)
            details.append(low)
            continue
        if "human" in ty or "person" in ty or low in PERSON_LABELS:
            persons.append(_person_of(st, year_known))
            continue
        if low in CONCEPT:
            if low == "nudity":
                details.append(low)
            continue
        if _not_a_thing(low):
            details.append(low)                           # an activity or an idea: a plain detail of the hint, never the thing
            continue
        wear_c = maps.first(low, maps.CLOTHING) if (low in maps.CLOTHING or "clothing" in ty) else None
        wear_a = maps.first(low, ACCESSORY) if (low in ACCESSORY or "clothing" in ty) else None
        if "clothing" in ty or wear_c or wear_a:
            wear.append({"c": wear_c, "a": wear_a, "st": st, "low": low})
            continue
        if low in NATURE:
            depicted.append(_counted(low, st["qty"]) if low not in ("sky", "sea", "water", "fire", "smoke", "sand", "grass", "ice",
                                                                     "sunlight", "lightning", "drapery") else low)
            continue
        rank = _thing_rank(ty)
        if rank == 4 and not ({"plant", "food", "animal", "artifact"} & ty) and low not in BODY_OK:
            continue                                      # a part of a body (an aquiline nose), not an object of the picture
        if rank is None:
            if "geo" in ty:
                depicted.append(_counted(low, st["qty"]))
            elif _names_a_person(low):
                more = True                               # an untyped figure ('postilion'): one more than the typed persons,
                depicted.append(_counted(low, st["qty"]))  # named in the hint
            continue
        things.append({"rank": rank, "low": low, "st": st})
    if not persons:                                       # without a figure, a garment is an object of the picture
        for w in wear:
            things.append({"rank": 1, "low": w["low"], "st": w["st"]})
        wear = []
    single = len(persons) == 1 and persons[0]["qty"] in (None, 1) and not more
    s = core.Spec()
    # the persons: a count only when the source states it (one depicted person and nothing that suggests more: a human
    # individual is one, a person class counts by its stated quantity), never a sum; gender and age when they speak for the main
    # figure
    if persons:
        if len(persons) == 1 and not more:
            p = persons[0]
            n = 1 if p["st"]["human"] else p["qty"]
            if n:
                s.set("person", "count", str(n))
        # a gender only when it holds for every figure, as in the caption importers and the prompt parser: Mary, Joseph and the
        # Christ Child have none, and neither has a scene that suggests more figures than the depicted ones
        gs = [p["gender"] for p in persons]
        gender = gs[0] if gs[0] and all(x == gs[0] for x in gs) and not more else None
        if gender:
            s.set("person", "gender", gender)
        main = persons
        ages = {p["age"] for p in main if p["age"]}
        if len(ages) == 1 and all(p["age"] for p in main):
            s.set("person", "age", ages.pop())
        roles = [p["role"] for p in main if p["role"]]
        if roles and single:
            s.set("person", "role", roles[0])
        if hair and single:
            s.set("look", "hair", hair)
        if expr and single:
            s.set("look", "expression", expr)
        clothing = next((w for w in wear if w["c"]), None)
        accessory = next((w for w in wear if w["a"] and not w["c"]), None)
        if clothing:
            s.set("wear", "clothing", clothing["c"])
        if accessory:
            s.set("wear", "accessory", accessory["a"])
        for w in (clothing, accessory):
            if w and w["st"]["colour"]:
                c = maps.first(core.clean(w["st"]["colour"]), maps.COLOUR)
                if c and c not in maps.HAIR_COLOUR_ONLY and s.set("wear", "colour", c):
                    break
        if pose and single:
            s.set("body", "pose", pose)
        if gesture and single:
            s.set("body", "gesture", gesture)
    # the thing: the best-typed object, animals first
    things.sort(key=lambda t: (-(bool(t["st"]["qty"]) + bool(t["st"]["colour"]) + bool(t["st"]["pos"])), t["low"] in SEALED_THINGS,
                               t["low"] not in CONCRETE, t["rank"], int(t["st"]["d"][1:])))
    main_thing = None
    for t in things:
        if s.set("thing", "name", t["low"]):
            main_thing = t
            break
    if main_thing:
        st = main_thing["st"]
        if st["qty"]:
            s.set("thing", "count", str(st["qty"]))
        if st["colour"]:
            c = maps.first(core.clean(st["colour"]), maps.COLOUR)
            if c and c not in maps.HAIR_COLOUR_ONLY:
                s.set("thing", "colour", c)
        if st["pos"]:
            pos = POSITION.get(core.clean(st["pos"]))
            if pos:
                s.set("thing", "position", pos)
    # relations from the relative-position qualifiers of two depicted values
    placed = [(p["word"], POSITION.get(core.clean(p["st"]["pos"] or ""))) for p in persons if p.get("st") and p["st"]["pos"]]
    placed += [(t["low"], POSITION.get(core.clean(t["st"]["pos"] or ""))) for t in things if t["st"]["pos"]]
    placed = [(w, p) for w, p in placed if p]
    for (a, pa), (b, pb) in ((x, y) for i, x in enumerate(placed) for y in placed[i + 1:]):
        if {pa, pb} == {"left", "right"}:
            s.relate(a, "left of", b) if pa == "left" else s.relate(b, "left of", a)
        elif {pa, pb} == {"foreground", "background"}:
            s.relate(a, "in front of", b) if pa == "foreground" else s.relate(b, "in front of", a)
    # the scene
    if setting:
        s.set("scene", "setting", setting)
    if tod:
        s.set("scene", "time", tod)
    if weather:
        s.set("scene", "weather", weather)
    if layout:
        s.set("scene", "layout", layout)
    if light:
        s.set("shot", "light", light)
    if camera_angle:
        s.set("shot", "angle", camera_angle)
    if camera_frame:
        s.set("shot", "framing", camera_frame)
    subject = s.n()
    if not subject:
        return None
    # the form
    materials = [m for m in (prop.get("mats") or "").split("|") if m]
    medium = _medium(materials)
    if medium:
        s.set("form", "medium", medium)
    styles = [x for x in (_style(m) for m in (prop.get("moves") or "").split("|") if m) if x]
    if styles:
        s.set("form", "style", styles[0])
    period = _period(year, precision, _european(prop.get("origin")))
    if period:
        s.set("form", "period", period)
    genre = _genre(genres, domain)
    # the hint: plain sentences from the labels, no names
    groups: dict = {}
    for p in persons:                                     # one word a figure, never summed: 'men', 'a woman', 'three soldiers'
        w = p["word"] if not p["st"]["human"] else (p["gender"] or "figure")
        g = groups.setdefault(w, {"people": 0, "qty": []})
        if p["st"]["human"]:
            g["people"] += 1
        else:
            g["qty"].append(p["qty"])
    figures = []
    for w, g in groups.items():
        stated = max((q for q in g["qty"] if q), default=None)
        if g["people"] > 1:
            figures.append(_plural(w))                    # two named people or more: 'men'
        elif g["people"] == 1:                            # one named person; a class of the same word ('Mary' and 'woman') may be
            figures.append(_counted(w, stated) if stated and stated > 1 else _article(w))   # the same figure: 'a woman'
        else:
            figures.append(_counted(w, g["qty"][0]) if len(g["qty"]) == 1 else _plural(w))
    objs = []
    for w in wear:
        c = core.clean(w["st"]["colour"] or "")
        objs.append(_counted((c + " " if c and c == maps.first(c, maps.COLOUR) else "") + w["low"], w["st"]["qty"]))
    for t in things:
        c = core.clean(t["st"]["colour"] or "")
        objs.append(_counted((c + " " if c and c == maps.first(c, maps.COLOUR) else "") + t["low"], t["st"]["qty"]))
    shown = list(dict.fromkeys(figures + objs + depicted))
    mat_low = [core.clean(m) for m in materials if m == m.lower()]
    parts = [f"A {kind}" + (f" made with {', '.join(mat_low[:4])}" if mat_low else "") + "."]
    if year is not None and precision is not None and precision >= 9:
        parts.append(f"It is dated {year}." if year > 0 else f"It is dated {-year} BCE.")
    if shown:
        parts.append("It depicts " + (", ".join(shown[:-1]) + " and " + shown[-1] if len(shown) > 1 else shown[0]) + ".")
    det = list(dict.fromkeys(details))
    if det:
        parts.append("Also shown: " + ", ".join(det[:8]) + ".")
    g_low = [core.clean(g) for g in genres if g == g.lower()]
    if g_low:
        parts.append("Its genre is " + " and ".join(g_low[:2]) + ".")
    if styles:
        parts.append(f"Its style is {styles[0]}.")
    hint = core.make_hint([core.drop_named(p, allow=core.DATE_MARKS) for p in parts])      # 'It is dated 340 BCE.' holds no name
    return core.make_seed(DATASET, qid, domain, genre, textspec.finish(DATASET, qid, s, group), hint, LICENSE,
                          f"https://www.wikidata.org/wiki/{qid}", min_records=2, group=group)


def seeds(raw_dir: str, limit: int | None = None) -> Iterator[dict]:
    """The selected works in their stable order; a work that a museum source also holds is routed with that museum's seed id
    (museum_group), from the ids Wikidata gives (origin_NNNN.json) or the Wikidata ids the museums' own raw files give."""
    raw = os.path.join(raw_dir, DATASET)
    if not os.path.exists(os.path.join(raw, "selection.json")):
        raise FileNotFoundError(f"{raw}: run fetch() first")
    sel, stmts, props, types = _load(raw)
    links = museum_links(raw_dir)
    n = 0
    for w in sel:
        if limit is not None and n >= limit:
            return
        prop = props.get(w["id"], {})
        group = museum_group(prop.get("origin"), links, w["id"])
        seed = build(w["id"], w["kind"], stmts.get(w["id"], {}), prop, types, group)
        if seed:
            n += 1
            yield seed
