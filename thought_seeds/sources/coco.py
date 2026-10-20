"""thought_seeds.sources.coco - COCO 2017 captions + instance boxes -> hidden picture specs.

Per image: the person count and the main non-person object (name, count, position, colour and state) come from the instance boxes
and the captions; person, wear, body, look, scene and shot facts come from the five captions by a majority (at least two captions
give the value and no other value ties it); up to four geometric relations come from the boxes where the separation is clear, plus
up to two 'holding' / 'looking at' relations the captions agree on. The hint is the captions without any sentence that may hold a
name (core.drop_named). Only the annotation zip is read: no image is downloaded, used or redistributed (the images carry their own
Flickr licenses; the annotations are CC BY 4.0)."""
from __future__ import annotations

import bisect
import json
import os
import re
import zipfile
from collections import Counter, defaultdict

from .. import core, maps

DATASET = "coco"
LICENSE = "CC BY 4.0"
URL = "https://cocodataset.org"
ATTRIBUTION = ("COCO 2017 captions and instance annotations, the COCO Consortium (Lin et al. 2014; Chen et al. 2015), CC BY 4.0; "
               "annotations only, no image used or redistributed")
CITATION = r"""@inproceedings{lin2014microsoft,
  title     = {Microsoft {COCO}: Common Objects in Context},
  author    = {Lin, Tsung-Yi and Maire, Michael and Belongie, Serge and Hays, James and Perona, Pietro and Ramanan, Deva and Doll{\'a}r, Piotr and Zitnick, C. Lawrence},
  booktitle = {Computer Vision -- ECCV 2014},
  series    = {Lecture Notes in Computer Science},
  volume    = {8693},
  pages     = {740--755},
  publisher = {Springer},
  year      = {2014},
  doi       = {10.1007/978-3-319-10602-1_48}
}

@article{chen2015microsoft,
  title   = {Microsoft {COCO} Captions: Data Collection and Evaluation Server},
  author  = {Chen, Xinlei and Fang, Hao and Lin, Tsung-Yi and Vedantam, Ramakrishna and Gupta, Saurabh and Doll{\'a}r, Piotr and Zitnick, C. Lawrence},
  journal = {arXiv preprint arXiv:1504.00325},
  year    = {2015}
}"""
TAKEN = ("records + hint: person count, the main object's name / count / position and up to four box relations from the instance "
         "boxes; person, wear, body, look, scene, shot, thing colour / state and caption relations by a two-caption majority; "
         "hint = the five captions without any sentence holding a capitalized name")

ZIP = "annotations_trainval2017.zip"
ZIP_URL = "http://images.cocodataset.org/annotations/annotations_trainval2017.zip"
ZIP_BYTES = 252907541
SPLITS = ("val2017", "train2017")
EXPLORE = "https://cocodataset.org/#explore?id={}"

STATS: Counter = Counter()          # the last seeds() run: images seen, seeds, the drop reasons


# ------------------------------------------------------------------ download
def _download(url: str, path: str, chunk: int = 1 << 20) -> None:
    import requests
    tmp = path + ".part"
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for b in r.iter_content(chunk):
                fh.write(b)
    os.replace(tmp, path)


def fetch(raw_dir: str) -> dict:
    """The annotation zip (241 MB, annotations only) into raw_dir/coco/; skipped when present at its published size."""
    d = os.path.join(raw_dir, DATASET)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, ZIP)
    if not (os.path.exists(path) and os.path.getsize(path) == ZIP_BYTES):
        _download(ZIP_URL, path)
    return {ZIP: os.path.getsize(path)}


# ------------------------------------------------------------------ the annotation files
_ANN = re.compile(rb'"area":\s*([-+0-9.eE]+),\s*"iscrowd":\s*([01]),\s*"image_id":\s*(\d+),\s*"bbox":\s*\[\s*([-+0-9.eE]+),\s*'
                  rb'([-+0-9.eE]+),\s*([-+0-9.eE]+),\s*([-+0-9.eE]+)\s*\],\s*"category_id":\s*(\d+)')


def _flat_list(raw: bytes, name: bytes) -> list | None:
    """A top-level list of flat objects (images, categories) cut out of the file without parsing the segmentation polygons."""
    i = raw.find(b'"' + name + b'":')
    if i < 0:
        return None
    j = raw.index(b"[", i)
    k = raw.index(b"]", j)
    return json.loads(raw[j:k + 1])


def _instances(raw: bytes) -> tuple:
    """-> (images, categories, {image_id: [(category_id, x, y, w, h, iscrowd)]}). The annotations are read by a pattern over the
    file's fixed field order (the 470 MB train file would take ~3 GB as parsed polygons); when the pattern does not account for
    every annotation the file is parsed whole instead."""
    anns = defaultdict(list)
    n = 0
    for m in _ANN.finditer(raw):
        anns[int(m[3])].append((int(m[8]), float(m[4]), float(m[5]), float(m[6]), float(m[7]), int(m[2])))
        n += 1
    images, cats = _flat_list(raw, b"images"), _flat_list(raw, b"categories")
    if n != raw.count(b'"category_id"') or images is None or cats is None:
        d = json.loads(raw)
        images, cats, anns = d["images"], d["categories"], defaultdict(list)
        for a in d["annotations"]:
            x, y, w, h = a["bbox"]
            anns[a["image_id"]].append((a["category_id"], x, y, w, h, int(a["iscrowd"])))
    return images, cats, anns


def _captions(raw: bytes) -> dict:
    out = defaultdict(list)
    for a in sorted(json.loads(raw)["annotations"], key=lambda a: a["id"]):
        out[a["image_id"]].append(a["caption"])
    return out


# ------------------------------------------------------------------ words
def _pat(phrases):
    alts = sorted(set(phrases), key=len, reverse=True)
    return re.compile(r"(?<![a-z0-9'])(" + "|".join(re.escape(p) for p in alts) + r")(?![a-z0-9'])")


class _M:
    """A phrase map with match positions (maps.find gives the values only)."""

    def __init__(self, mapping: dict):
        self.map = dict(mapping)
        self.pat = _pat(self.map)

    def iter(self, text: str) -> list:
        """(start, end, value) of every match; a blocking phrase of the shared maps (value None) consumes its words and yields nothing."""
        return [(m.start(), m.end(), self.map[m.group(1)]) for m in self.pat.finditer(text) if self.map[m.group(1)] is not None]


def _words(s: str) -> tuple:
    return tuple(w.strip() for w in s.split("|") if w.strip())


