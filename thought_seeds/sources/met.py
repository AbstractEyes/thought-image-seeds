"""thought_seeds.sources.met - The Metropolitan Museum of Art Open Access (MetObjects.csv, CC0) to seeds.

Only the rows marked Is Public Domain = True. The records come from the catalogue fields, never from a guess: the medium (form medium),
the begin and end dates when both fall in one period (form period), the department / classification / object name (the domain, and
for an object the thing itself: a bowl, a sword guard, a statuette), the curated subject tags (person, thing, setting, weather, time,
angle, pose; the genre), and a title only when every word of it is a plain generic word (no name). The hint is a few plain sentences
built from the same fields (object, medium, date, culture, the tagged subjects, a generic title); never an artist, a sitter, a
named title, a period named after a ruler, or a credit line.

This module also holds the museum word maps the other museum sources share (aic, nga, cleveland import them from here)."""
from __future__ import annotations

import csv
import hashlib
import os
import re
import sys

from .. import core, maps

DATASET = "met"
LICENSE = "CC0 1.0"
URL = "https://github.com/metmuseum/openaccess"
ATTRIBUTION = "The Metropolitan Museum of Art Open Access, MetObjects.csv (CC0 1.0), public-domain objects only"
CITATION = """@misc{met_openaccess,
  author       = {{The Metropolitan Museum of Art}},
  title        = {The Metropolitan Museum of Art Open Access: MetObjects.csv},
  year         = {2017},
  howpublished = {\\url{https://github.com/metmuseum/openaccess}},
  note         = {Released under Creative Commons Zero (CC0 1.0); updated weekly; accessed 2026-10-19}
}"""
TAKEN = ("records + hint: public-domain rows of MetObjects.csv (Medium, Object Begin/End Date, Department, Classification, Object "
         "Name, Culture, Tags, generic titles only); no artist, sitter, named title, period name or credit line")
CSV_URL = "https://media.githubusercontent.com/media/metmuseum/openaccess/master/MetObjects.csv"
OBJECT_URL = "https://www.metmuseum.org/art/collection/search/{}"

# ------------------------------------------------------------------ shared museum helpers (aic, nga, cleveland)


