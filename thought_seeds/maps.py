"""thought_seeds.maps - source words to the trie's closed values (thought_pack 0.1.62 lists).

Each map takes a source phrase (lower case, as it appears in captions, scene graphs, museum fields or prompts) to ONE value of a closed
list; a phrase with no honest equivalent is left out rather than bent (a 'shirt' is not a 'jacket'). `find(text, MAP)` returns the
values found in a text, longest phrase first, word-bounded, in order of appearance. Every value here is checked against the lists by
the tests (tests/test_maps.py), so a list change in the trainer fails loudly."""
from __future__ import annotations

import re
from functools import lru_cache

GENDER = {"man": "man", "men": "man", "guy": "man", "guys": "man", "gentleman": "man", "gentlemen": "man", "male": "man",
          "woman": "woman", "women": "woman", "lady": "woman", "ladies": "woman", "female": "woman",
          "boy": "boy", "boys": "boy", "girl": "girl", "girls": "girl"}
AGE = {"child": "child", "children": "child", "kid": "child", "kids": "child", "toddler": "child", "little boy": "child",
       "little girl": "child", "young boy": "child", "young girl": "child",
       "baby": "baby", "babies": "baby", "infant": "baby",
       "teen": "teen", "teens": "teen", "teenager": "teen", "teenagers": "teen", "teenage": "teen",
       "elderly": "elderly", "old man": "elderly", "old woman": "elderly", "older man": "elderly", "older woman": "elderly",
       "old lady": "elderly", "senior": "elderly", "grandmother": "elderly", "grandfather": "elderly",
       "young man": "young adult", "young woman": "young adult", "young men": "young adult", "young women": "young adult"}
ROLE = {"worker": "worker", "workers": "worker", "construction worker": "worker", "dancer": "dancer", "dancers": "dancer",
        "musician": "musician", "musicians": "musician", "guitarist": "musician", "violinist": "musician", "drummer": "musician",
        "soldier": "soldier", "soldiers": "soldier", "farmer": "farmer", "farmers": "farmer", "nurse": "nurse", "student": "student",
        "students": "student", "chef": "chef", "chefs": "chef", "cook": "chef", "rider": "rider", "riders": "rider", "cyclist": "rider",
        "biker": "rider", "motorcyclist": "rider", "horseback rider": "rider", "jockey": "rider", "swimmer": "swimmer",
        "swimmers": "swimmer", "painter": "painter", "artist painting": "painter", "monk": "monk", "monks": "monk", "vendor": "vendor",
        "vendors": "vendor", "street vendor": "vendor", "seller": "vendor", "merchant": "vendor", "guard": "guard", "guards": "guard",
        "traveller": "traveller", "traveler": "traveller", "travelers": "traveller", "tourist": "traveller", "tourists": "traveller",
        "reader": "reader", "mother": "mother", "mom": "mother", "father": "father", "dad": "father", "bride": "bride",
        "athlete": "athlete", "athletes": "athlete", "surfer": "athlete", "skier": "athlete", "skateboarder": "athlete",
        "snowboarder": "athlete", "tennis player": "athlete", "baseball player": "athlete", "soccer player": "athlete",
        "football player": "athlete", "batter": "athlete", "pitcher": "athlete", "player": "athlete", "runner": "athlete"}
CLOTHING = {"raincoat": "raincoat", "rain coat": "raincoat", "suit": "suit", "business suit": "suit", "dress": "dress",
            "kimono": "kimono", "hoodie": "hoodie", "hooded sweatshirt": "hoodie", "uniform": "uniform", "overalls": "overalls",
            "gown": "gown", "wedding gown": "gown", "jacket": "jacket", "sweater": "sweater", "jumper": "sweater", "cardigan": "sweater",
            "coat": "coat", "overcoat": "coat", "trench coat": "coat", "robe": "robe", "robes": "robe", "bathrobe": "robe",
            "armour": "armour", "armor": "armour", "apron": "apron", "cloak": "cloak", "cape": "cloak", "tunic": "tunic",
            "jeans": "jeans", "blue jeans": "jeans", "sari": "sari", "saree": "sari", "parka": "parka", "vest": "vest",
            "waistcoat": "vest"}