# COCO category -> (the spec's name, the caption words that name it); 'person' is the person system
CATS = {
    "bicycle": ("bicycle", "bicycle|bicycles|bike|bikes"),
    "car": ("car", "car|cars|jeep|jeeps|suv|suvs|taxi|taxis|cab|cabs|sedan|sedans"),
    "motorcycle": ("motorcycle", "motorcycle|motorcycles|motorbike|motorbikes|bike|bikes|dirt bike|dirt bikes|scooter|scooters|moped|mopeds"),
    "airplane": ("airplane", "airplane|airplanes|plane|planes|jet|jets|airliner|airliners|jetliner|jetliners|aircraft|aeroplane"),
    "bus": ("bus", "bus|buses|busses|double decker"),
    "train": ("train", "train|trains|locomotive|locomotives|tram|trams|trolley"),
    "truck": ("truck", "truck|trucks|pickup|pickup truck|lorry"),
    "boat": ("boat", "boat|boats|ship|ships|sailboat|sailboats|canoe|canoes|kayak|kayaks|yacht|yachts|ferry|ferries"),
    "traffic light": ("traffic light", "traffic light|traffic lights|stop light|stop lights|stoplight|stoplights|traffic signal|traffic signals"),
    "fire hydrant": ("fire hydrant", "fire hydrant|fire hydrants|hydrant|hydrants"),
    "stop sign": ("stop sign", "stop sign|stop signs"),
    "parking meter": ("parking meter", "parking meter|parking meters|meter|meters"),
    "bench": ("bench", "bench|benches"),
    "bird": ("bird", "bird|birds|pigeon|pigeons|seagull|seagulls|gull|gulls|duck|ducks|goose|geese|swan|swans|parrot|parrots|"
                     "owl|owls|eagle|eagles|hawk|hawks|crow|crows|sparrow|sparrows|pelican|pelicans|chicken|chickens"),
    "cat": ("cat", "cat|cats|kitten|kittens|kitty|kitties"),
    "dog": ("dog", "dog|dogs|puppy|puppies|pup|pups|lab|labs|labrador|labradors"),
    "horse": ("horse", "horse|horses|pony|ponies"),
    "sheep": ("sheep", "sheep|lamb|lambs"),
    "cow": ("cow", "cow|cows|cattle|bull|bulls|calf|calves|ox|oxen"),
    "elephant": ("elephant", "elephant|elephants"),
    "bear": ("bear", "bear|bears"),
    "zebra": ("zebra", "zebra|zebras"),
    "giraffe": ("giraffe", "giraffe|giraffes"),
    "backpack": ("backpack", "backpack|backpacks"),
    "umbrella": ("umbrella", "umbrella|umbrellas|parasol|parasols"),
    "handbag": ("handbag", "handbag|handbags|purse|purses"),
    "tie": ("tie", "tie|ties|necktie|neckties|bow tie"),
    "suitcase": ("suitcase", "suitcase|suitcases|luggage"),
    "frisbee": ("frisbee", "frisbee|frisbees"),
    "skis": ("skis", "skis|skiing"),
    "snowboard": ("snowboard", "snowboard|snowboards|snowboarding"),
    "sports ball": ("ball", "ball|balls|soccer ball|tennis ball|basketball|volleyball|football"),
    "kite": ("kite", "kite|kites"),
    "baseball bat": ("baseball bat", "baseball bat|baseball bats|bat|bats"),
    "baseball glove": ("baseball glove", "baseball glove|baseball gloves|glove|gloves|mitt|mitts"),
    "skateboard": ("skateboard", "skateboard|skateboards|skate board|skateboarding"),
    "surfboard": ("surfboard", "surfboard|surfboards|surf board|surf boards|surfing"),
    "tennis racket": ("tennis racket", "tennis racket|tennis rackets|racket|rackets|racquet|racquets"),
    "bottle": ("bottle", "bottle|bottles"),
    "wine glass": ("wine glass", "wine glass|wine glasses|glass of wine|glasses of wine"),
    "cup": ("cup", "cup|cups|mug|mugs"),
    "fork": ("fork", "fork|forks"),
    "knife": ("knife", "knife|knives"),
    "spoon": ("spoon", "spoon|spoons"),
    "bowl": ("bowl", "bowl|bowls"),
    "banana": ("banana", "banana|bananas"),
    "apple": ("apple", "apple|apples"),
    "sandwich": ("sandwich", "sandwich|sandwiches|burger|burgers|hamburger|hamburgers|sub"),
    "orange": ("orange", "oranges|orange slices|tangerine|tangerines|clementine|clementines"),
    "broccoli": ("broccoli", "broccoli"),
    "carrot": ("carrot", "carrot|carrots"),
    "hot dog": ("hot dog", "hot dog|hot dogs|hotdog|hotdogs"),
    "pizza": ("pizza", "pizza|pizzas"),
    "donut": ("donut", "donut|donuts|doughnut|doughnuts"),
    "cake": ("cake", "cake|cakes|cupcake|cupcakes"),
    "chair": ("chair", "chair|chairs"),
    "couch": ("couch", "couch|couches|sofa|sofas"),
    "potted plant": ("potted plant", "potted plant|potted plants|plant|plants|house plant|houseplant"),
    "bed": ("bed", "bed|beds"),
    "dining table": ("table", "table|tables|dining table|kitchen table"),
    "toilet": ("toilet", "toilet|toilets"),
    "tv": ("television", "tv|tvs|television|televisions|monitor|monitors|screen|screens"),
    "laptop": ("laptop", "laptop|laptops|laptop computer|notebook computer"),
    "mouse": ("computer mouse", "mouse|computer mouse"),
    "remote": ("remote control", "remote|remotes|remote control|remote controls|controller|controllers"),
    "keyboard": ("keyboard", "keyboard|keyboards"),
    "cell phone": ("phone", "phone|phones|cell phone|cell phones|cellphone|cellphones|smartphone|smartphones|mobile phone"),
    "microwave": ("microwave", "microwave|microwaves"),
    "oven": ("oven", "oven|ovens|stove|stoves"),
    "toaster": ("toaster", "toaster|toasters"),
    "sink": ("sink", "sink|sinks"),
    "refrigerator": ("refrigerator", "refrigerator|refrigerators|fridge|fridges"),
    "book": ("book", "book|books"),
    "clock": ("clock", "clock|clocks"),
    "vase": ("vase", "vase|vases"),
    "scissors": ("scissors", "scissors"),
    "teddy bear": ("teddy bear", "teddy|teddies|stuffed animal|stuffed animals|stuffed bear"),
    "hair drier": ("hair dryer", "hair dryer|hair drier|blow dryer|hairdryer"),
    "toothbrush": ("toothbrush", "toothbrush|toothbrushes"),
}
TV_NAMES = (("television", ("tv", "tvs", "television", "televisions")), ("monitor", ("monitor", "monitors")))

# the picture's kind by its main object (the seed's genre: one or two plain words)
GENRE = {"vehicle": "vehicle", "outdoor": "street", "animal": "animal", "accessory": "people", "sports": "sport", "kitchen": "food",
         "food": "food", "furniture": "interior", "electronic": "interior", "appliance": "interior", "indoor": "still life"}
WILD = {"elephant", "bear", "zebra", "giraffe"}
STREET_WORDS = _pat(("street", "streets", "road", "intersection", "sidewalk", "downtown", "traffic", "crosswalk"))
CITY_WORDS = _pat(("city", "skyline", "skyscraper", "skyscrapers", "buildings", "cityscape", "downtown"))
LAND_WORDS = _pat(("landscape", "field", "mountain", "mountains", "hill", "hills", "ocean", "lake", "sky", "valley", "countryside"))