def download(url: str, path: str, params: dict | None = None, headers: dict | None = None, timeout: int = 120) -> int:
    """`url` to `path` unless the file is there (idempotent); a .part file renamed on success. -> the file's size in bytes."""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return os.path.getsize(path)
    import requests
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with requests.get(url, params=params, headers=headers, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    os.replace(tmp, path)
    return os.path.getsize(path)


def stable_order(ids) -> list:
    """The ids in a stable pseudo-random order (sha1 of the id), so a `limit` takes a spread of the collection, not its first shelf."""
    return sorted(ids, key=lambda i: hashlib.sha1(str(i).encode("utf-8")).hexdigest())


# words that make a row sexually explicit (the dataset drops explicit material; nudes of the art-historical kind stay)
EXPLICIT = re.compile(r"\berotic|\berotica\b|\bshunga\b|phall|pornograph|\bsexual|\bsex\b|intercourse|genital|brothel|\bimpale", re.I)

# the subject terms (museum tags, lower case; a singular finds its plural) to records -------------------------------------------
PERSON = {"men": ("gender", "man"), "women": ("gender", "woman"), "boys": ("gender", "boy"), "girls": ("gender", "girl"),
          "actresses": ("gender", "woman"), "actors": ("gender", "man"), "kings": ("gender", "man"), "queens": ("gender", "woman"),
          "princes": ("gender", "man"), "princesses": ("gender", "woman"), "emperors": ("gender", "man"), "nuns": ("gender", "woman"),
          "female nudes": ("gender", "woman"), "male nudes": ("gender", "man"), "female figures": ("gender", "woman"),
          "male figures": ("gender", "man"), "children": ("age", "child"), "infants": ("age", "baby"), "babies": ("age", "baby"),
          "old age": ("age", "elderly"), "elderly": ("age", "elderly"),
          "soldiers": ("role", "soldier"), "musicians": ("role", "musician"), "dancers": ("role", "dancer"),
          "farmers": ("role", "farmer"), "monks": ("role", "monk"), "athletes": ("role", "athlete"), "jockeys": ("role", "rider"),
          "mothers": ("role", "mother"), "fathers": ("role", "father"), "students": ("role", "student"), "nurses": ("role", "nurse"),
          "brides": ("role", "bride"), "merchants": ("role", "vendor"), "vendors": ("role", "vendor"), "reading": ("role", "reader"),
          "readers": ("role", "reader"), "swimmers": ("role", "swimmer"), "chefs": ("role", "chef"), "guards": ("role", "guard"),
          "travelers": ("role", "traveller"), "travellers": ("role", "traveller"), "equestrians": ("role", "rider"),
          "horsemen": ("role", "rider")}
ROLE_GENDER = {"mother": "woman", "father": "man", "bride": "woman", "nun": "woman"}
HUMAN = {"human figures", "figures", "people", "couples", "crowd", "crowds", "portraits", "self-portraits", "heads", "faces",
         "spectators", "servants", "shepherds", "sailors", "warriors", "knights", "saints", "apostles", "angels", "putti", "bishops",
         "popes", "priests", "generals", "admirals", "doctors", "poets", "artists", "authors", "singers", "acrobats", "clowns",
         "gardeners", "teachers", "philosophers", "blacksmiths", "bakers", "butchers", "barbers", "magicians", "witches", "samurai",
         "gladiators", "amazons", "family", "lovers", "prisoners", "slaves", "police", "firefighters", "astronomers", "scientists",
         "architects", "clergy", "marines", "nymphs", "muses", "maenads", "bacchantes", "satyrs", "centaurs"} | set(PERSON)
SCENE = {"crowd": ("scene", "layout", "crowd"), "crowds": ("scene", "layout", "crowd"), "snow": ("scene", "weather", "snow"),
         "rain": ("scene", "weather", "rain"), "storms": ("scene", "weather", "storm"), "fog": ("scene", "weather", "fog"),
         "wind": ("scene", "weather", "wind"), "night": ("scene", "time", "night"), "evening": ("scene", "time", "late evening"),
         "morning": ("scene", "time", "morning"), "dawn": ("scene", "time", "dawn"), "sunsets": ("scene", "time", "dusk"),
         "sunset": ("scene", "time", "dusk"), "twilight": ("scene", "time", "dusk"), "moonlight": ("shot", "light", "moonlight"),
         "profiles": ("shot", "angle", "profile"), "profile": ("shot", "angle", "profile"), "dancing": ("body", "pose", "dancing"),
         "walking": ("body", "pose", "walking"), "running": ("body", "pose", "running"), "kneeling": ("body", "pose", "kneeling"),
         "climbing": ("body", "pose", "climbing"), "seated figures": ("body", "pose", "sitting"),
         "standing figures": ("body", "pose", "standing"), "reclining figures": ("body", "pose", "lying"),
         "abstraction": ("form", "style", "abstract"), "symmetry": ("form", "compose", "symmetry")}
SETTING = {"gardens": "garden", "forests": "forest", "woods": "forest", "beaches": "beach", "ruins": "ruins", "bridges": "bridge",
           "temples": "temple", "shrines": "temple", "cathedrals": "cathedral", "kitchens": "kitchen", "courtyards": "courtyard",
           "farms": "farm", "markets": "market street", "harbors": "harbour", "harbours": "harbour", "ports": "harbour",
           "caves": "cave", "deserts": "desert", "cliffs": "cliff", "lighthouses": "lighthouse", "vineyards": "vineyard",
           "libraries": "library", "ballrooms": "ballroom", "piers": "pier", "docks": "pier", "swamps": "swamp", "meadows": "meadow",
           "attics": "attic", "laboratories": "laboratory", "greenhouses": "greenhouse", "stadiums": "stadium", "workshops": "workshop",
           "cafes": "cafe", "cafe": "cafe", "classrooms": "classroom", "alleys": "alley", "hospitals": "hospital ward"}
# the thing (the main non-person subject), in priority order: an animal or a made thing before a plant, a plant before the land
THINGS = [("horses", "horse"), ("dogs", "dog"), ("cats", "cat"), ("lions", "lion"), ("tigers", "tiger"), ("leopards", "leopard"),
          ("elephants", "elephant"), ("deer", "deer"), ("cows", "cow"), ("cattle", "cow"), ("bulls", "bull"), ("ox", "ox"),
          ("oxen", "ox"), ("sheep", "sheep"), ("lambs", "lamb"), ("goats", "goat"), ("rams", "ram"), ("pigs", "pig"),
          ("boars", "boar"), ("donkeys", "donkey"), ("camels", "camel"), ("monkeys", "monkey"), ("baboons", "baboon"),
          ("bears", "bear"), ("wolves", "wolf"), ("foxes", "fox"), ("rabbits", "rabbit"), ("hares", "hare"), ("squirrels", "squirrel"),
          ("mice", "mouse"), ("rats", "rat"), ("bats", "bat"), ("giraffes", "giraffe"), ("zebras", "zebra"), ("rhinoceros", "rhinoceros"),
          ("hippos", "hippo"), ("buffalos", "buffalo"), ("antelope", "antelope"), ("ibex", "ibex"), ("panthers", "panther"),
          ("cheetahs", "cheetah"), ("jaguars", "jaguar"), ("jackals", "jackal"), ("hedgehogs", "hedgehog"),
          ("eagles", "eagle"), ("owls", "owl"), ("peacocks", "peacock"), ("swans", "swan"), ("cranes", "crane"), ("ducks", "duck"),
          ("geese", "goose"), ("roosters", "rooster"), ("hens", "hen"), ("chickens", "chicken"), ("turkeys", "turkey"),
          ("parrots", "parrot"), ("doves", "dove"), ("pigeons", "pigeon"), ("falcons", "falcon"), ("hawks", "hawk"),
          ("pheasants", "pheasant"), ("pelicans", "pelican"), ("birds", "bird"),
          ("fish", "fish"), ("dolphins", "dolphin"), ("whales", "whale"), ("octopus", "octopus"), ("crabs", "crab"),
          ("lobsters", "lobster"), ("crayfish", "crayfish"), ("seahorses", "seahorse"), ("turtles", "turtle"), ("frogs", "frog"),
          ("snakes", "snake"), ("serpents", "snake"), ("crocodiles", "crocodile"), ("alligators", "alligator"), ("lizards", "lizard"),
          ("salamanders", "salamander"), ("butterflies", "butterfly"), ("dragonflies", "dragonfly"), ("bees", "bee"),
          ("spiders", "spider"), ("scorpions", "scorpion"), ("snails", "snail"), ("insects", "insect"), ("shells", "shell"),
          ("dragons", "dragon"), ("griffins", "griffin"), ("unicorns", "unicorn"), ("phoenix", "phoenix"), ("sphinx", "sphinx"),
          ("mermaids", "mermaid"), ("hippocamps", "hippocamp"), ("minotaurs", "minotaur"), ("monsters", "monster"),
          ("skeletons", "skeleton"), ("skulls", "skull"),
          ("boats", "boat"), ("ships", "ship"), ("shipwrecks", "shipwreck"), ("carriages", "carriage"), ("chariots", "chariot"),
          ("carts", "cart"), ("wagons", "wagon"), ("sleighs", "sleigh"), ("trains", "train"), ("railways", "train"),
          ("streetcars", "streetcar"), ("bicycles", "bicycle"), ("cars", "car"), ("buses", "bus"), ("hot air balloons", "balloon"),
          ("balloons", "balloon"), ("kites", "kite"),
          ("books", "book"), ("chairs", "chair"), ("tables", "table"), ("beds", "bed"), ("benches", "bench"), ("stools", "stool"),
          ("couches", "couch"), ("thrones", "throne"), ("cradles", "cradle"), ("desks", "desk"), ("cabinets", "cabinet"),
          ("chests", "chest"), ("screens", "screen"), ("clocks", "clock"), ("mirrors", "mirror"), ("windows", "window"),
          ("doors", "door"), ("doorways", "doorway"), ("gates", "gate"), ("ladders", "ladder"), ("stairs", "stairs"),
          ("fences", "fence"), ("wells", "well"), ("fountains", "fountain"), ("baskets", "basket"), ("umbrellas", "umbrella"),
          ("parasols", "umbrella"), ("lanterns", "lantern"), ("lamps", "lamp"), ("candles", "candle"), ("candlesticks", "candlestick"),
          ("candelabra", "candelabrum"), ("chandelier", "chandelier"), ("flags", "flag"), ("banners", "banner"), ("signs", "sign"),
          ("swords", "sword"), ("daggers", "dagger"), ("knives", "knife"), ("spears", "spear"), ("shields", "shield"),
          ("helmets", "helmet"), ("bow and arrow", "bow"), ("firearms", "gun"), ("cannons", "cannon"), ("axes", "axe"),
          ("drums", "drum"), ("violins", "violin"), ("violas", "viola"), ("cellos", "cello"), ("guitars", "guitar"), ("lutes", "lute"),
          ("mandolins", "mandolin"), ("harps", "harp"), ("lyres", "lyre"), ("flutes", "flute"), ("trumpets", "trumpet"),
          ("bagpipes", "bagpipe"), ("pianos", "piano"), ("organs", "organ"), ("bells", "bell"),
          ("musical instruments", "instrument"), ("vases", "vase"), ("urns", "urn"), ("jugs", "jug"), ("pitchers", "pitcher"),
          ("ewers", "ewer"), ("bowls", "bowl"), ("cups", "cup"), ("goblets", "goblet"), ("chalices", "chalice"),
          ("drinking glasses", "glass"), ("bottles", "bottle"), ("jars", "jar"), ("teapots", "teapot"), ("kettles", "kettle"),
          ("buckets", "bucket"), ("barrels", "barrel"), ("trays", "tray"), ("dishes", "dish"), ("boxes", "box"),
          ("playing cards", "playing card"), ("dice", "dice"), ("fans", "fan"), ("masks", "mask"), ("crowns", "crown"),
          ("globes", "globe"), ("maps", "map"), ("scrolls", "scroll"), ("easels", "easel"), ("palettes", "palette"),
          ("telescopes", "telescope"), ("sundials", "sundial"), ("hourglass", "hourglass"),
          ("anchors", "anchor"), ("cameras", "camera"), ("dolls", "doll"), ("puppets", "puppet"), ("toys", "toy"),
          ("spinning wheel", "spinning wheel"), ("looms", "loom"), ("tents", "tent"), ("windmills", "windmill"),
          ("watermills", "watermill"), ("haystacks", "haystack"), ("statues", "statue"), ("sculpture", "statue"),
          ("columns", "column"), ("obelisks", "obelisk"), ("pyramids", "pyramid"), ("arches", "arch"), ("towers", "tower"),
          ("castles", "castle"), ("churches", "church"), ("chapels", "chapel"), ("mosques", "mosque"), ("pagodas", "pagoda"),
          ("stupas", "stupa"), ("palaces", "palace"), ("houses", "house"), ("barns", "barn"), ("factories", "factory"),
          ("monuments", "monument"), ("tombs", "tomb"), ("altars", "altar"), ("fireplaces", "fireplace"), ("curtains", "curtain"),
          ("roses", "rose"), ("peonies", "peony"), ("lotuses", "lotus"), ("lilies", "lily"), ("tulips", "tulip"), ("daisies", "daisy"),
          ("poppies", "poppy"), ("sunflowers", "sunflower"), ("orchids", "orchid"), ("water lilies", "water lily"),
          ("chrysanthemums", "chrysanthemum"), ("irises", "iris"), ("flowers", "flower"), ("bamboo", "bamboo"), ("grapes", "grapes"),
          ("apples", "apple"), ("peaches", "peach"), ("pears", "pear"), ("lemons", "lemon"), ("cherries", "cherry"),
          ("strawberries", "strawberry"), ("pomegranates", "pomegranate"), ("gourds", "gourd"), ("fruit", "fruit"),
          ("vegetables", "vegetable"), ("bread", "bread"), ("trees", "tree"), ("palms", "palm tree"), ("cypresses", "cypress"),
          ("oaks", "oak"), ("olive trees", "olive tree"), ("pinecones", "pinecone"), ("acorns", "acorn"), ("vines", "vine"),
          ("leaves", "leaf"), ("plants", "plant"), ("garlands", "garland"), ("wreaths", "wreath"),
          ("mountains", "mountain"), ("volcanoes", "volcano"), ("hills", "hill"), ("waterfalls", "waterfall"), ("rivers", "river"),
          ("streams", "stream"), ("lakes", "lake"), ("ponds", "pond"), ("canals", "canal"), ("waves", "wave"), ("seas", "sea"),
          ("oceans", "sea"), ("islands", "island"), ("rainbows", "rainbow"), ("clouds", "cloud"), ("moon", "moon"), ("sun", "sun"),
          ("stars", "star")]
THING_OF = dict(THINGS)
THING_RANK = {k: i for i, (k, _) in enumerate(THINGS)}
# the genre, in priority order: (the terms any of which gives it, the genre)
GENRES = [({"self-portraits", "self-portrait", "self portraits"}, "self portrait"),
          ({"portraits", "portrait"}, "portrait"),
          ({"crucifixion", "annunciation", "nativity", "holy family", "madonna and child", "saints", "apostles", "angels",
            "adoration of the magi", "adoration of the shepherds", "last supper", "entombment", "lamentation", "resurrection",
            "descent from the cross", "bearing the cross", "assumption of the virgin", "coronation of the virgin", "visitation",
            "pentecost", "evangelists", "bodhisattvas", "buddha", "buddhism", "hinduism", "daoism", "christianity", "bible",
            "religious", "devotional"}, "religious"),
          ({"mythology", "greek mythology", "norse mythology", "mythological", "satyrs", "nymphs", "muses", "maenads", "centaurs",
            "bacchantes", "gods", "goddess"}, "mythology"),
          ({"battles", "wars", "massacres", "american civil war", "trojan war", "french revolution", "world war i", "world war ii",
            "military", "army", "war"}, "war"),
          ({"female nudes", "male nudes", "nudes", "nude"}, "nude study"),
          ({"still life", "still lifes", "still-life"}, "still life"),
          ({"seascapes", "seascape", "marines", "marine"}, "seascape"),
          ({"landscapes", "landscape"}, "landscape"),
          ({"cityscapes", "cityscape", "cities", "towns", "city views"}, "cityscape"),
          ({"street scene", "streets"}, "street"),
          ({"interiors", "interior", "bedrooms", "dining rooms", "living rooms"}, "interior"),
          ({"satire", "caricature", "caricatures", "politics"}, "caricature"),
          ({"genre scene", "genre scenes", "daily life", "domestic scenes", "working", "drinking", "smoking", "dining", "eating",
            "playing", "games", "fishing", "hunting", "sewing", "cooking", "washing", "party", "picnics", "leisure", "bathing",
            "tea drinking", "harvesting", "agriculture", "skating", "rowing", "sailing", "reading", "writing", "music", "dancing"},
           "genre scene"),
          ({"baseball", "boxing", "sports", "tennis", "wrestling", "football", "fencing", "billiards", "archery"}, "sport"),
          ({"fashion", "costumes"}, "fashion"),
          ({"architecture", "buildings", "architectural drawings", "ornament & architecture"}, "architecture"),
          ({"ornament", "ornaments", "grotesques", "cartouches", "palmettes", "acanthus"}, "ornament"),
          ({"maps"}, "map"),
          ({"animals", "horses", "dogs", "cats", "birds", "lions"}, "animal study"),
          ({"flowers", "plants", "botany", "botanical"}, "botanical")]
GENRE_NEEDS_PEOPLE = {"genre scene", "sport", "fashion"}
# generic subject words that may be named in the hint though they give no record (no proper name of any kind)
HINT_SUBJECTS = (HUMAN | set(SCENE) | set(SETTING) | set(THING_OF) | {t for terms, _ in GENRES for t in terms} |
                 {"animals", "architecture", "buildings", "ornament", "coat of arms", "hieroglyphs", "calligraphy", "cross",
                  "writing", "insignia", "heraldry", "emblems", "medallions", "zodiac", "allegory", "death", "suffering", "sadness",
                  "fear", "anger", "love", "music", "theatre", "dance", "opera", "circus", "ceremony", "processions", "weddings",
                  "funerals", "burials", "christmas", "winter", "summer", "spring", "autumn", "sky", "fire", "fireworks", "hands",
                  "deities", "religion", "people", "nature", "water", "rocks", "foliage", "decoration", "vessels", "containers",
                  "furniture", "clouds", "geometric motif", "stripes", "spirals", "grids", "circles", "squares", "triangles",
                  "feet", "eyes", "hair", "legs", "food", "wine", "tea", "coffee", "money", "coins", "medals", "documents",
                  "inscriptions", "scarabs", "amulets", "hats", "shoes", "boots", "gloves", "dresses", "robes", "uniforms",
                  "military clothing", "jewelry", "necklaces", "earrings", "rings", "headdresses", "wigs", "armor", "weapons",
                  "cityscapes", "roads", "streets", "villages", "cities", "towns", "parks", "camps", "stage design"})
HINT_SUBJECTS = {t for t in HINT_SUBJECTS if not re.search(r"virgin|madonna|christ|buddha|magi", t)}   # a holy figure's name stays out
# culture words a hint may carry (peoples, nations and places by their adjective; none of them is named after a person)
CULTURES = {"american", "native american", "british", "english", "scottish", "irish", "welsh", "french", "dutch", "flemish",
            "netherlandish", "south netherlandish", "north netherlandish", "german", "southern german", "austrian", "swiss",
            "italian", "spanish", "catalan", "portuguese", "belgian", "danish", "swedish", "norwegian", "finnish", "russian", "polish",
            "bohemian", "czech", "hungarian", "greek", "roman", "etruscan", "cypriot", "minoan", "mycenaean", "byzantine", "coptic",
            "frankish", "visigothic", "langobardic", "celtic", "egyptian", "assyrian", "babylonian", "sumerian", "elamite",
            "phoenician", "anatolian", "hittite", "persian", "iranian", "turkish", "syrian", "arabian", "islamic", "moroccan",
            "indian", "south asian", "nepalese", "tibetan", "chinese", "japanese", "korean", "thai", "vietnamese", "cambodian",
            "khmer", "burmese", "javanese", "balinese", "indonesian", "filipino", "mexican", "peruvian", "colombian", "aztec",
            "maya", "mayan", "inca", "olmec", "moche", "nasca", "chimu", "wari", "paracas", "mezcala", "huastec", "zapotec",
            "mixtec", "teotihuacan", "canadian", "australian", "african", "european", "asian", "yoruba", "akan", "asante", "edo",
            "kongo", "luba", "dogon", "bamana", "senufo", "fang", "baule", "dan", "chokwe", "kuba", "songye", "hawaiian", "maori",
            "polynesian", "melanesian", "micronesian", "papua new guinea", "japan", "china", "korea", "india", "iran", "egypt",
            "france", "italy", "spain", "germany", "england", "mexico", "peru", "thailand", "tibet", "nepal", "indonesia",
            "cambodia", "vietnam", "pakistan", "afghanistan", "syria", "turkey", "iraq"}
# words a title may be made of for it to enter a hint (all of its words, case aside); given names that are also words are left out
STOP = {"a", "an", "the", "of", "and", "or", "with", "in", "on", "at", "by", "from", "to", "for", "his", "her", "their", "its",
        "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "one", "some", "several", "many", "under", "over",
        "near", "beside", "before", "after", "into", "out", "up", "down", "between", "behind", "above", "below", "among", "against",
        "across", "along", "around", "through", "during", "without", "is", "are", "was", "s", "no", "not", "this", "that", "who",
        "as", "pair", "set", "part", "piece", "fragment", "fragments", "detail", "study", "studies", "sketch", "view", "views", "side",
        "belt", "watch", "cook",
        "scene", "scenes", "design", "designs", "figure", "figures", "head", "heads", "bust", "portrait", "portraits", "untitled",
        "plate", "page", "leaf", "folio", "sheet", "verso", "recto", "left", "right", "half", "small", "large", "little", "great",
        "big", "old", "young", "new", "early", "late", "first", "second", "third", "last", "other", "another", "same", "seated",
        "standing", "lying", "reclining", "kneeling", "walking", "sleeping", "reading", "writing", "playing", "dancing", "holding",
        "wearing", "eating", "drinking", "bathing", "fishing", "hunting", "riding", "working", "resting", "looking", "sitting",
        "running", "praying", "singing", "smoking", "sewing", "knitting", "spinning", "carrying", "feeding", "picking",
        "gathering", "washing", "cooking", "landscape", "landscapes", "still", "life", "interior", "exterior", "morning",
        "evening", "night", "day", "noon", "afternoon", "winter", "summer", "spring", "autumn", "fall", "snow", "rain", "storm",
        "sunset", "sunrise", "moonlight", "light", "dark", "shade", "shadow", "shadows", "sea", "seascape", "sky", "clouds",
        "cloud", "wind", "water", "field", "fields", "road", "path", "street", "streets", "village", "town", "city", "harbor",
        "harbour", "port", "bay", "coast", "shore", "beach", "rocks", "rock", "river", "stream", "lake", "pond", "pool",
        "waterfall", "mountain", "mountains", "hill", "hills", "valley", "forest", "woods", "wood", "trees", "tree", "garden",
        "gardens", "park", "meadow", "farm", "barn", "house", "houses", "cottage", "church", "chapel", "temple", "ruins", "ruin",
        "bridge", "tower", "castle", "palace", "gate", "wall", "window", "door", "room", "kitchen", "studio", "court", "courtyard",
        "market", "shop", "inn", "boat", "boats", "ship", "ships", "sail", "sails", "man", "men", "woman", "women", "boy", "boys",
        "girl", "girls", "child", "children", "baby", "infant", "lady", "ladies", "gentleman", "gentlemen", "youth", "mother",
        "father", "family", "couple", "lovers", "peasant", "peasants", "farmer", "farmers", "shepherd", "shepherdess", "fisherman",
        "fishermen", "soldier", "soldiers", "horseman", "rider", "musician", "musicians", "dancer", "dancers", "monk", "nun",
        "priest", "beggar", "vendor", "merchant", "sailor", "warrior", "hunter", "huntsman", "player", "players", "card", "cards",
        "nude", "nudes", "torso", "hand", "hands", "foot", "feet", "eye", "eyes", "face", "profile", "horse", "horses", "dog",
        "dogs", "cat", "cats", "bird", "birds", "cow", "cows", "cattle", "sheep", "goat", "goats", "lion", "lions", "deer",
        "stag", "fish", "duck", "ducks", "rooster", "hen", "chickens", "eagle", "owl", "parrot", "monkey", "elephant", "tiger",
        "dragon", "dragons", "flowers", "flower", "fruit", "fruits", "basket", "vase", "bowl", "cup", "jar", "jug", "pitcher",
        "bottle", "glass", "dish", "table", "chair", "bed", "book", "books", "letter", "mirror", "lamp", "candle", "clock",
        "fan", "hat", "dress", "costume", "robe", "mask", "box", "chest", "cabinet", "panel", "screen", "scroll", "album",
        "textile", "fabric", "tile", "tiles", "border", "ornament", "ornaments", "pattern", "patterns", "frieze", "medallion",
        "cartouche", "vessel", "plaque", "relief", "statue", "statuette", "figurine", "column", "capital", "arch", "fountain",
        "red", "blue", "green", "yellow", "white", "black", "brown", "grey", "gray", "gold", "golden", "silver", "pink", "purple",
        "orange", "composition", "abstraction", "number", "no", "group", "procession", "dance", "music", "concert", "party",
        "feast", "harvest", "hunt", "battle", "war", "wedding", "funeral", "bath", "bathers", "picnic", "game", "games",
        "lesson", "school", "visit", "return", "departure", "arrival", "conversation", "game", "toilette", "pastoral", "scenery",
        "copy", "after", "style", "manner", "attributed", "anonymous", "unknown", "artist", "maker", "workshop", "circle",
        "follower", "school", "type", "model", "fragmentary", "decorated", "painted", "carved", "inscribed", "standing", "head",
        "ewer", "teapot", "plate", "saucer", "spoon", "fork", "knife", "sword", "dagger", "shield", "helmet", "armor", "armour",
        "bracelet", "necklace", "ring", "earring", "earrings", "brooch", "pendant", "bead", "beads", "amulet", "seal", "coin",
        "medal", "button", "buckle", "comb", "pin", "lantern", "umbrella", "cart", "carriage", "wagon", "train", "station",
        "factory", "mill", "windmill", "bridge", "tent", "camp", "bench", "fence", "ladder", "well", "path", "steps", "stairs"}
TITLE_WORDS = (STOP | {w for k in list(HINT_SUBJECTS) + list(THING_OF.values()) + list(SETTING.values()) for w in k.split()}
               | {w for m in maps.ALL.values() for k in m for w in k.split()}) - core.GIVEN_NAMES


def plural_keys(term: str) -> list:
    """A subject term and its plural forms (the maps hold the museums' plural tags; another museum may give the singular)."""
    t = term.strip().lower()
    out = [t, t + "s", t + "es"]
    if t.endswith("y"):
        out.append(t[:-1] + "ies")
    if t.endswith("f"):
        out.append(t[:-1] + "ves")
    irregular = {"man": "men", "woman": "women", "child": "children", "mouse": "mice", "goose": "geese", "ox": "oxen",
                 "person": "people", "fish": "fish", "deer": "deer", "sheep": "sheep", "nude": "nudes"}
    if t in irregular:
        out.insert(1, irregular[t])
    return out


def norm_terms(terms) -> list:
    """Subject terms lower-cased and folded to the map's keys where a plural form is known; the order kept, duplicates dropped."""
    known = set(HINT_SUBJECTS) | set(PERSON) | set(SCENE) | set(SETTING) | set(THING_OF)
    out = []
    for t in terms:
        t = core.ascii_text(t or "").lower().strip()
        if not t:
            continue
        key = next((k for k in plural_keys(t) if k in known), t)
        if key not in out:
            out.append(key)
    return out


def title_ok(title: str, vocab: set | None = None) -> str | None:
    """A title in lower case when every word of it is a plain generic word (no name, no foreign phrase), else None. `vocab`: the
    plain words of the source's own text corpus (core.corpus_vocab: words that live in lower case there), allowed beside the
    list."""
    t = re.sub(r"\s*\([^)]*\)", "", core.ascii_text(title or "")).strip()     # a bracketed note goes (it may hold a name)
    if not t or len(t) > 80 or any(c in t for c in "|()[]:;\"") or re.search(r"\d", t):
        return None
    words = re.findall(r"[A-Za-z']+", t.replace("'s", ""))
    ok = TITLE_WORDS | (vocab or set())
    if not words or any(w.lower() not in ok or w.lower() in core.GIVEN_NAMES or w.lower() in NAME_TITLES for w in words):
        return None
    if ADDRESS.search(t.lower()):                                    # 'king lear', 'lady jane': a title of address and a name
        return None
    return t.lower().strip(" .,")


NAME_TITLES = {"mr", "mrs", "ms", "miss", "mister", "mme", "mlle", "madame", "monsieur", "mademoiselle", "sir", "dame", "dr", "st",
               "san", "santa", "don", "dona", "fra", "signor", "signora", "herr", "frau", "de", "van", "von", "da", "di", "del",
               "della", "der", "den", "du", "le", "la", "mac", "mc", "ibn", "bin"}
ADDRESS = re.compile(r"\b(lady|lord|king|queen|prince|princess|duke|duchess|count|countess|baron|baroness|captain|general|colonel|"
                     r"bishop|cardinal|pope|emperor|empress|saint|uncle|aunt|cousin|brother|sister|father|mother)\s+"
                     r"(?!of\b|and\b|with\b|in\b|at\b|on\b|by\b|from\b|to\b|for\b|or\b|is\b|was\b|reading\b|seated\b|standing\b)"
                     r"[a-z]")


def culture_ok(culture: str) -> str | None:
    """The culture's first part when it is a people or a nation word of the list (not named after a person), else None."""
    c = core.ascii_text(culture or "").split(",")[0].split(";")[0]
    c = re.sub(r"^(probably|possibly|perhaps|likely)\s+", "", c.strip(), flags=re.I).strip(" ?.")
    return c if c and c.lower() in CULTURES else None


def plain_phrase(text: str, max_len: int = 120) -> str | None:
    """A catalogue phrase (a medium, an object name, a date) in lower case when it holds no capitalized word past its first and
    no bracketed note; else None (a medium like 'pen and ink on Whatman paper' carries a maker's name)."""
    t = core.ascii_text(re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text or "")).strip(" ;,.")
    t = re.sub(r"\s+", " ", t)
    if not t or len(t) > max_len:
        return None
    words = t.split()
    if any(w not in core.COMMON_CAPS for w in core._CAP.findall(" ".join(words[1:]))):
        return None
    return t[0].lower() + t[1:] if not t[:2].isupper() else t