ACCESSORY = {"hat": "hat", "hats": "hat", "beanie": "hat", "fedora": "hat", "sun hat": "hat", "cowboy hat": "hat", "cap": "cap",
             "baseball cap": "cap", "glasses": "glasses", "sunglasses": "glasses", "eyeglasses": "glasses", "spectacles": "glasses",
             "goggles": "glasses", "scarf": "scarf", "umbrella": "umbrella", "parasol": "umbrella", "watch": "watch",
             "wristwatch": "watch", "bag": "bag", "backpack": "bag", "handbag": "bag", "purse": "bag", "shoulder bag": "bag",
             "cane": "cane", "walking stick": "cane", "gloves": "gloves", "glove": "gloves", "mittens": "gloves", "mask": "mask",
             "crown": "crown", "tiara": "crown", "headphones": "headphones", "earphones": "headphones", "belt": "belt", "veil": "veil",
             "necklace": "necklace", "earrings": "earrings", "earring": "earrings", "ring": "ring", "bracelet": "bracelet",
             "brooch": "pin", "pin": "pin"}
COLOUR = {"black": "black", "blue": "blue", "brown": "brown", "green": "green", "grey": "grey", "gray": "grey", "orange": "orange",
          "pink": "pink", "purple": "purple", "red": "red", "white": "white", "yellow": "yellow", "silver": "silver", "gold": "gold",
          "golden": "golden", "teal": "teal", "turquoise": "turquoise", "violet": "violet", "magenta": "magenta", "crimson": "crimson",
          "scarlet": "scarlet", "lavender": "lavender", "emerald": "emerald", "amber": "amber", "aqua": "aqua", "cream": "cream",
          "beige": "beige", "tan": "tan", "navy": "navy", "navy blue": "navy", "olive": "olive", "maroon": "maroon", "coral": "coral",
          "lilac": "lilac", "rust": "rust", "ivory": "ivory", "charcoal": "charcoal", "indigo": "indigo", "peach": "peach",
          "mint": "mint", "mustard": "mustard", "plum": "plum", "sand": "sand", "slate": "slate", "wine": "wine",
          "dark blue": "dark blue", "light blue": "light blue", "dark brown": "dark brown", "light brown": "light brown",
          "hazel": "hazel", "blond": "blonde", "blonde": "blonde", "auburn": "auburn", "ginger": "ginger"}
HAIR_COLOUR_ONLY = {"blonde", "auburn", "ginger", "platinum blonde", "strawberry blonde", "hazel"}
SETTING = {"market": "market street", "street market": "market street", "marketplace": "market street",
           "farmers market": "market street", "open air market": "market street", "forest": "forest", "woods": "forest",
           "woodland": "forest", "jungle": "forest", "beach": "beach", "seashore": "beach", "shore": "beach", "kitchen": "kitchen",
           "studio": "studio", "rooftop": "rooftop", "roof top": "rooftop", "subway": "subway", "metro station": "subway",
           "subway station": "subway", "cathedral": "cathedral", "desert": "desert", "harbor": "harbour", "harbour": "harbour",
           "marina": "harbour", "cafe": "cafe", "coffee shop": "cafe", "library": "library", "garden": "garden", "mountain pass": "mountain pass",
           "alley": "alley", "alleyway": "alley", "ballroom": "ballroom", "farm": "farm", "barnyard": "farm", "classroom": "classroom",
           "river bank": "river bank", "riverbank": "river bank", "riverside": "river bank", "snowfield": "snowfield",
           "snow field": "snowfield", "greenhouse": "greenhouse", "stadium": "stadium", "ballpark": "stadium", "arena": "stadium",
           "workshop": "workshop", "bridge": "bridge", "cliff": "cliff", "cliffs": "cliff", "meadow": "meadow", "laboratory": "laboratory",
           "lab": "laboratory", "temple": "temple", "shrine": "temple", "bus stop": "bus stop", "hospital": "hospital ward",
           "hospital room": "hospital ward", "lighthouse": "lighthouse", "vineyard": "vineyard", "attic": "attic", "ruins": "ruins",
           "pier": "pier", "dock": "pier", "jetty": "pier", "wharf": "pier", "swamp": "swamp", "marsh": "swamp", "courtyard": "courtyard",
           "cave": "cave", "skate park": "skate park", "skatepark": "skate park", "night market": "night market"}