PERSON_WORDS = _words(
    "man|men|woman|women|person|people|persons|boy|boys|girl|girls|child|children|kid|kids|baby|babies|toddler|toddlers|infant|"
    "guy|guys|lady|ladies|gentleman|gentlemen|teen|teens|teenager|teenagers|adult|adults|couple|family|crowd|team|he|she|someone|"
    "somebody|player|players|skier|skiers|surfer|surfers|skateboarder|skateboarders|snowboarder|snowboarders|rider|riders|biker|"
    "bikers|cyclist|cyclists|batter|pitcher|catcher|umpire|chef|chefs|cook|cooks|worker|workers|officer|officers|policeman|policemen|"
    "soldier|soldiers|student|students|athlete|athletes|tourist|tourists|mother|father|mom|dad|daughter|son|bride|groom|husband|"
    "wife|friends|spectators|fans|passenger|passengers|pedestrian|pedestrians|driver|vendor|vendors|farmer|farmers|musician|"
    "musicians|dancer|dancers|jockey|businessman|businessmen|businesswoman|player|surfers|individual|individuals|lady|youngster")
ANIMAL_WORDS = tuple(w for c in ("bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe")
                     for w in _words(CATS[c][1])) + ("animal", "animals")
OTHER_NOUNS = ("animal", "animals", "statue", "statues", "mannequin", "doll", "dolls", "toy", "toys", "robot", "sculpture", "figurine",
               "poster", "painting", "cartoon")

# source text that reads as a person / clothing / time word but is not one ('lab' is the dog; 'night stand' the furniture)
SCRUB = [(re.compile(p), r) for p, r in (
    (r"\bteddy bears?\b", "teddy"), (r"\blab coats?\b", "coat"),
    (r"\b(?:dvd|cd|record|mp3|media|blu ray|blu-ray|music) players?\b", "device"),
    (r"\b(?:guard ?rails?|shin ?guards?|mouth ?guards?|knee ?guards?|hand ?guards?)\b", "rail"),
    (r"\b(?:e-?readers?|card readers?)\b", "device"),
    (r"\b(?:wet|swim|bathing|ski|snow|space|body|jump|track|jogging) ?suits?\b", "outfit"),
    (r"\bdress shirts?\b", "shirt"), (r"\bsuit ?cases?\b", "suitcase"),
    (r"\b(?:bottle|hub|ice|knee) ?caps?\b", "lid"), (r"\bcandy canes?\b", "candy"),
    (r"\bnight ?(?:stands?|tables?)\b", "side table"), (r"\bnightstands?\b", "side table"),
    (r"\brain ?(?:coats?|jackets?)\b", "raincoat"), (r"\brain ?(?:boots|gear)\b", "boots"),
    (r"\b(?:chicken|turkey|duck) breasts?\b", "meat"), (r"\b(?:cake|pancake|waffle|cookie) batter\b", "dough"),
    (r"\b(?:water|beer|milk|glass) pitchers?\b", "jug"), (r"\bwalking sticks?\b", "cane"), (r"\brunning (?:shoes|water)\b", "item"),
    (r"\bsitting (?:room|area)\b", "lounge"), (r"\bsleeping bags?\b", "bedroll"), (r"\bwatch(?:es|ing)? tower\b", "tower"),
    (r"\bstreet ?lights?\b", "street lamp"), (r"\bflat ?screen\b", "flatscreen"))]
ANIMAL_CTX = re.compile(r"(?<![a-z0-9'])(" + "|".join(re.escape(w) for w in sorted(ANIMAL_WORDS, key=len, reverse=True)) + r")(?![a-z0-9'])")
# words that name a person's kin, age or sex but name an animal's as often ('a baby elephant', 'the mother giraffe')
ANIMAL_SHARED = {"baby", "babies", "infant", "mother", "mom", "father", "dad", "male", "female"}
BASEBALL = re.compile(r"base ?ball|\bbat\b|\bpitch|\bswing|home plate|umpire|catcher|\bmound\b")
NOT_BASEBALL = [(re.compile(r"\bbatters?\b"), "dough"), (re.compile(r"\bpitchers?\b"), "jug")]   # cake batter, a water pitcher

GENDER = {k: v for k, v in maps.GENDER.items()}
AGE = dict(maps.AGE)
ROLE = {k: v for k, v in maps.ROLE.items() if k not in ("cook",)}       # 'cook' is a verb as often as a noun
ROLE_ACTS = {"riding a horse": "rider", "riding horses": "rider", "riding a bike": "rider", "riding a bicycle": "rider",
             "riding a motorcycle": "rider", "riding motorcycles": "rider", "riding bikes": "rider", "on horseback": "rider",
             "riding a dirt bike": "rider", "riding a motorbike": "rider", "riding a scooter": "rider",
             "skiing": "athlete", "snowboarding": "athlete", "surfing": "athlete", "skateboarding": "athlete",
             "playing tennis": "athlete", "playing baseball": "athlete", "playing soccer": "athlete", "playing football": "athlete",
             "playing basketball": "athlete", "playing volleyball": "athlete", "playing rugby": "athlete", "playing lacrosse": "athlete",
             "playing a game of tennis": "athlete", "playing a game of baseball": "athlete", "playing a game of soccer": "athlete"}
CLOTHING = {k: v for k, v in maps.CLOTHING.items() if k not in ("jumper",)}
ACCESSORY = {k: v for k, v in maps.ACCESSORY.items()
             if k not in ("watch", "ring", "bag", "belt", "pin", "brooch", "glasses", "umbrella", "parasol", "goggles")}
ACCESSORY.update({"wearing glasses": "glasses", "wears glasses": "glasses", "with glasses": "glasses", "wrist watch": "watch",
                  "wedding ring": "ring", "engagement ring": "ring", "messenger bag": "bag", "tote bag": "bag", "ski goggles": "glasses",
                  "goggles": "glasses", "holding an umbrella": "umbrella", "holding umbrellas": "umbrella",
                  "holding a umbrella": "umbrella", "holding an open umbrella": "umbrella", "under an umbrella": "umbrella",
                  "under umbrellas": "umbrella", "with an umbrella": "umbrella", "carrying an umbrella": "umbrella"})
COLOUR_UNSURE = {"wine", "cream", "olive", "mint", "peach", "plum", "sand", "slate", "rust", "charcoal", "coral", "amber", "emerald",
                 "mustard", "lilac", "aqua", "ivory", "indigo", "golden"}
HUE = {k: v for k, v in maps.COLOUR.items() if v not in maps.HAIR_COLOUR_ONLY and k not in COLOUR_UNSURE}
GARMENTS = tuple(CLOTHING) + _words("shirt|shirts|t-shirt|t shirt|tee shirt|top|tank top|blouse|pants|trousers|shorts|skirt|outfit|"
                                    "outfits|clothes|clothing|jersey|jerseys|sweatshirt|attire|garb")
EXPRESSION = {"smiling": "smile", "smiles": "smile", "smile": "smile", "grinning": "grin", "grins": "grin", "laughing": "laughing",
              "laughs": "laughing", "crying": "crying", "cries": "crying", "frowning": "frown", "yawning": "open mouth",
              "yawns": "open mouth"}