NOLIST = re.compile(r"(?<![a-z])(chalk|crayon|silverpoint|metalpoint|conte|bistre|sanguine|porcelain|stoneware|silk|linen|cotton|"
                    r"wool|silver|gold|ivory|jade|wood|glass|iron|steel|stone|limestone|sandstone|alabaster|copper|brass|"
                    r"lacquer|enamel|leather|faience|bone|shell)(?![a-z])")


def _medium_line(text: str) -> str:
    """A catalogue medium line as medium_of reads it: lower case, without a 'with ...' tail, a bracketed note or mosaic glass
    (millefiori is not a mosaic), a '-printed' compound opened ('woodblock-printed' reads as a woodblock print)."""
    t = re.split(r"\bwith\b|\bwhich\b", (text or "").lower())[0]
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"mosaic[- ]glass|mosaic technique|glass[, ]+mosaic", " ", t)
    return re.sub(r"-(printed|print)\b", r" \1", t)


def _read_medium(text: str) -> tuple:
    """-> (the medium value or None, whether the line's first technique is one the list has no value for)."""
    t = _medium_line(text)
    first_clause = t.split(";")[0]
    for part in ([first_clause, t] if ";" in t else [t]):
        pat = maps._pattern(id(maps.MEDIUM), tuple(maps.MEDIUM))
        m = pat.search(part)
        n = NOLIST.search(part)
        if n and (not m or n.start() < m.start()):
            return None, False
        if m:
            v = maps.MEDIUM[m.group(1)]
            return v, v is None
    return None, False