TIME = {"dawn": "dawn", "sunrise": "dawn", "daybreak": "dawn", "morning": "morning", "noon": "noon", "midday": "noon",
        "afternoon": "afternoon", "golden hour": "golden hour", "dusk": "dusk", "sunset": "dusk", "twilight": "dusk",
        "blue hour": "blue hour", "night": "night", "nighttime": "night", "night time": "night", "midnight": "midnight",
        "evening": "late evening", "late evening": "late evening"}
WEATHER = {"rain": "rain", "rainy": "rain", "raining": "rain", "snow": "snow", "snowy": "snow", "snowing": "snow", "fog": "fog",
           "foggy": "fog", "mist": "fog", "misty": "fog", "clear sky": "clear", "sunny": "clear", "overcast": "overcast",
           "cloudy": "overcast", "storm": "storm", "stormy": "storm", "thunderstorm": "storm", "haze": "haze", "hazy": "haze",
           "windy": "wind", "drizzle": "drizzle", "sleet": "sleet", "frost": "frost", "frosty": "frost"}
POSE = {"standing": "standing", "stands": "standing", "sitting": "sitting", "sits": "sitting", "seated": "sitting",
        "walking": "walking", "walks": "walking", "running": "running", "runs": "running", "lying": "lying", "laying": "lying",
        "lies": "lying", "kneeling": "kneeling", "kneels": "kneeling", "leaning": "leaning", "leans": "leaning",
        "crouching": "crouching", "squatting": "crouching", "crouched": "crouching", "jumping": "jumping", "jumps": "jumping",
        "leaping": "jumping", "dancing": "dancing", "dances": "dancing", "reaching": "reaching", "resting": "resting",
        "climbing": "climbing", "climbs": "climbing", "floating": "floating", "bowing": "bowing", "stretching": "stretching",
        "arms crossed": "crossed arms", "crossed arms": "crossed arms", "arms raised": "arms raised", "raised arms": "arms raised"}
GESTURE = {"waving": "waving", "waves": "waving", "pointing": "pointing", "points": "pointing", "clapping": "clapping",
           "thumbs up": "thumbs up", "shrugging": "shrug", "saluting": "saluting", "hands clasped": "hands clasped"}
LIGHT = {"backlit": "backlit", "backlighting": "backlit", "back lit": "backlit", "rim light": "rim light", "rim lighting": "rim light",
         "neon": "neon", "neon light": "neon", "neon lights": "neon", "candlelight": "candle", "candle light": "candle",
         "candlelit": "candle", "spotlight": "spotlight", "moonlight": "moonlight", "moonlit": "moonlight",
         "fluorescent": "fluorescent", "firelight": "firelight", "studio lighting": "studio flash", "studio light": "studio flash",
         "dappled light": "dappled", "dappled sunlight": "dappled", "silhouette": "silhouette", "silhouetted": "silhouette",
         "lantern light": "lantern", "street lamp": "street lamp", "streetlight": "street lamp", "street light": "street lamp",
         "low key": "low key", "low-key": "low key", "high key": "high key", "high-key": "high key", "window light": "soft window",
         "soft window light": "soft window", "harsh sunlight": "hard sun", "golden light": "golden", "overcast light": "overcast"}
ANGLE = {"low angle": "low angle", "low-angle": "low angle", "high angle": "high angle", "high-angle": "high angle",
         "overhead": "overhead", "top down": "overhead", "top-down": "overhead", "bird's eye": "overhead", "birds eye": "overhead",
         "aerial view": "overhead", "worm's eye": "worm's eye", "dutch angle": "dutch tilt", "dutch tilt": "dutch tilt",
         "over the shoulder": "over the shoulder", "profile": "profile", "side view": "profile", "three quarter": "three quarter",
         "three-quarter": "three quarter", "front view": "frontal", "frontal": "frontal", "eye level": "eye level"}
FRAMING = {"close-up": "close-up", "closeup": "close-up", "close up": "close-up", "extreme close-up": "extreme close",
           "extreme closeup": "extreme close", "portrait shot": "portrait", "waist up": "waist up", "upper body": "waist up",
           "full body": "full body", "full-body": "full body", "full length": "full body", "wide shot": "wide", "wide view": "wide",
           "extreme wide": "extreme wide", "macro": "macro", "macro shot": "macro", "detail shot": "detail", "medium shot": "medium shot",
           "two shot": "two shot", "establishing shot": "establishing"}