HAIR = {"long hair": "long", "short hair": "short", "curly hair": "curly", "straight hair": "straight", "wavy hair": "wavy",
        "braided hair": "braided", "braids": "braided", "braid": "braided", "messy hair": "messy", "wet hair": "wet",
        "ponytail": "ponytail", "pony tail": "ponytail", "pigtails": "pigtails", "dreadlocks": "locs", "dreads": "locs",
        "afro": "afro", "hair in a bun": "bun", "shaved head": "shaved", "buzz cut": "buzzed", "bangs": "bangs"}
SETTING = {k: v for k, v in maps.SETTING.items() if k not in ("lab", "hospital")}
SETTING.update({"ski slope": "snowfield", "ski slopes": "snowfield", "snowy slope": "snowfield", "snow covered slope": "snowfield",
                "snowy hill": "snowfield", "snow covered hill": "snowfield", "snowy hillside": "snowfield",
                "snow covered mountain": "snowfield", "snowy mountain": "snowfield", "snowy field": "snowfield",
                "snow covered field": "snowfield", "barn": "farm", "pasture": "meadow", "grassy field": "meadow",
                "field of grass": "meadow", "hospital room": "hospital ward", "hospital bed": "hospital ward"})
TIME = dict(maps.TIME)
WEATHER = {k: v for k, v in maps.WEATHER.items() if v != "snow"}
WEATHER.update({"snowing": "snow", "falling snow": "snow", "snow falling": "snow", "snowfall": "snow", "snow storm": "storm",
                "snowstorm": "storm", "blizzard": "storm", "clear blue sky": "clear", "cloudless": "clear", "cloudy day": "overcast",
                "overcast day": "overcast", "rainy day": "rain", "in the rain": "rain"})
POSE = dict(maps.POSE)
POSE.update({"sit": "sitting", "stand": "standing", "laying down": "lying", "lying down": "lying", "squats": "crouching"})
GESTURE = dict(maps.GESTURE)
FRAMING = dict(maps.FRAMING)
ANGLE = {k: v for k, v in maps.ANGLE.items() if k not in ("overhead",)}
ANGLE.update({"overhead view": "overhead", "overhead shot": "overhead", "overhead photo": "overhead", "view from above": "overhead",
              "taken from above": "overhead", "aerial photo": "overhead", "aerial shot": "overhead", "top view": "overhead"})
LIGHT = {k: v for k, v in maps.LIGHT.items() if v not in ("street lamp", "golden", "overcast", "hard sun", "soft window",
                                                          "studio flash", "high key", "low key")}
LIGHT.pop("neon", None)                                             # 'neon green' is a colour, not the light
LIGHT.update({"neon signs": "neon", "neon sign": "neon"})
PALETTE = {"black and white photo": "black and white", "black and white photograph": "black and white",
           "black and white picture": "black and white", "black and white image": "black and white",
           "black and white shot": "black and white", "black and white photography": "black and white",
           "black and white scene": "black and white", "black and white view": "black and white",
           "black and white snapshot": "black and white", "black and white still": "black and white",
           "monochrome": "black and white", "grayscale": "black and white", "greyscale": "black and white",
           "sepia": "sepia", "sepia toned": "sepia"}
ANIMALS = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}
# animals outside the 80 categories, which annotators boxed as the nearest one (goats as sheep, deer as cows, donkeys as horses)
OTHER_ANIMALS = _pat(_words("goat|goats|deer|antelope|antelopes|moose|elk|llama|llamas|alpaca|alpacas|donkey|donkeys|mule|mules|"
                            "camel|camels|pig|pigs|hog|hogs|rhino|rhinos|rhinoceros|hippo|hippos|lion|lions|tiger|tigers|monkey|"
                            "monkeys|gorilla|gorillas|kangaroo|kangaroos|buffalo|buffaloes|bison|yak|yaks|wolf|wolves|fox|foxes|"
                            "squirrel|squirrels|rabbit|rabbits|bunny|bunnies|rat|rats|ostrich|emu|seal|seals|walrus|otter|otters"))
VEHICLES = {"bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"}
_WORN = {"snow covered": "snow covered", "covered in snow": "snow covered", "rusty": "rusty", "dirty": "dirty", "wet": "wet",
         "broken": "broken", "empty": "empty"}
# the thing's state by the thing's kind: a posture is an animal's, 'sitting on a runway' is a parked plane, a toilet has no posture
STATE_BY_KIND = {
    "animal": {"sleeping": "sleeping", "asleep": "sleeping", "sleeps": "sleeping", "napping": "sleeping", "laying": "lying",
               "lying": "lying", "lays": "lying", "lies": "lying", "laying down": "lying", "lying down": "lying",
               "standing": "standing", "stands": "standing", "sitting": "sitting", "sits": "sitting", "running": "running",
               "runs": "running", "grazing": "grazing", "grazes": "grazing", "eating": "eating", "eats": "eating",
               "drinking": "drinking", "drinks": "drinking", "flying": "flying", "flies": "flying", "soaring": "flying",
               "swimming": "swimming", "floating": "floating", "perched": "perched", "wet": "wet", "resting": "resting"},
    "vehicle": dict(_WORN, **{"parked": "parked", "sitting": "parked", "sits": "parked", "stationary": "parked", "stopped": "stopped",
                              "docked": "docked", "moored": "docked", "flying": "flying", "flies": "flying", "taking off": "taking off",
                              "landing": "landing", "moving": "moving", "floating": "floating", "overturned": "overturned"}),
    "object": dict(_WORN, **{"open": "open", "opened": "open", "closed": "closed", "lit": "lit", "lit up": "lit", "unmade": "unmade",
                             "sliced": "sliced", "half eaten": "half eaten", "partially eaten": "half eaten", "stacked": "stacked",
                             "frosted": "frosted", "turned on": "turned on", "turned off": "turned off", "flying": "flying",
                             "flies": "flying", "melted": "melted", "overturned": "overturned"})}
# 'a above b' / 'a below b' only when the upper one is aloft (in the air, on a pole, on a wall): between two things on the ground
# a higher box is a farther one, not one above
ALOFT = {"kite", "airplane", "bird", "traffic light", "clock", "frisbee", "sports ball"}
# words that name a group of categories (a caption's 'animals' names the horses when horses are the only animals in the picture)
GENERIC = {"animal": "animal", "animals": "animal", "vehicle": "vehicle", "vehicles": "vehicle", "fruit": "fruit", "fruits": "fruit",
           "vegetable": "vegetable", "vegetables": "vegetable", "veggies": "vegetable", "electronics": "electronic",
           "electronic devices": "electronic", "appliances": "appliance", "furniture": "furniture", "food": "food",
           "dessert": "dessert", "desserts": "dessert", "pastry": "dessert", "pastries": "dessert", "utensils": "utensil",
           "silverware": "utensil", "cutlery": "utensil"}
GENERIC_OF = {"fruit": {"banana", "apple", "orange"}, "vegetable": {"broccoli", "carrot"}, "dessert": {"cake", "donut"},
              "utensil": {"fork", "knife", "spoon"}}