def medium_of(text: str) -> str | None:
    """form medium from a catalogue medium line: the first painting / print / material word of the list, a 'with ...' tail left
    out (a 'pottery fragment with ink inscription' is not an ink work), and nothing when a material that has no list value comes
    first ('red chalk; framing lines in black ink' is a chalk drawing, not an ink one; 'silver, gilt' is not a silver print) or the
    first technique named has none ('engraving; printed in black ink')."""
    return _read_medium(text)[0]


def medium_blocked(text: str) -> bool:
    """Whether a medium line's first technique is one the list has no value for ('engraving'): a source then reads no second
    field for the medium (an engraving's 'ink' material does not make it an ink work)."""
    return _read_medium(text)[1]


# cultures and departments outside the European tradition: no European era name for their works (maps.period_of, western=False)
NON_WESTERN = re.compile(
    r"\b(japan|japanese|china|chinese|korea|korean|india|indian|iran|iranian|persia|persian|turkish|turkey|ottoman|islamic|arab|"
    r"arabian|syria|syrian|iraq|egypt|egyptian|tibet|tibetan|nepal|nepalese|thai|thailand|cambodia|cambodian|khmer|vietnam|"
    r"vietnamese|indonesia|indonesian|java|javanese|bali|balinese|burma|burmese|pakistan|afghanistan|himalayan|asian|asia|africa|"
    r"african|yoruba|akan|asante|kongo|luba|dogon|bamana|senufo|baule|chokwe|kuba|songye|aztec|mexica|maya|mayan|inca|olmec|moche|"
    r"nasca|nazca|chimu|wari|paracas|mezcala|huastec|zapotec|mixtec|teotihuacan|chancay|navajo|native american|hawaii|hawaiian|"
    r"maori|polynesia|polynesian|melanesia|melanesian|micronesia|oceania|papua|peru|peruvian|mexico|mexican|mesoamerica|"
    r"mesoamerican|andean|pre-columbian|precolumbian)\b", re.I)