LENS = {"24mm": "24mm", "35mm": "35mm", "50mm": "50mm", "85mm": "85mm", "135mm": "135mm", "telephoto": "telephoto",
        "fisheye": "fisheye", "fish-eye": "fisheye", "tilt-shift": "tilt-shift", "tilt shift": "tilt-shift", "pinhole": "pinhole",
        "anamorphic": "anamorphic"}
FOCUS = {"shallow depth of field": "shallow", "shallow focus": "shallow", "deep focus": "deep", "deep depth of field": "deep",
         "soft focus": "soft", "selective focus": "selective", "motion blur": "motion blur", "bokeh": "bokeh", "tack sharp": "tack sharp",
         "sharp focus": "tack sharp"}
MEDIUM = {"photograph": "photograph", "photo": "photograph", "oil on canvas": "oil painting", "oil on panel": "oil painting",
          "oil on wood": "oil painting", "oil on copper": "oil painting", "oil on paper": "oil painting", "oil painting": "oil painting",
          "oil paint": "oil painting", "watercolor": "watercolour", "watercolour": "watercolour", "ink": "ink", "ink and wash": "ink",
          "india ink": "ink", "charcoal": "charcoal", "pencil": "pencil", "graphite": "pencil", "gouache": "gouache",
          "acrylic": "acrylic", "acrylic on canvas": "acrylic", "fresco": "fresco", "woodcut": "woodcut", "woodblock print": "woodcut",
          "woodblock": "woodcut", "wood engraving": "woodcut", "etching": "etching", "drypoint": "etching", "aquatint": "etching",
          "engraving": "etching", "digital painting": "digital painting", "digital art": "digital painting", "3d render": "3d render",
          "octane render": "3d render", "unreal engine": "3d render", "blender render": "3d render", "pixel art": "pixel art",
          "collage": "collage", "bronze": "bronze", "marble": "marble", "clay": "clay", "terracotta": "clay", "earthenware": "clay",
          "pastel": "pastel", "tempera": "tempera", "egg tempera": "tempera", "linocut": "linocut", "gelatin silver print": "silver print",
          "silver print": "silver print", "albumen print": "silver print", "cyanotype": "cyanotype", "polaroid": "polaroid",
          "film still": "film still", "mosaic": "mosaic", "tapestry": "tapestry", "stained glass": "stained glass",
          "vector art": "vector art", "vector illustration": "vector art", "lithograph": "lithograph", "lithography": "lithograph"}
STYLE = {"realism": "realism", "realist": "realism", "impressionism": "impressionism", "impressionist": "impressionism",
         "expressionism": "expressionism", "expressionist": "expressionism", "cubism": "cubism", "cubist": "cubism",
         "surrealism": "surrealism", "surrealist": "surrealism", "surreal": "surrealism", "baroque": "baroque",
         "renaissance": "renaissance", "high renaissance": "renaissance", "early renaissance": "renaissance",
         "northern renaissance": "renaissance", "ukiyo-e": "ukiyo-e", "ukiyo e": "ukiyo-e", "art nouveau": "art nouveau",
         "art deco": "art deco", "minimalism": "minimalism", "minimalist": "minimalism", "pop art": "pop art", "bauhaus": "bauhaus",
         "anime": "anime", "comic": "comic", "comic book": "comic", "noir": "noir", "film noir": "noir", "romanticism": "romanticism",
         "abstract": "abstract", "abstract art": "abstract", "fauvism": "fauvism", "fauvist": "fauvism", "pointillism": "pointillism",
         "pointillist": "pointillism", "brutalism": "brutalism", "brutalist": "brutalism", "folk art": "folk art",
         "photorealism": "photorealism", "photorealistic": "photorealism", "gothic": "gothic", "rococo": "rococo",
         "futurism": "futurism", "futurist": "futurism", "dada": "dada", "dadaism": "dada", "street art": "street art",
         "graffiti": "street art", "naive art": "naive", "naive": "naive", "symbolism": "symbolism", "symbolist": "symbolism"}