# the picture's subject when it is none of the 80 categories: a noun at least three captions name
CAPTION_THINGS = {"street sign": "street sign", "street signs": "street sign", "sign": "sign", "signs": "sign",
                  "road sign": "road sign", "road signs": "road sign", "window": "window", "windows": "window", "tree": "tree",
                  "trees": "tree", "building": "building", "buildings": "building", "flowers": "flower", "flower": "flower",
                  "statue": "statue", "statues": "statue", "fountain": "fountain", "fence": "fence", "mirror": "mirror",
                  "lamp": "lamp", "lamps": "lamp", "lantern": "lantern", "candle": "candle", "candles": "candle", "camera": "camera",
                  "guitar": "guitar", "drum": "drum", "drums": "drum", "violin": "violin", "sword": "sword", "ladder": "ladder",
                  "basket": "basket", "tower": "tower", "clock tower": "clock tower", "church": "church", "lighthouse": "lighthouse",
                  "tent": "tent", "barn": "barn", "castle": "castle", "doughnut": "donut", "plate": "plate", "plates": "plate",
                  "pole": "pole", "graffiti": "graffiti", "mural": "mural", "fire truck": "fire truck", "bridge": "bridge"}
NUMBER = {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
          "a pair of": "2", "a couple of": "2", "2": "2", "3": "3", "4": "4", "5": "5"}
RELATE = {"holding": "holding", "holds": "holding", "looking at": "looking at", "looks at": "looking at", "watching": "looking at",
          "watches": "looking at", "staring at": "looking at"}       # no 'carrying': 'carrying bananas on her head' is not holding
PART_WORDS = {"door", "doors", "box", "boxes", "handle", "handles", "lid", "leash", "case", "cover", "stand", "rack", "cord",
              "seat", "carton", "wrapper", "crust", "string", "strings", "tail", "sail", "mast", "wheel", "wheels", "screen",
              "window", "light", "lights", "frame", "shelf", "station", "bag", "bags", "sign", "pole", "holder", "cage", "pen",
              "stall", "cart", "track", "tracks", "dish", "bowl", "plate", "basket", "costume", "food", "toy", "toys"}
EXPLICIT = re.compile(r"\b(?:nude|nudes|naked|nudity|topless|bottomless|sex|sexual|sexy|porn|porno|pornographic|erotic|genital|"
                      r"genitals|penis|vagina|nipple|nipples|breasts|boobs|lingerie|stripper|strip club)\b")
STOP = {"and", "or", "with", "of", "on", "in", "at", "to", "the", "a", "an", "near", "by", "next", "for", "from", "is", "are", "its",
        "his", "her", "their", "that", "which", "while", "as", "under", "over", "behind", "beside", "inside", "has", "have"}

# the categories whose box stands on the ground (a lower box bottom reads as nearer only for these); never person vs a ridable one
GROUNDED = {"person", "dog", "sheep", "cow", "bear", "zebra", "giraffe", "elephant", "horse", "car", "bus", "truck", "train",
            "fire hydrant"}
RIDABLE = {"horse", "elephant", "car", "bus", "truck", "train", "motorcycle", "bicycle"}
GAP = 0.02                 # a clear separation: 2% of the image between the boxes
DEPTH_DROP = 0.10          # the nearer box's bottom at least 10% of the image height lower
DEPTH_AREA = 1.5           # and its area at least 1.5 times the farther box's
MAX_GEOMETRIC = 4
MAX_CAPTION_RELATIONS = 2

_M_CACHE: dict = {}


def _m(mapping: dict) -> _M:
    k = id(mapping)
    if k not in _M_CACHE:
        _M_CACHE[k] = _M(mapping)
    return _M_CACHE[k]


SYN = defaultdict(set)
for _cat, (_name, _ws) in CATS.items():
    for _w in _words(_ws):
        SYN[_w].add(_cat)
SYN_M = _M({w: tuple(sorted(c)) for w, c in SYN.items()})
GENERIC_M = _M(GENERIC)
CAPTION_THINGS_M = _M(CAPTION_THINGS)
NUMBER_M = _M(NUMBER)
PERSON_M = _M({w: "person" for w in PERSON_WORDS})
OTHER_M = _M({w: "other" for w in OTHER_NOUNS})
GARMENT_M = _M({g: g for g in GARMENTS})
assert not set(PERSON_WORDS) & set(SYN), set(PERSON_WORDS) & set(SYN)      # a word is a person or an object, never both


class _Cap:
    """One caption, lower-cased and scrubbed, with its noun mentions (person words and category words) for binding."""

    def __init__(self, text: str):
        t = core.ascii_text(text).lower()
        for p, r in SCRUB:
            t = p.sub(r, t)
        if not BASEBALL.search(t):
            for p, r in NOT_BASEBALL:
                t = p.sub(r, t)
        self.t = t
        self.animal = bool(ANIMAL_CTX.search(t))
        nouns = [(s, e, "person") for s, e, _ in PERSON_M.iter(t)]
        self.cats = defaultdict(list)                  # category -> [(start, end, word)]
        for s, e, cs in SYN_M.iter(t):
            nouns.append((s, e, cs))
            for c in cs:
                self.cats[c].append((s, e, t[s:e]))
        nouns += [(s, e, "other") for s, e, _ in OTHER_M.iter(t)]
        self.generic = {g for _, _, g in GENERIC_M.iter(t)}
        nouns.sort(key=lambda n: n[0])
        self.nouns = nouns
        self.starts = [n[0] for n in nouns]

    def subject(self, pos: int):
        """The noun a word at `pos` tells of: the nearest noun before it, else the first within 30 characters after it."""
        i = bisect.bisect_left(self.starts, pos)
        if i > 0:
            return self.nouns[i - 1][2]
        if i < len(self.nouns) and self.nouns[i][0] - pos < 30:
            return self.nouns[i][2]
        return None

    def subject_word(self, pos: int):
        """The surface word of the nearest noun before `pos` (the person word a verb tells of)."""
        i = bisect.bisect_left(self.starts, pos)
        if i > 0:
            s, e, _ = self.nouns[i - 1]
            return self.t[s:e]
        return None

    def object_after(self, pos: int, reach: int = 25):
        """The first noun starting within `reach` characters after `pos`; None when it is a possessive ('a dog's leash') or the
        first word of a compound ('an oven door', 'a pizza box')."""
        i = bisect.bisect_left(self.starts, pos)
        if i < len(self.nouns) and self.nouns[i][0] - pos <= reach:
            s, e, kind = self.nouns[i]
            nxt = self.t[e:].split()[:1]
            if self.t[e:e + 2] == "'s" or (nxt and nxt[0].strip(".,;:!?") in PART_WORDS):
                return None
            return kind
        return None


UNGENDERED_YOUNG = re.compile(r"\b(?:child|children|kid|kids|baby|babies|toddler|toddlers|infant|infants|youngster)\b")
GENDERED_PLURAL = {"man": re.compile(r"\b(?:men|guys|gentlemen|businessmen|policemen)\b"),
                   "woman": re.compile(r"\b(?:women|ladies|businesswomen)\b"),
                   "boy": re.compile(r"\bboys\b"), "girl": re.compile(r"\bgirls\b")}


def _all_of(caps: list, gvotes: list, gender: str) -> bool:
    """For two or more people: the gender word holds for all of them when no caption names another gender or an ungendered young
    person, and two captions or more use the gender's own plural ('two women', 'men')."""
    if any(v != gender for s in gvotes for v in s):
        return False
    if any(UNGENDERED_YOUNG.search(c.t) and not c.animal for c in caps):
        return False
    return sum(1 for c in caps if GENDERED_PLURAL[gender].search(c.t)) >= 2