NON_WESTERN_DEPTS = {"Asian Art", "Islamic Art", "Arts of Africa, Oceania, and the Americas", "Egyptian Art", "Ancient West Asian Art"}


def apply_subjects(spec: core.Spec, terms: list, domain: str, thing_from_tags: bool = True) -> dict:
    """Records from subject terms (already normalized). -> {"genre": str|None, "people": bool, "thing": str|None}."""
    genders, ages, roles = [], [], []
    for t in terms:
        if t in PERSON:
            attr, val = PERSON[t]
            (genders if attr == "gender" else ages if attr == "age" else roles).append(val)
    people = any(t in HUMAN for t in terms)
    for r in roles:
        if r in ROLE_GENDER:
            genders.append(ROLE_GENDER[r])
    # one person system: the terms of different figures must not make one impossible person (a woman of age child, a boy soldier)
    gender = genders[0] if len(set(genders)) == 1 else None
    age = ages[0] if len(set(ages)) == 1 else None
    role = roles[0] if roles else None
    if gender in ("boy", "girl") and role not in (None, "student", "dancer", "musician", "reader", "swimmer", "athlete", "rider"):
        role = None
    adult = gender in ("man", "woman") or role not in (None, "student")
    if age in ("child", "baby", "teen") and adult:
        age = None
    if age in ("elderly", "young adult") and gender in ("boy", "girl"):
        age = None
    if gender:
        spec.set("person", "gender", gender)
    elif not genders and people and ("human figures" in terms or "figures" in terms):
        spec.set("person", "gender", "person")
    if age:
        spec.set("person", "age", age)
    if role:
        spec.set("person", "role", role)
    for t in terms:
        if t in SCENE:
            s, a, v = SCENE[t]
            if s == "body" and not people:
                continue
            spec.set(s, a, v)
        elif t in SETTING:
            spec.set("scene", "setting", SETTING[t])
    thing = None
    if thing_from_tags:
        cands = sorted((THING_RANK[t], THING_OF[t]) for t in terms if t in THING_OF)
        for _, name in cands:
            if spec.set("thing", "name", name):
                thing = name
                break
    genre = None
    for keys, g in GENRES:
        if any(t in keys for t in terms):
            if g in GENRE_NEEDS_PEOPLE and not people:
                continue
            if g == "animal study" and people:
                continue
            if g == "botanical" and (people or domain not in ("illustration", "painting")):
                continue
            genre = g
            break
    return {"genre": genre, "people": people, "thing": thing}