TEXTURE = {"smooth": "smooth", "rough": "rough", "grainy": "grainy", "film grain": "grainy", "glossy": "glossy", "matte": "matte",
           "cracked": "cracked", "velvet": "velvet", "wet": "wet", "dusty": "dusty", "woven": "woven", "brushy": "brushy",
           "visible brushstrokes": "brushy", "impasto": "brushy", "polished": "polished"}
CONTRAST = {"high contrast": "high", "low contrast": "low"}
# the relations of scene graphs (Visual Genome, GQA, Open Images) to the trie's relation list; 'on' and 'in' are left out (on a table,
# in a shirt: too many senses to bind to one relation word)
RELATION = {"left of": "left of", "to the left of": "left of", "right of": "right of", "to the right of": "right of",
            "above": "above", "over": "above", "below": "below", "beneath": "under", "under": "under", "underneath": "under",
            "behind": "behind", "in back of": "behind", "in front of": "in front of", "next to": "beside", "beside": "beside",
            "near": "beside", "by": "beside", "holding": "holding", "holds": "holding", "carrying": "holding", "carries": "holding",
            "facing": "facing", "faces": "facing", "looking at": "looking at", "watching": "looking at", "looks at": "looking at",
            "larger than": "larger than", "bigger than": "larger than", "smaller than": "smaller than", "touching": "touching",
            "inside": "inside", "inside of": "inside", "inside_of": "inside", "leaning on": "leaning on", "leaning against": "leaning on",
            "reflected in": "reflected in", "same color as": "same colour as", "same colour as": "same colour as"}
WEARING = ("wearing", "wears", "wear", "dressed in", "in")      # scene-graph predicates that put clothing or an accessory on a person

ALL = {"person gender": GENDER, "person age": AGE, "person role": ROLE, "wear clothing": CLOTHING, "wear accessory": ACCESSORY,
       "wear colour": COLOUR, "thing colour": COLOUR, "look eyes": COLOUR, "scene setting": SETTING, "scene time": TIME,
       "scene weather": WEATHER, "body pose": POSE, "body gesture": GESTURE, "shot light": LIGHT, "shot angle": ANGLE,
       "shot framing": FRAMING, "shot lens": LENS, "shot focus": FOCUS, "form medium": MEDIUM, "form style": STYLE,
       "form texture": TEXTURE, "form contrast": CONTRAST}


@lru_cache(maxsize=None)
def _pattern(map_id: int, phrases: tuple):
    alts = sorted(phrases, key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9'])(" + "|".join(re.escape(p) for p in alts) + r")(?![a-z0-9'])")


def find(text: str, mapping: dict) -> list:
    """The values the mapping's phrases give in `text` (lower-cased), in order of appearance, longest phrase first at each place."""
    if not text:
        return []
    pat = _pattern(id(mapping), tuple(mapping))
    return [mapping[m.group(1)] for m in pat.finditer(text.lower())]


def first(text: str, mapping: dict) -> str | None:
    vals = find(text, mapping)
    return vals[0] if vals else None


def majority(texts, mapping: dict, min_votes: int = 2) -> str | None:
    """The value most texts agree on (each text votes once per value), when at least `min_votes` texts give it."""
    from collections import Counter
    c = Counter()
    for t in texts:
        for v in set(find(t, mapping)):
            c[v] += 1
    if not c:
        return None
    v, n = c.most_common(1)[0]
    return v if n >= min_votes else None


def period_of(year) -> str | None:
    """A date (the start year; negative = BCE) to the trie's period list."""
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    if y < 500:
        return "ancient"
    if y < 1400:
        return "medieval"
    if y < 1600:
        return "renaissance"
    if y < 1750:
        return "baroque"
    if y < 1800:
        return None                        # the 18th century after the baroque has no entry of its own in the list
    if y < 1900:
        return "19th century"
    if y < 1945:
        return "early 20th"
    if y < 1975:
        return "mid century"
    if y < 1980:
        return None
    if y < 1990:
        return "1980s"
    if y < 2000:
        return "1990s"
    return "contemporary"


def position_of(cx: float) -> str:
    """A horizontal centre in [0, 1] to left / centre / right (thing position is an open key; three plain words)."""
    return "left" if cx < 0.38 else "right" if cx > 0.62 else "centre"