def _box_count(n: int, crowd: bool) -> str:
    """A count from boxes: exact up to three (small far instances are boxed too, so larger box counts are not trusted as numbers),
    'several' up to ten, 'many' beyond or for a crowd box."""
    if crowd or n > 10:
        return "many"
    return str(n) if n <= 3 else "several"


PLURAL_PEOPLE = frozenset(w for w in PERSON_WORDS if w.endswith("s") and w not in ("boss",)) | {
    "men", "women", "people", "children", "gentlemen", "businessmen", "policemen", "couple", "family", "crowd", "team"}
INTRODUCED = re.compile(r"\b(?:a|an|one)\s+(?:[a-z]+\s+){0,2}$")


def _people_said(c) -> set:
    """How many people one caption introduces: {'plural'} when it uses a group word ('people', 'a couple', 'skiers'), else the number
    of people it introduces with 'a' / 'an' / 'one' ('a man and a woman' -> 2; up to 3), else nothing."""
    ms = [(s, c.t[s:e]) for s, e, _ in PERSON_M.iter(c.t)]
    if any(w in PLURAL_PEOPLE for _, w in ms):
        return {"plural"}
    n = sum(1 for s, w in ms if w not in ("he", "she", "someone", "somebody") and INTRODUCED.search(c.t[max(0, s - 24):s]))
    return {str(n)} if 1 <= n <= 3 else set()


def _stated_count(caps: list, spans) -> str | None:
    """The number the captions state for a subject: a number word ending within 12 characters before one of the subject's spans
    (`spans(caption)` -> [(start, end)]), voted across the captions (two agree, no tie)."""
    votes = []
    for c in caps:
        sp = spans(c)
        votes.append({num for _, ne, num in NUMBER_M.iter(c.t) if any(0 <= ts - ne <= 12 for ts, _ in sp)})
    return _vote(votes)


def _vote(votes: list, min_votes: int = 2):
    """votes: one set of values a caption. The value at least `min_votes` captions give and no other value ties (None otherwise)."""
    c = Counter(v for s in votes for v in set(s) if v is not None)    # None: a blocking phrase of the shared maps
    if not c:
        return None
    top = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
    if top[0][1] < min_votes or (len(top) > 1 and top[1][1] == top[0][1]):
        return None
    return top[0][0]


def _person_votes(caps: list, mapping: dict, bound: bool = True, skip_animal_words: bool = False) -> list:
    out = []
    for c in caps:
        s = set()
        for p, e, v in _m(mapping).iter(c.t):
            word = c.t[p:e]
            if skip_animal_words and c.animal and any(w in ANIMAL_SHARED for w in word.split()):
                continue
            if not bound or c.subject(p) == "person":
                s.add(v)
        out.append(s)
    return out


def _hue_before(c: _Cap, spans: list) -> set:
    """The colours that stand right before one of `spans` (at most two plain words between), not in a 'black and white' pair."""
    out = set()
    for hs, he, hv in _m(HUE).iter(c.t):
        before = c.t[:hs].split()
        after_w = c.t[he:].split()
        if (before and before[-1] in ("and", "or", "&")) or (after_w and after_w[0] in ("and", "or", "&")) or c.t[he:he + 1] == "-":
            continue
        for ns, _, _ in spans:
            if ns < he:
                continue
            gap = c.t[he:ns].split()
            if len(gap) <= 2 and not any(w in STOP or w in HUE for w in gap):
                out.add(hv)
                break
    return out


def _state_votes(c: _Cap, spans: list, states: dict) -> set:
    out = set()
    for s, e, v in _m(states).iter(c.t):
        for ns, ne, _ in spans:
            gap_before = c.t[e:ns].split() if ns >= e else None
            gap_after = c.t[ne:s].split() if s >= ne else None
            if gap_before is not None and len(gap_before) == 0:
                out.add(v)
            elif gap_after is not None and len(gap_after) <= 2 and all(w in ("is", "are", "that", "which", "being", "all")
                                                                       for w in gap_after):
                out.add(v)
    return out


# ------------------------------------------------------------------ the hint
ACRONYMS = {"TV", "TVS", "DVD", "CD", "LCD", "LED", "CPU", "PC", "USB", "ATM", "SUV", "RV", "UFO", "BBQ", "OK", "ID", "AM", "PM"}
_SHOUT = re.compile(r"\b[A-Z]{2,}\b")


def unshout(text: str) -> str:
    """The text without every sentence holding an all-capitals word other than a common acronym: core.drop_named reads a name by
    its capital and lower-case letters, so 'JOHN' or 'OMNI HOTELS' would pass it (an all-capitals caption is dropped whole)."""
    keep = [s for s in re.split(r"(?<=[.!?])\s+", str(text).strip()) if not set(_SHOUT.findall(s)) - ACRONYMS]
    return " ".join(keep)


# ------------------------------------------------------------------ geometry
def _union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _geo(a: dict, b: dict):
    """The relation of group a to group b from their boxes (every box of a against every box of b), or None when unclear."""
    A, B = a["boxes"], b["boxes"]
    ua, ub = _union(A), _union(B)
    if ua[2] + GAP <= ub[0]:
        return "left of"
    if ub[2] + GAP <= ua[0]:
        return "right of"
    if min(ua[2], ub[2]) <= max(ua[0], ub[0]):
        return None                                        # no horizontal overlap and no clear gap
    if ua[3] + GAP <= ub[1]:
        return "above" if a["cat"] in ALOFT else None
    if ub[3] + GAP <= ua[1]:
        return "below" if b["cat"] in ALOFT else None
    if len(A) == 1 and len(B) == 1 and a["cat"] in GROUNDED and b["cat"] in GROUNDED and not (
            {a["cat"], b["cat"]} & RIDABLE and "person" in (a["cat"], b["cat"])):
        (ax1, ay1, ax2, ay2), (bx1, by1, bx2, by2) = A[0], B[0]
        aa, ba = (ax2 - ax1) * (ay2 - ay1), (bx2 - bx1) * (by2 - by1)
        inter = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
        if ay2 - by2 >= DEPTH_DROP and aa >= DEPTH_AREA * ba and inter < 0.5 * ba:
            return "in front of"
        if by2 - ay2 >= DEPTH_DROP and ba >= DEPTH_AREA * aa and inter < 0.5 * aa:
            return "behind"
    return None


# ------------------------------------------------------------------ one image
def _sealed_name(name: str) -> bool:
    return bool(core.tp.sealed_used([("thing name", name)], core.HELD))