OBJECT_COMPOUNDS = re.compile(r"\b(sword|hand|fire|knee|arm|neck|shin|leg|chest|mud|splash|finger|thumb|nose|cheek|tsuba) ?guards?\b|"
                              r"\bbook ?(case|end|plate|binding)s?\b|\bdancers? ?(mask|costume)s?\b|\bnurse(ry)? ?(chair|bottle)s?\b")


def title_records(spec: core.Spec, gtitle: str, domain: str) -> None:
    """Records a generic title gives: the person (gender, age, role), the pose, the setting, the time, the weather. An object's
    title (a design object: 'sword guard', 'bookcase') names no person or pose, so for design only the setting, time, weather."""
    t = OBJECT_COMPOUNDS.sub(" ", gtitle)
    keys = ("scene setting", "scene time", "scene weather") if domain == "design" else (
        "person gender", "person age", "person role", "scene setting", "scene time", "scene weather", "body pose")
    second = re.search(r"\b(her|his|their)\b", t)       # 'laundress and her child': the child is a second figure
    for key in keys:
        if key == "person age" and second:
            continue
        v = maps.first(t, maps.ALL[key])
        if v:
            sys_, attr = key.split()
            if key == "person gender" and (spec.has("person", "gender") or len(set(maps.find(t, maps.GENDER))) > 1):
                continue
            spec.set(sys_, attr, v)
    if domain != "design" and re.search(r"\breading\b", t):                 # 'woman reading': the shared role map has 'reader'
        spec.set("person", "role", "reader")
    fix_person(spec)


def fix_person(spec: core.Spec) -> None:
    """After the title adds its words: the same one-person rules (no adult of age child, no boy of age elderly)."""
    p = spec.d.get("person", {})
    g, a, r = p.get("gender"), p.get("age"), p.get("role")
    if a in ("child", "baby", "teen") and (g in ("man", "woman") or r not in (None, "student")):
        p.pop("age")
    elif a in ("elderly", "young adult") and g in ("boy", "girl"):
        p.pop("age")
    if p.get("role") in ROLE_GENDER and g and ROLE_GENDER[p["role"]] != g:
        p.pop("role")
    if not p:
        spec.d.pop("person", None)


def fit(text: str, n: int) -> str:
    """Whole sentences of `text` within `n` bytes (after the core's ASCII fold, which is what the hint keeps)."""
    out = []
    for sent in core._SENT.split(core.ascii_text(text or "")):
        if len(" ".join(out + [sent])) > n:
            break
        out.append(sent)
    return " ".join(out).strip()


def subject_sentence(terms: list, limit: int = 12) -> str | None:
    """'Subjects: women, horses, trees.' from the generic terms only (a name never passes; a singular beside its plural goes)."""
    words = [t for t in terms if t in HINT_SUBJECTS and not (t + "s" in terms or t + "es" in terms)][:limit]
    return f"Subjects: {', '.join(words)}." if words else None


def object_noun(name: str) -> tuple:
    """A catalogue object name to (thing name, state): 'Kylix fragment' -> ('kylix', 'fragment'); a name with a capital past its
    first word, or over the budget, gives (None, None)."""
    t = plain_phrase(name, 60)
    if not t:
        return None, None
    state = None
    lead = re.match(r"^(?:a |an |the )?(pair|set|group|fragments?|piece|part|section|sample|length|border|panel) of (?:a |an |the )?",
                    t.lower())
    if lead:
        if lead.group(1).startswith("fragment"):
            state = "fragment"
        t = t[lead.end():]
    t = re.split(r"[,;]| with | of | from | for | in ", t.lower())[0].strip()
    m = re.search(r"\b(fragments?|shards?|sherds?)\b", t)
    if m:
        state = "fragment"
        t = re.sub(r"\b(fragments?|shards?|sherds?)\b", "", t).strip()
    t = core.clean(t)
    if not t or t in ("piece", "object", "sample", "item", "part", "element", "miscellaneous") or len(t) > 17:
        return None, state
    return t, state


# ------------------------------------------------------------------ the Met itself

PAINT_MEDIA = {"oil painting", "tempera", "acrylic", "gouache", "watercolour", "fresco", "pastel"}
PHOTO = re.compile(r"albumen|daguerreotype|ambrotype|tintype|gelatin silver|salted paper|platinum print|palladium print|"
                   r"carbon print|collodion|cyanotype|photogravure|photograph|chromogenic|dye transfer|inkjet print", re.I)