def build(image_id, width: float, height: float, anns: list, captions: list, cat_names: dict, cat_super: dict) -> dict | None:
    """The seed of one image. anns: [(category_id, x, y, w, h, iscrowd)] in pixels; captions: the image's captions."""
    caps = [_Cap(t) for t in captions if t and t.strip()]
    if not caps:
        STATS["no caption"] += 1
        return None
    if any(EXPLICIT.search(c.t) for c in caps):
        STATS["explicit words"] += 1
        return None
    sid = str(image_id)
    seed_id = f"{DATASET}:{sid}"
    may_hold = core.held_pick(f"coco-image:{sid}")   # by the picture (shared with localized_narratives); a seed outside the held tenth never picks a sealed name
    W, H = float(width), float(height)
    groups = {}
    for cid, x, y, w, h, crowd in anns:
        cat = cat_names.get(cid)
        if cat is None or w <= 0 or h <= 0:
            continue
        g = groups.setdefault(cat, dict(cat=cat, boxes=[], crowd=False, area=0.0))
        box = (max(0.0, x / W), max(0.0, y / H), min(1.0, (x + w) / W), min(1.0, (y + h) / H))
        g["area"] += (box[2] - box[0]) * (box[3] - box[1])
        if crowd:
            g["crowd"] = True
            g["crowd_boxes"] = g.get("crowd_boxes", []) + [box]
        else:
            g["boxes"].append(box)
    sp = core.Spec()

    # --- the person
    P = groups.get("person")
    n_people = len(P["boxes"]) if P else 0
    # boxes alone are not enough: people in the far background, on posters or on screens are boxed too; the captions must speak of
    # people (two of them at least) before the picture has a person subject
    spoken = sum(1 for c in caps if PERSON_M.iter(c.t))
    has_people = bool(P) and (n_people > 0 or P["crowd"]) and spoken >= 2
    gender = None
    if has_people:
        stated = _stated_count(caps, lambda c: [(s, e) for s, e, _ in PERSON_M.iter(c.t)])
        votes = [_people_said(c) for c in caps]
        said = _vote(votes)
        more = {v for s in votes for v in s if v == "plural" or (said and said != "plural" and int(v) > int(said))}
        said = said if said and said != "plural" and not more else None     # any caption with more people: the boxes decide
        count = stated or said or _box_count(n_people, P["crowd"])
        if count == "1" and any(v == "plural" or int(v) > 1 for s in votes for v in s):
            # one box, but the captions see more people ('a couple', 'a man and a woman'): the captions' most named number
            nums = Counter(v for s in votes for v in s if v != "plural" and int(v) > 1)
            top = nums.most_common(2)
            count = top[0][0] if top and (len(top) == 1 or top[0][1] > top[1][1]) else "several"
        sp.set("person", "count", count)
        gvotes = _person_votes(caps, GENDER, bound=False, skip_animal_words=True)
        gender = _vote(gvotes)
        if gender and sp.d.get("person", {}).get("count") != "1" and not _all_of(caps, gvotes, gender):
            gender = None              # two or more people: the gender word must hold for all of them ('a woman and a child' is not two women)
        if gender:
            sp.set("person", "gender", gender)
        role = _vote([a | b for a, b in zip(_person_votes(caps, ROLE, bound=False, skip_animal_words=True),
                                             _person_votes(caps, ROLE_ACTS))])
        age = _vote(_person_votes(caps, AGE, bound=False, skip_animal_words=True))
        if age:
            sp.set("person", "age", age)
        if role:
            sp.set("person", "role", role)

    # --- the main non-person object
    def kinds_of(cat):
        return {k for k, v in GENERIC_OF.items() if cat in v} | {cat_super.get(cat, "")}

    present_kinds = Counter(k for c in groups if c != "person" for k in kinds_of(c))
    cands = []
    for cat, g in groups.items():
        if cat == "person" or cat not in CATS:
            continue
        name = CATS[cat][0]
        if cat == "tv":
            said = Counter()
            for c in caps:
                for nm, ws in TV_NAMES:
                    if any(c.t[s:e] in ws for s, e, _ in c.cats.get("tv", [])):
                        said[nm] += 1
            name = "television" if said["television"] else "monitor" if said["monitor"] else "screen"
        sole = {k for k in kinds_of(cat) if present_kinds[k] == 1}     # the only category of its kind: a group word names it
        named = sum(1 for c in caps if c.cats.get(cat))
        if cat in ANIMALS and (not named or sum(1 for c in caps if OTHER_ANIMALS.search(c.t)) > named):
            continue            # an animal the captions do not name, or call another animal, is not trusted ('sheep' boxes on goats)
        mentions = sum(1 for c in caps if c.cats.get(cat) or sole & c.generic)
        cands.append((mentions, g["area"], cat, name))
    cands.sort(key=lambda t: (-t[0], -t[1], t[2]))
    names = {cat: name for _, _, cat, name in cands}
    main = None
    for mentions, area, cat, name in cands:
        if not may_hold and _sealed_name(name):
            continue
        if mentions >= 1 or area >= 0.05:
            main = cat
        break
    if main:
        g = groups[main]
        sp.set("thing", "name", names[main])
        n = len(g["boxes"])
        stated = _stated_count(caps, lambda c: [(s, e) for s, e, _ in c.cats.get(main, [])])
        sp.set("thing", "count", stated or _box_count(n, g["crowd"]))
        allb = g["boxes"] + g.get("crowd_boxes", [])
        pos = {maps.position_of((b[0] + b[2]) / 2) for b in allb}
        if len(pos) == 1:
            sp.set("thing", "position", pos.pop())
        spans = lambda c: c.cats.get(main, [])
        if main != "orange":
            col = _vote([_hue_before(c, spans(c)) for c in caps])
            if col:
                sp.set("thing", "colour", col)
        states = STATE_BY_KIND["animal" if main in ANIMALS else "vehicle" if main in VEHICLES else "object"]
        st = _vote([{v for v in _state_votes(c, spans(c), states)
                     if not any(v in vals for vals in core.HELD.values())} for c in caps])
        if st:
            sp.set("thing", "state", st)
    else:
        # no category qualifies as the subject: the noun at least three captions name, its number when they agree on one
        votes = [{v for _, _, v in CAPTION_THINGS_M.iter(c.t)} for c in caps]
        name = _vote(votes, min_votes=3)
        if name and (may_hold or not _sealed_name(name)):
            sp.set("thing", "name", name)
            nv = []
            for c in caps:
                s = set()
                for ns, ne, num in NUMBER_M.iter(c.t):
                    if any(v == name and 0 <= ts - ne <= 12 for ts, _, v in CAPTION_THINGS_M.iter(c.t)):
                        s.add(num)
                nv.append(s)
            num = _vote(nv)
            if num:
                sp.set("thing", "count", num)

    # --- the person's body, wear and look (words bound to a person word)
    if has_people:
        pose = _vote(_person_votes(caps, POSE))
        if pose:
            sp.set("body", "pose", pose)
        gesture = _vote(_person_votes(caps, GESTURE))
        if gesture:
            sp.set("body", "gesture", gesture)
        clothing = _vote(_person_votes(caps, CLOTHING))
        if clothing:
            sp.set("wear", "clothing", clothing)
        garment_votes = []
        for c in caps:
            spans_all = [(s, e, v) for s, e, v in GARMENT_M.iter(c.t) if c.subject(s) == "person"]
            if clothing:
                spans_all = [x for x in spans_all if CLOTHING.get(x[2]) == clothing]
            s = _hue_before(c, spans_all)
            for m in re.finditer(r"\b(?:dressed in|clad in|wearing|dressed all in|wearing all) (?:all )?([a-z]+)\b(?! and)", c.t):
                if m.group(1) in HUE and c.subject(m.start()) == "person":
                    s.add(HUE[m.group(1)])
            garment_votes.append(s)
        wc = _vote(garment_votes)
        if wc:
            sp.set("wear", "colour", wc)
        acc = _vote(_person_votes(caps, ACCESSORY))
        if acc and not (main and (CATS[main][0] == acc or (acc == "bag" and main in ("handbag", "backpack")))):
            sp.set("wear", "accessory", acc)
        expr = _vote(_person_votes(caps, EXPRESSION))
        if expr:
            sp.set("look", "expression", expr)
        hair = _vote(_person_votes(caps, HAIR))
        if hair:
            sp.set("look", "hair", hair)

    # --- the scene and the shot (words of the whole picture)
    def whole(mapping):
        return _vote([{v for _, _, v in _m(mapping).iter(c.t)} for c in caps])

    for key, mapping in (("setting", SETTING), ("time", TIME), ("weather", WEATHER)):
        v = whole(mapping)
        if v:
            sp.set("scene", key, v)
    n_anns = sum(len(g["boxes"]) + len(g.get("crowd_boxes", [])) for g in groups.values())
    layout = None
    if P and (P["crowd"] or n_people >= 10):
        layout = "crowd"
    elif n_anns == 1 and sum(g["area"] for g in groups.values()) >= 0.15:
        layout = "single subject"
    elif n_anns == 2 and len(groups) == 1:
        layout = "pair"
    elif not has_people and _vote([{"empty"} if re.search(r"\bempty (?:street|road|room|kitchen|bathroom|bedroom|field|beach|"
                                                           r"office|park|lot|parking lot|station|platform|restaurant)\b", c.t)
                                   else set() for c in caps]):
        layout = "empty"
    if layout:
        sp.set("scene", "layout", layout)
    for key, mapping in (("framing", FRAMING), ("angle", ANGLE), ("light", LIGHT)):
        v = whole(mapping)
        if v:
            sp.set("shot", key, v)
    pal = whole(PALETTE)
    if pal:
        sp.set("form", "palette", pal)

    # --- relations: the boxes first, then what the captions agree on
    person_end = gender or "person"
    ends = []
    if P and P["boxes"] and not P["crowd"]:
        ends.append(("person", person_end))
    if main and groups[main]["boxes"] and not groups[main]["crowd"]:
        ends.append((main, names[main]))
    for mentions, area, cat, name in cands:
        if cat == main or groups[cat]["crowd"] or not groups[cat]["boxes"]:
            continue
        if mentions == 0 and area < 0.02:
            continue
        if not may_hold and _sealed_name(name):
            continue
        if name in {e[1] for e in ends}:
            continue
        ends.append((cat, name))
        if len(ends) >= 5:
            break
    geo = 0
    pairs = [(i, j) for i in range(len(ends)) for j in range(i + 1, len(ends))]
    for i, j in pairs:
        if geo >= MAX_GEOMETRIC:
            break
        (ca, na), (cb, nb) = ends[i], ends[j]
        rel = _geo(groups[ca], groups[cb])
        if rel and sp.relate(na, rel, nb):
            geo += 1
    if has_people:
        rv, who = [], defaultdict(set)       # (rel, category) votes; the person words that did the holding / looking
        for c in caps:
            s = set()
            for p, e, rel in _m(RELATE).iter(c.t):
                if c.subject(p) != "person":
                    continue
                kind = c.object_after(e)
                if isinstance(kind, tuple):
                    for cat in kind:
                        if cat in names:
                            s.add((rel, cat))
                            who[(rel, cat)].add(GENDER.get(c.subject_word(p) or "", "person"))
            rv.append(s)
        for _ in range(MAX_CAPTION_RELATIONS):
            v = _vote(rv)
            if not v:
                break
            rel, cat = v
            named = who[v] - {"person"}
            end = named.pop() if len(named) == 1 else "person"     # the holder's word when the captions agree on it
            if may_hold or not _sealed_name(names[cat]):
                sp.relate(end, rel, names[cat])
            rv = [s - {v} for s in rv]

    # --- the genre and the hint
    if main:
        sup = cat_super.get(main, "")
        genre = GENRE.get(sup, "scene")
        if main in WILD:
            genre = "wildlife"
        elif main == "kite":
            genre = "leisure"
        elif sup in ("vehicle", "accessory", "outdoor", "indoor") and main not in ("book", "scissors", "toothbrush", "vase") and \
                _vote([{1} if CITY_WORDS.search(c.t) else set() for c in caps]):
            genre = "cityscape"
        elif sup in ("vehicle", "accessory", "indoor") and _vote([{1} if STREET_WORDS.search(c.t) else set() for c in caps]):
            genre = "street"
        elif sup == "kitchen" and not any(cat_super.get(c) == "food" for c in groups):
            genre = "still life"
        elif sup == "indoor" and has_people:
            genre = "interior"
    elif has_people:
        big = max((b[2] - b[0]) * (b[3] - b[1]) for b in (P["boxes"] or P.get("crowd_boxes", [])))
        genre = "portrait" if n_people <= 2 and big >= 0.2 else "people"
    elif _vote([{1} if CITY_WORDS.search(c.t) else set() for c in caps]):
        genre = "cityscape"
    elif _vote([{1} if STREET_WORDS.search(c.t) else set() for c in caps]):
        genre = "street"
    else:
        genre = "landscape" if _vote([{1} if LAND_WORDS.search(c.t) else set() for c in caps]) else "scene"
    if has_people and main and main != "kite" and cat_super.get(main) == "sports":
        genre = "sport"
    hint = core.make_hint([core.drop_named(unshout(t)) for t in captions])
    seed = core.make_seed(DATASET, sid, "photograph", genre, sp, hint, LICENSE, EXPLORE.format(sid), group=f"coco-image:{sid}")
    if seed is None:
        STATS["empty or failed check"] += 1
        return None
    for k, v in sp.dropped.items():
        STATS[f"dropped {k}"] += v
    return seed


# ------------------------------------------------------------------ the source
def _load(raw_dir: str, split: str):
    path = os.path.join(raw_dir, DATASET, ZIP)
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        inst, capf = f"annotations/instances_{split}.json", f"annotations/captions_{split}.json"
        if inst not in names or capf not in names:
            return None
        images, cats, anns = _instances(z.read(inst))
        caps = _captions(z.read(capf))
    return images, cats, anns, caps


def seeds(raw_dir: str, limit: int | None = None):
    """The seeds of COCO 2017, val2017 first, then train2017 (an image without captions or with explicit words is skipped)."""
    STATS.clear()
    n = 0
    for split in SPLITS:
        got = _load(raw_dir, split)
        if got is None:
            continue
        images, cats, anns, caps = got
        cat_names = {c["id"]: c["name"] for c in cats}
        cat_super = {c["name"]: c.get("supercategory", "") for c in cats}
        for im in images:
            if limit is not None and n >= limit:
                return
            STATS["images"] += 1
            s = build(im["id"], im["width"], im["height"], anns.get(im["id"], []), caps.get(im["id"], []), cat_names, cat_super)
            if s is not None:
                n += 1
                STATS["seeds"] += 1
                yield s