SCULPT_NAME = re.compile(r"\b(statue|statuette|figure|figurine|bust|relief|torso|head|stela|stele|shabti|ushabti|sculpture|"
                         r"group|netsuke|okimono|idol|effigy|caryatid|herm|tomb figure)\b", re.I)
ILLUS_CLASS = ("drawings", "prints", "codices", "manuscripts", "illustrated books", "books", "albums", "calligraphy",
               "ephemera", "papyrus", "stencils", "works on paper")
CLASS_MEDIUM = {"glass-stained": "stained glass", "textiles-tapestries": "tapestry", "mosaics": "mosaic"}
CLASS_TEXTURE = {"textiles-woven": "woven", "textiles-tapestries": "woven", "textiles-rugs": "woven", "textiles-velvets": "velvet"}
BLUE_WHITE = re.compile(r"blue[- ]and[- ]white|underglaze (cobalt )?blue", re.I)
COLOUR_METAL = {"gold": "gold", "silver": "silver"}
COLS = ("Object ID", "Is Public Domain", "Department", "Object Name", "Title", "Culture", "Object Date", "Object Begin Date",
        "Object End Date", "Medium", "Classification", "Tags")


def fetch(raw_dir: str) -> dict:
    path = os.path.join(raw_dir, DATASET, "MetObjects.csv")
    return {"MetObjects.csv": download(CSV_URL, path)}


def domain_of(dept: str, cls: str, name: str, medium_text: str, medium: str | None) -> str:
    c, n = cls.lower(), name.lower()
    if dept == "Photographs" or "photograph" in c or PHOTO.search(medium_text or "") or "photograph" in n:
        return "photograph"
    if any(k in c for k in ("paintings", "miniatures", "pastels & oil sketches")) or re.match(
            r"(painting|hanging scroll|handscroll|album leaf|folding fan mounted)", n):
        return "painting"
    if dept == "Drawings and Prints" or re.match(r"(print|drawing|woodblock|watercolor)", n):
        return "painting" if medium in PAINT_MEDIA else "illustration"
    if any(k in c for k in ("sculpture", "netsuke")) or SCULPT_NAME.search(n):
        return "sculpture"
    if any(k in c for k in ILLUS_CLASS):
        return "painting" if medium in PAINT_MEDIA else "illustration"
    return "design"


def build(row: dict):
    """One MetObjects row (the public-domain ones) to a seed, or None."""
    oid = row["Object ID"].strip()
    title, tags_raw, name = row["Title"], row["Tags"], row["Object Name"]
    if EXPLICIT.search(" ".join((title, tags_raw, name))):
        return None
    medium_text = row["Medium"]
    medium = medium_of(medium_text)
    cls = row["Classification"]
    for k, v in CLASS_MEDIUM.items():
        if k in cls.lower():
            medium = v
    domain = domain_of(row["Department"], cls, name, medium_text, medium)
    terms = norm_terms(t for t in tags_raw.split("|") if t)
    gtitle = title_ok(title)
    if gtitle and gtitle == core.clean(name):
        gtitle = None
    s = core.Spec()
    noun, state = object_noun(name)
    obj_is_thing = domain == "design" or (domain == "sculpture" and noun is not None)
    sub = apply_subjects(s, terms, domain, thing_from_tags=domain != "design")
    if domain == "design" and noun:                       # the object itself is the thing seen (its decoration goes to the hint)
        s.set("thing", "name", noun, overwrite=True)
    elif domain == "sculpture" and noun and not sub["thing"]:
        s.set("thing", "name", noun)
    if obj_is_thing and s.has("thing", "name"):
        if state:
            s.set("thing", "state", state)
        metal = COLOUR_METAL.get(core.clean(medium_text))
        if metal:
            s.set("thing", "colour", metal)
    if gtitle:                                           # a generic title names what is shown
        title_records(s, gtitle, domain)
    fix_person(s)
    if medium:
        s.set("form", "medium", medium)
    for k, v in CLASS_TEXTURE.items():
        if cls.lower().startswith(k):
            s.set("form", "texture", v)
    if "porcelain" in medium_text.lower() and BLUE_WHITE.search(medium_text):
        s.set("form", "palette", "blue and white")
    western = row["Department"] not in NON_WESTERN_DEPTS and not NON_WESTERN.search(row["Culture"])
    per = maps.period_of(row["Object Begin Date"], row["Object End Date"], western)
    if per:
        s.set("form", "period", per)
    genre = sub["genre"]
    if domain == "design" or (domain == "sculpture" and not genre):
        genre = noun or genre or ("object" if domain == "design" else "sculpture")
    if not genre:
        genre = {"photograph": "photograph", "painting": "painting", "illustration": "print" if "print" in cls.lower() else "drawing",
                 "sculpture": "sculpture"}.get(domain, domain)
    parts = []
    obj = plain_phrase(name, 60)
    med = plain_phrase(medium_text, 160)
    if obj and med:
        parts.append(f"{obj[0].upper() + obj[1:]}; {med}.")
    elif obj or med:
        parts.append(f"{(obj or med)[0].upper() + (obj or med)[1:]}.")
    date = plain_phrase(row["Object Date"], 40)
    if date:
        parts.append(f"Made {date}.")
    cul = culture_ok(row["Culture"])
    if cul:
        parts.append(f"Culture: {cul}.")
    ss = subject_sentence(terms)
    if ss:
        parts.append(ss)
    if gtitle:
        parts.append(f'Title: "{gtitle}".')
    allow = (set(cul.split()) if cul else set()) | core.DATE_MARKS          # 'Made ca. 500 BCE.' holds no name
    hint = core.make_hint(core.drop_named(p, allow=allow) for p in parts)
    return core.make_seed(DATASET, oid, domain, genre, s, hint, LICENSE, OBJECT_URL.format(oid),
                          min_records=1 if len(hint) >= 100 else 2)


def rows(raw_dir: str):
    path = os.path.join(raw_dir, DATASET, "MetObjects.csv")
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("Is Public Domain", "").strip() == "True":
                yield {k: (r.get(k) or "") for k in COLS}


def seeds(raw_dir: str, limit: int | None = None):
    table = {r["Object ID"]: r for r in rows(raw_dir)}
    n = 0
    for oid in stable_order(table):
        seed = build(table[oid])
        if seed:
            yield seed
            n += 1
            if limit and n >= limit:
                return
