"""thought_seeds.textspec - the prompt-text parser the prompt and label sources share (parti, diffusiondb, wikidata).

spec_from_text(text) reads the records a text states: the closed lists of the trie (maps.py) found in the text, each with a context
guard where a word has a second sense ('studio lighting' is a light, not a setting; 'pastel colours' is not a pastel medium; 'wine
glasses' are not glasses); the thing is the first concrete noun of a fixed vocabulary (animals, vehicles, objects, buildings, food,
plants), with its count, bound colour and position when the text gives them; persons come from the gender / age / role words (a
person word directly before an animal noun is not a person: 'baby elephant'); clothing, hair, expression, pose and gesture only when a
person is present and the word sits near the person word; relations from the trie's relation phrases between two nouns of the
vocabulary. A record is set only when the words state it; nothing is guessed.

Beside it: domain_of (the picture's domain a text asks for), is_explicit, norm_digits (digits a source stores one by one),
strip_phrases (the 'in the style of <Name>' / 'by <Name>' phrases) and finish (the routed spec without an orphaned wear colour).

This module is not a source: build.available() treats every module under sources/ as one."""
from __future__ import annotations

import re

from . import core, maps

# ------------------------------------------------------------------ vocabulary of the parser
ANIMALS = """dog puppy cat kitten horse pony foal donkey mule cow bull ox calf sheep lamb goat pig piglet chicken hen rooster duck
duckling goose swan turkey bird owl eagle hawk falcon parrot penguin flamingo peacock pigeon dove crow raven sparrow robin hummingbird
seagull gull pelican toucan ostrich heron stork bat mouse rat rabbit bunny hare squirrel chipmunk hamster hedgehog fox wolf bear
polar_bear panda red_panda koala kangaroo wallaby sloth monkey ape gorilla chimpanzee orangutan lion lioness tiger leopard cheetah
jaguar panther lynx cougar elephant rhino rhinoceros hippo hippopotamus giraffe zebra camel llama alpaca deer stag moose elk reindeer
antelope gazelle bison buffalo yak boar raccoon skunk badger otter beaver seal sea_lion walrus whale dolphin shark fish goldfish
salmon octopus squid jellyfish crab lobster shrimp starfish snail turtle tortoise frog toad lizard gecko iguana chameleon snake cobra
crocodile alligator dinosaur dragon unicorn butterfly moth bee wasp ant spider beetle ladybug dragonfly grasshopper caterpillar
scorpion wombat pangolin armadillo meerkat lemur platypus ferret weasel porcupine hyena corgi poodle husky labrador retriever
bulldog chihuahua dachshund kangaroo griffin phoenix pegasus mermaid triceratops diplodocus tyrannosaurus""".split()
VEHICLES = """car truck pickup_truck van bus taxi train tram bicycle bike motorcycle motorbike scooter skateboard boat ship sailboat
yacht canoe kayak ferry submarine airplane plane aeroplane jet helicopter rocket spaceship space_shuttle hot_air_balloon tractor
cart wagon carriage ambulance fire_truck police_car limousine jeep sled sleigh bulldozer excavator steam_train locomotive""".split()
OBJECTS = """umbrella lantern lamp candle book cup mug teacup bottle vase bowl plate pot kettle teapot jar basket box suitcase backpack
chair armchair table bench sofa couch bed desk shelf bookshelf cabinet door window mirror clock phone cell_phone telephone smartphone
computer laptop keyboard television radio camera guitar violin piano drum trumpet flute harp cello saxophone microphone sword shield
spear axe hammer knife fork spoon scissors key ladder rope chain fence wall gate flag sign stop_sign traffic_light mailbox
fire_hydrant bucket barrel crate statue sculpture bust picture_frame toy teddy_bear doll robot ball soccer_ball basketball football
baseball kite hat cap crown helmet shoe sneaker boot coin trophy pillow blanket towel rug carpet curtain globe map envelope paintbrush
easel bell tent wheel anchor compass telescope microscope hourglass skull egg nest feather seashell pumpkin snowman sandcastle
castle tower house cabin hut barn windmill church pyramid skyscraper building fountain monument arch column well chimney fireplace
stove oven refrigerator fridge toaster sink bathtub toilet chandelier cage aquarium birdcage cauldron treasure_chest throne
billboard wheelbarrow shovel broom watering_can snow_globe dress suit jacket coat robe gown kimono uniform scarf necklace glasses
sunglasses gloves mask watch ring bracelet earrings backpack handbag purse headphones tie bowtie shirt t-shirt sweater hoodie
skateboard surfboard snowboard skis sculpture vending_machine water_tower lighthouse bridge temple tractor guitar paper_lantern
balloon pen notebook newspaper magazine letter calendar chess_board candle_holder teapot frying_pan grill bench_press""".split()
FOOD = """apple banana lemon lime pear grape strawberry cherry watermelon melon pineapple mango coconut avocado tomato potato carrot
onion broccoli cabbage lettuce corn eggplant cucumber mushroom bread loaf toast croissant sandwich burger hamburger hot_dog pizza pasta
noodles soup salad cake cupcake cookie pie donut doughnut muffin pancake waffle ice_cream chocolate candy cheese steak sushi taco
burrito coffee tea juice orange_juice beer milk cocktail smoothie honey popcorn pretzel bagel dumpling rice omelette""".split()
PLANTS = """tree palm_tree pine_tree oak_tree apple_tree christmas_tree flower rose tulip sunflower daisy lily orchid lotus cactus fern
bush shrub plant potted_plant vine bamboo bonsai maple_tree cherry_tree willow""".split()
PLACES = """mountain hill river lake sea ocean waterfall island volcano canyon valley field road street path city village town skyline
moon sun planet cloud rainbow tornado wave beach forest desert garden meadow""".split()
CREATURES = """mech mecha cyborg alien monster creature demon angel skeleton zombie vampire werewolf fairy elf goblin orc golem troll
gnome ogre kraken yeti centaur minotaur""".split()
MASK = re.compile(r"\b(pen and ink|pen-and-ink|pen & ink|matte painting|concept art|key art|splash art|fan art|line art|pixel art|"
                  r"album cover|book cover|movie poster|film still|movie still|lens flare|depth of field|ray tracing|light rays|"
                  r"god rays|star wars|tarot card|playing card|trading card|card game|master painter|photo realistic|"
                  r"path tracing|mental ray|subsurface scattering|dragon ball|"
                  r"photo-realistic|photo real|photo quality|photographic)\b")    # phrases whose nouns are not the picture's things
HEAD_AFTER = {"ears", "ear", "tail", "tails", "mask", "costume", "onesie", "skull", "horns", "horn", "wings", "scales", "fur",
              "feathers", "paw", "paws", "claws", "eyes", "blond", "blonde", "colored", "coloured", "color", "colour", "shaped",
              "flavored", "flavoured", "scented", "themed", "style", "styled", "like", "print", "pattern", "patterned", "skin",
              "head", "hybrid", "girl", "boy", "man", "woman", "warrior", "knight", "king", "queen", "god", "goddess", "lord", "rider",
              "pelt", "hide", "leather", "bone", "bones", "teeth", "tooth", "shell", "egg", "eggs", "mane", "hair", "face"}
PERSON_EXTRA = {"person": None, "people": None, "astronaut": None, "knight": None, "wizard": None, "witch": None, "pirate": None,
                "warrior": None, "king": "man", "queen": "woman", "prince": "man", "princess": "woman", "businessman": "man",
                "businesswoman": "woman", "policeman": "man", "policewoman": "woman", "fireman": "man", "firefighter": None,
                "cowboy": "man", "cowgirl": "woman", "grandma": "woman", "grandpa": "man", "grandmother": "woman",
                "grandfather": "man", "nun": "woman", "priest": "man", "doctor": None, "scientist": None, "teacher": None,
                "cricketer": None, "husband": "man", "wife": "woman", "actress": "woman", "actor": "man", "waitress": "woman",
                "waiter": "man", "mom": "woman", "mother": "woman", "dad": "man", "father": "man", "monk": "man", "bride": "woman",
                "groom": "man", "gentleman": "man", "lady": "woman", "ladies": "woman", "skier": None, "surfer": None,
                "goddess": "woman", "human": None, "someone": None, "humans": None}
ROLE_EXTRA = {"cricketer": "athlete"}
NUMBERS = {"one": 1, "single": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a pair of": 2, "twin": 2}
POSITIONS = [("on the left", "left"), ("to the left", "left"), ("on the right", "right"), ("to the right", "right"),
             ("in the center", "centre"), ("in the centre", "centre"), ("in the middle", "centre"), ("in the foreground", "foreground"),
             ("in the background", "background"), ("at the top", "top"), ("at the bottom", "bottom")]
EXPRESSION = {"smiling": "smile", "smile": "smile", "smiles": "smile", "laughing": "laughing", "laughs": "laughing",
              "crying": "crying", "cries": "crying", "in tears": "tears", "frowning": "frown", "frown": "frown", "grinning": "grin",
              "grin": "grin", "angry": "angry", "sad": "sad", "surprised": "surprised", "scared": "scared", "frightened": "scared",
              "serious": "serious", "winking": "wink", "sleepy": "sleepy", "eyes closed": "closed eyes", "closed eyes": "closed eyes",
              "pensive": "pensive", "happy": "happy", "screaming": "open mouth", "shouting": "open mouth", "pouting": "pout",
              "smirking": "smirk", "smirk": "smirk", "blushing": "blush"}
HAIR = [(r"\b(?:long|waist[- ]length|shoulder[- ]length)\s+(?:\w+\s+)?hair\b", "long"), (r"\bshort\s+(?:\w+\s+)?hair\b", "short"),
        (r"\bcurly\s+(?:\w+\s+)?hair\b", "curly"), (r"\bwavy\s+(?:\w+\s+)?hair\b", "wavy"), (r"\bstraight\s+(?:\w+\s+)?hair\b", "straight"),
        (r"\bmessy\s+(?:\w+\s+)?hair\b", "messy"), (r"\bwet\s+(?:\w+\s+)?hair\b", "wet"), (r"\bbraid(?:s|ed)?\b", "braided"),
        (r"\bponytail\b", "ponytail"), (r"\bpigtails\b", "pigtails"), (r"\b(?:hair\s+bun|in\s+a\s+bun)\b", "bun"), (r"\bbangs\b", "bangs"),
        (r"\bafro\b", "afro"), (r"\b(?:dreadlocks|locs)\b", "locs"), (r"\bbuzz\s*cut\b", "buzzed"), (r"\bshaved\s+head\b", "shaved"),
        (r"\bbob\s+(?:cut|haircut)\b", "bob"), (r"\bslicked[- ]back\s+hair\b", "slicked"), (r"\bundercut\b", "undercut"),
        (r"\bwindblown\s+hair\b", "windblown")]
EXPLICIT = re.compile(r"\b(nsfw|nude|nudes|naked|nudity|topless|bottomless|sex|sexy|sexual|porn|porno|pornographic|hentai|erotic|"
                      r"erotica|xxx|boobs?|breasts?|nipples?|genitals?|genitalia|penis|vagina|vulva|cum|orgasm|fetish|bdsm|lingerie|"
                      r"undressed|undressing|stripper|seductive|lewd|ecchi|playboy|onlyfans|busty|cleavage|thong|panties|bra|"
                      r"sensual|horny|intercourse|masturbat\w*|orgy|bondage|dominatrix|milf|nipple|buttocks|ass|butt)\b")
STOP_LOOKBACK = {"of", "with", "on", "in", "at", "to", "and", "or", "is", "are", "was", "has", "have", "by", "from", "for", "the",
                 "his", "her", "its", "their", "under", "over", "behind", "near", "beside", "next", "into", "onto", "while", "as"}
COLOUR_WORDS = {k: v for k, v in maps.COLOUR.items() if v not in maps.HAIR_COLOUR_ONLY}
NOUN_COLOURS = {"wine", "rust", "sand", "slate", "mint", "plum", "peach", "olive", "coral", "cream", "ivory", "charcoal", "amber",
                "tan", "lilac", "indigo", "mustard"}           # also things: wine bottles, olive oil, mint leaves, sand castle
NEGATION = {"no", "without", "not", "nor", "zero", "none", "never", "isn't", "aren't", "doesn't", "don't", "lacking"}
NOT_A_MAN = {"iron", "spider", "bat", "pac", "gingerbread", "snow", "tin", "lego", "straw", "stick", "sand", "super", "ant",
             "toy", "paper", "wicker", "clay", "cookie"}
LOCAL_RELATION = dict(maps.RELATION)
LOCAL_RELATION.pop("by", None)                              # 'by' has too many senses in prompts (lit by, made by, by the sea)
LOCAL_RELATION.pop("over", None)                            # 'rolling over a field', 'flying over a city': motion, not 'above'
LOCAL_RELATION["on top of"] = "above"


def _forms(word: str) -> list:
    w = word.replace("_", " ")
    head, _, last = w.rpartition(" ")
    irregular = {"mouse": "mice", "goose": "geese", "ox": "oxen", "sheep": "sheep", "deer": "deer", "fish": "fish", "moose": "moose",
                 "bison": "bison", "buffalo": "buffaloes", "knife": "knives", "wolf": "wolves", "leaf": "leaves", "calf": "calves",
                 "loaf": "loaves", "shelf": "shelves", "person": "people", "cactus": "cacti", "octopus": "octopuses",
                 "glasses": "glasses", "sunglasses": "sunglasses", "gloves": "gloves", "earrings": "earrings",
                 "headphones": "headphones", "noodles": "noodles", "skis": "skis", "jeans": "jeans", "series": "series",
                 "dice": "dice", "corn": "corn", "rice": "rice", "milk": "milk", "honey": "honey", "popcorn": "popcorn",
                 "candy": "candies", "pony": "ponies", "puppy": "puppies", "bunny": "bunnies", "butterfly": "butterflies",
                 "dragonfly": "dragonflies", "strawberry": "strawberries", "cherry": "cherries", "ladybug": "ladybugs"}
    if last in irregular:
        p = irregular[last]
    elif re.search(r"(s|x|z|ch|sh)$", last):
        p = last + "es"
    elif re.search(r"[^aeiou]y$", last):
        p = last[:-1] + "ies"
    elif last.endswith("o") and last in ("tomato", "potato", "volcano", "hippo", "mango"):
        p = last + "es"
    else:
        p = last + "s"
    plural = (head + " " + p).strip()
    out = [(w, False)]
    if plural != w:
        out.append((plural, True))
    if "-" in w:
        out.append((w.replace("-", " "), False))
    return out


NOUNS = {}                                                    # surface form -> (singular, plural?, kind)
for kind, words in (("animal", ANIMALS), ("vehicle", VEHICLES), ("object", OBJECTS), ("food", FOOD), ("plant", PLANTS),
                    ("creature", CREATURES), ("place", PLACES)):
    for wd in words:
        for form, pl in _forms(wd):
            NOUNS.setdefault(form, (wd.replace("_", " "), pl, kind))
PERSON_WORDS = {}                                             # surface form -> (gender, age, role)
for src in (maps.GENDER, maps.AGE, maps.ROLE, PERSON_EXTRA):
    for w in src:
        if w in ("player", "pitcher", "batter", "cook", "seller"):
            continue
        if src is not PERSON_EXTRA and src[w] is None:
            continue                                          # a blocking phrase of the shared maps ('dvd player'): no person
        g = maps.GENDER.get(w) or PERSON_EXTRA.get(w) or maps.first(w, maps.GENDER)
        if g is None and w in ("little boy", "young boy"):
            g = "boy"
        if g is None and w in ("little girl", "young girl"):
            g = "girl"
        PERSON_WORDS[w] = (g, maps.AGE.get(w), maps.ROLE.get(w) or ROLE_EXTRA.get(w))
for w in ("guy", "guys", "lady", "ladies"):
    PERSON_WORDS.setdefault(w, (maps.GENDER.get(w, "woman" if "lad" in w else "man"), None, None))
WEAR_WORDS = set(maps.CLOTHING) | set(maps.ACCESSORY) | {"sunglasses", "glasses", "hat", "cap", "crown", "helmet", "mask", "scarf",
                                                         "necklace", "watch", "ring", "bracelet", "earrings", "gloves", "tie",
                                                         "bowtie", "shirt", "t-shirt", "sweater", "hoodie", "dress", "suit",
                                                         "jacket", "coat", "robe", "gown", "kimono", "uniform", "handbag", "purse",
                                                         "backpack", "headphones", "shoe", "sneaker", "boot"}


def _tokens(clause: str) -> list:
    return re.findall(r"[a-z0-9]+(?:['\-][a-z0-9]+)*", clause)


def _mentions(toks: list) -> list:
    """Noun and person mentions in a clause: (start, end, word, plural, kind, person tuple or None), longest match first."""
    out, i = [], 0
    while i < len(toks):
        hit = None
        for n in (3, 2, 1):
            if i + n > len(toks):
                continue
            form = " ".join(toks[i:i + n])
            if form in PERSON_WORDS:
                nxt = toks[i + n] if i + n < len(toks) else ""
                nxt2 = " ".join(toks[i + n:i + n + 2])
                if (NOUNS.get(nxt, (0, 0, ""))[2] not in ("", "place") or NOUNS.get(nxt2, (0, 0, ""))[2] == "animal"
                        or (nxt in HEAD_AFTER and nxt not in PERSON_WORDS)   # 'cowboy hats', 'baby bottle': a modifier
                                                                             # ('woman warrior' keeps the woman)
                        or (form in ("man", "men") and i > 0 and toks[i - 1] in NOT_A_MAN)
                        or nxt in ("made", "nature", "earth") or (form == "nurse" and nxt == "shark")
                        or (form == "monk" and nxt == "seal")):
                    continue
                hit = (i, i + n, form, form.endswith("s") and form not in ("boss",), "person", PERSON_WORDS[form])
                break
            if form in NOUNS:
                w, pl, kind = NOUNS[form]
                nxt = toks[i + n] if i + n < len(toks) else ""
                if nxt in HEAD_AFTER or (nxt in NOUNS and NOUNS[nxt][2] != "place") or nxt in PERSON_WORDS:
                    hit = (i, i + n, None, False, "modifier", None)       # 'dog house', 'cat ears', 'strawberry blonde'
                    break
                hit = (i, i + n, w, pl, kind, None)
                break
        if hit:
            if hit[4] != "modifier" and not NEGATION & set(toks[max(0, i - 3):i]):   # 'without any boats': not in the picture
                out.append(hit)
            i = hit[1]
        else:
            i += 1
    return out


def _lookback(toks: list, start: int) -> tuple:
    """(count, colour) from the words just before a mention: a number or an article, and a colour adjective."""
    count = colour = None
    j = start - 1
    steps = 0
    while j >= 0 and steps < 4:
        w = toks[j]
        two = " ".join(toks[j - 1:j + 1]) if j >= 1 else ""
        if w in NOUN_COLOURS and toks[j + 1:j + 2] not in (["colored"], ["coloured"], ["color"], ["colour"]):
            j -= 1                                        # 'wine bottles': a kind of bottle, not a colour
            steps += 1
            continue
        if two in COLOUR_WORDS and colour is None:
            colour = COLOUR_WORDS[two]
            j -= 2
            steps += 2
            continue
        if w in COLOUR_WORDS and colour is None:
            colour = COLOUR_WORDS[w]
        elif w in NUMBERS:
            count = NUMBERS[w]
            break
        elif w.isdigit() and 0 < int(w) < 100:
            count = int(w)
            break
        elif w in STOP_LOOKBACK or w in NOUNS or w in PERSON_WORDS:
            break
        j -= 1
        steps += 1
    return count, colour


_PATTERNS: dict = {}
_COLOUR_ALT = "|".join(re.escape(c) for c in sorted(COLOUR_WORDS, key=len, reverse=True))
EYES_RE = re.compile(r"\b(" + _COLOUR_ALT + r")\s+eyes\b")
_WEAR_COLOUR: dict = {}
WEATHER_X = {**maps.WEATHER, "snowstorm": "snow", "blizzard": "snow", "snowfall": "snow", "rainstorm": "rain"}


def _hits(text: str, mapping: dict) -> list:
    """(start, end, phrase, value) of every phrase of a module-level mapping in the text, longest first, bounded as maps.find
    bounds them; a blocking phrase of the shared maps comes back with the value None."""
    if not text:
        return []
    pat = _PATTERNS.get(id(mapping))
    if pat is None:
        pat = _PATTERNS[id(mapping)] = maps.pattern(mapping)
    return [(m.start(), m.end(), m.group(1), mapping[m.group(1)]) for m in pat.finditer(text)]


def _wear_colour_re(target: str):
    if target not in _WEAR_COLOUR:
        phrases = [p for p, v in {**maps.CLOTHING, **maps.ACCESSORY}.items() if v == target]
        _WEAR_COLOUR[target] = re.compile(r"\b(" + _COLOUR_ALT + r")\s+(?:[a-z\-]+\s+)?(?:"
                                          + "|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + r")\b")
    return _WEAR_COLOUR[target]


def _after(t: str, end: int, n: int = 30) -> str:
    return t[end:end + n].lstrip()


def _before(t: str, start: int, n: int = 30) -> str:
    return t[max(0, start - n):start].rstrip()


def _guarded(t: str, mapping: dict, guard) -> str | None:
    """The first value of the mapping in the text whose guard accepts its context; a blocking phrase is passed over."""
    for s, e, phrase, value in _hits(t, mapping):
        if value is not None and guard(phrase, value, _before(t, s), _after(t, e)):
            return value
    return None


def _g_medium(phrase, value, before, after):
    if value in ("bronze", "marble", "clay"):
        return False                                          # the material of a depicted object, not the picture's medium
    if value == "ink":
        return bool(re.match(r"(and wash|wash|drawing|painting|sketch|illustration|art|on paper)\b", after)) or \
            bool(re.search(r"\b(pen and|pen-and|india|chinese|in)$", before)) or phrase != "ink"
    if value == "charcoal":
        return bool(re.match(r"(drawing|sketch|painting|on paper|art|illustration|study)\b", after)) or before.endswith(" in")
    if value == "pencil":
        return bool(re.match(r"(drawing|sketch|art|illustration|on paper|study)\b", after)) or \
            bool(re.search(r"\b(in|colou?red)$", before))
    if value == "pastel":
        return bool(re.match(r"(drawing|painting|on paper|art|chalk|sketch)\b", after)) or bool(re.search(r"\b(oil|soft|in)$", before))
    if value == "acrylic":
        return bool(re.match(r"(paint|painting|on canvas|on paper)\b", after)) or phrase != "acrylic"
    if value in ("mosaic", "tapestry"):
        return bool(re.match(r"(of|art|style|tiles?|work)\b", after)) or bool(re.search(r"\b(a|in)$", before))
    if value == "photograph" and (re.match(r"(frame|album|-?realis|real\b|quality|bash)", after) or phrase == "photographic"):
        return False                                          # 'photo realistic' asks for a look, not a photograph
    return True


def _g_style(phrase, value, before, after):
    building = r"(cathedral|church|castle|building|buildings|architecture|arch|windows?|house|mansion|tower|palace|room|interior|" \
               r"facade|city|dress|furniture|chair|font|lettering)\b"
    if re.search(r"\bpost-?$", before) or before.endswith("post") or before.endswith("neo"):
        return False
    if value == "abstract":
        return bool(re.match(r"(?:[a-z]+\s+)?(art|painting|style|expressionism|cubism|illustration|composition|sculpture)\b", after))
    if value in ("gothic", "baroque", "rococo", "brutalism", "bauhaus", "renaissance", "art deco", "art nouveau"):
        if re.match(building, after) or re.match(r"(fair|festival|man)\b", after):
            return False
        return True
    if value == "naive":
        return bool(re.match(r"(art|style|painting)\b", after))
    if value == "street art" and phrase == "graffiti":
        return bool(re.match(r"(art|style|mural)\b", after)) or bool(re.search(r"\bas$", before))
    if value == "comic":
        return not re.match(r"(relief|sans)\b", after)
    return True


def _g_light(phrase, value, before, after):
    if value == "neon" and re.match(r"(green|pink|blue|yellow|orange|purple|red|colou?rs?|sign|signs)\b", after):
        return False
    if value == "fluorescent" and re.match(r"(green|pink|blue|yellow|orange|colou?rs?|paint)\b", after):
        return False
    return True


def _g_angle(phrase, value, before, after):
    if value == "profile" and (re.match(r"(picture|pic|photo|image)\b", after) or not re.search(r"\b(side|in|from the)$", before)):
        return False
    if value == "overhead" and re.match(r"(light|lights|lighting|lamp)\b", after):
        return False
    return True


def _g_lens(phrase, value, before, after):
    if re.match(r"(film|photo|photograph|photography|camera|film camera|negative|slide)\b", after):
        return False
    if value == "35mm" and not re.match(r"lens\b", after):
        return False
    return True


def _g_time(phrase, value, before, after):
    if re.match(r"(blue|glory|gown|dress|tea|snack|star|sky blue)\b", after):
        return False
    return True


def _g_weather(phrase, value, before, after):
    if phrase in ("snow", "snowy") and re.match(r"(white|globe|leopard|cone|owl|man|men|boots|shoes)\b", after):
        return False
    if phrase.startswith("rain") and re.match(r"(boots|coat|forest|drop|drops|bow)\b", after):
        return False
    if phrase.startswith("storm") and re.match(r"(trooper|troopers|drain)\b", after):
        return False
    if phrase == "frost" and re.match(r"(giant|giants)\b", after):
        return False
    return True


def _g_setting(phrase, value, before, after):
    if value == "studio" and re.match(r"(ghibli|light|lights|lighting|quality|apartment)\b", after):
        return False
    if phrase == "lab" and re.match(r"(coat|coats|rat|rats|grown)\b", after):
        return False
    if value == "beach" and re.match(r"(ball|towel|chair|umbrella|bag)\b", after):
        return False
    if value == "garden" and re.match(r"(gnome|hose|tools?|party)\b", after):
        return False
    if value == "forest" and re.match(r"green\b", after):
        return False
    if value == "kitchen" and re.match(r"(knife|knives|utensils?|towel|timer)\b", after):
        return False
    if value == "market street" and re.search(r"\b(stock|black|super)$", before):
        return False
    if value == "alley" and before.endswith("bowling"):
        return False
    if value == "bridge" and re.match(r"of\b", after):
        return False
    return True


def _g_role(phrase, value, before, after):
    if phrase == "runner" and before.endswith("blade"):
        return False
    if phrase == "guard" and (re.match(r"(dog|rail|rails)\b", after) or re.search(r"\b(shin|mud)$", before)):
        return False
    if phrase == "reader" and re.search(r"\b(card|mind|e)$", before):
        return False
    if phrase == "nurse" and re.match(r"shark\b", after):
        return False
    if phrase == "monk" and re.match(r"seal\b", after):
        return False
    if phrase in ("mother", "father") and re.match(r"(nature|earth|ship|board)\b", after):
        return False
    if phrase in ("pitcher", "batter", "player", "cook", "seller"):
        return False
    return True


def _g_clothing(phrase, value, before, after):
    if phrase == "suit" and (re.match(r"of\b", after) or re.search(r"\b(space|diving|bathing|wet|hazmat|mech|power)$", before)):
        return False
    if phrase in ("coat", "overcoat") and re.match(r"of\b", after):
        return False
    if phrase == "dress" and re.match(r"(shirt|shoes|code|up)\b", after):
        return False
    return True


def _g_accessory(phrase, value, before, after):
    if value == "glasses" and (re.search(r"\b(wine|drinking|champagne|beer|two|of|shot|martini)$", before) or
                               re.match(r"of\b", after)):
        return False
    if value == "cap" and re.search(r"\b(ice|bottle|polar|knee|snow)$", before):
        return False
    if phrase == "watch":
        return bool(re.search(r"\b(wrist|pocket|gold|silver|smart|a)$", before))
    if value == "ring":
        return bool(re.search(r"\b(wedding|engagement|diamond|gold|silver|a)$", before)) and not re.match(r"(of|light)\b", after)
    if value == "bag" and phrase == "bag":
        return False
    if value == "pin":
        return False
    if value == "cane" and re.search(r"\b(candy|sugar)$", before):
        return False
    if value == "belt" and re.search(r"\b(asteroid|conveyor|seat|black|tool)$", before):
        return False
    return True


def _near(mentions_by_clause, clause_idx: int, pos: int, window: int = 5) -> bool:
    """A word near a person word: in its clause within the window, or opening the next clause ('an old man in a coat, sitting')."""
    if any(k == "person" and (s - 2 <= pos <= e + window) for s, e, w, pl, k, p in mentions_by_clause.get(clause_idx, [])):
        return True
    return pos <= 1 and any(k == "person" for s, e, w, pl, k, p in mentions_by_clause.get(clause_idx - 1, []))


def spec_from_text(text: str, spec: core.Spec | None = None) -> tuple:
    """-> (Spec, info): the records the text states. info: persons (bool), thing (str|None), animal (bool), nouns (list)."""
    s = spec or core.Spec()
    t = norm_digits(core.ascii_text(text).lower())
    clauses = [c for c in re.split(r"[.;:!?\n()\[\]{}\"|]+|,", MASK.sub(" , ", t)) if c.strip()]
    toks_by = {i: _tokens(c) for i, c in enumerate(clauses)}
    ment_by = {i: _mentions(toks) for i, toks in toks_by.items()}
    persons = [(i, m) for i, ms in ment_by.items() for m in ms if m[4] == "person"]
    nouns = [(i, m) for i, ms in ment_by.items() for m in ms if m[4] != "person"]
    info = {"persons": bool(persons), "thing": None, "animal": False, "nouns": [m[2] for _, m in nouns]}
    # persons
    if persons:
        counts, genders, ages, roles = [], [], [], []
        for i, m in persons:
            g, a, r = m[5]
            c, _ = _lookback(toks_by[i], m[0])
            if m[2] in ("people", "children", "kids", "men", "women", "boys", "girls", "guys", "ladies", "students", "soldiers",
                        "dancers", "musicians", "workers", "farmers", "monks", "tourists", "travelers", "athletes", "riders"):
                c = c if c and c > 1 else None
            counts.append(c)
            genders.append(g)
            ages.append(a)
            roles.append(r if r and _g_role(m[2], r, " ".join(toks_by[i][max(0, m[0] - 2):m[0]]),
                                           " ".join(toks_by[i][m[1]:m[1] + 2])) else None)
        if all(counts):
            s.set("person", "count", str(sum(counts)))
        g = next((x for x in genders if x), None)
        if g:
            s.set("person", "gender", g)
        a = next((x for x in ages if x), None)
        if a:
            s.set("person", "age", a)
        r = next((x for x in roles if x), None)
        if r:
            s.set("person", "role", r)
        # look, wear, body: near a person word
        for pat, v in HAIR:
            if re.search(pat, t):
                s.set("look", "hair", v)
                break
        m = EYES_RE.search(t)
        if m:
            s.set("look", "eyes", COLOUR_WORDS[m.group(1)])
        for i, toks in toks_by.items():
            for j in range(len(toks)):
                for n in (2, 1):
                    w = " ".join(toks[j:j + n])
                    if w in EXPRESSION and _near(ment_by, i, j) and not s.has("look", "expression"):
                        s.set("look", "expression", EXPRESSION[w])
                    if w in maps.POSE and _near(ment_by, i, j, 6) and not s.has("body", "pose"):
                        if not (w == "running" and toks[j + 1:j + 2] == ["water"]):
                            s.set("body", "pose", maps.POSE[w])
                    if w in maps.GESTURE and _near(ment_by, i, j, 6) and not s.has("body", "gesture"):
                        s.set("body", "gesture", maps.GESTURE[w])
        cl = _guarded(t, maps.CLOTHING, _g_clothing)
        if re.search(r"\bsuit of (armou?r)\b", t):
            cl = "armour"
        if cl:
            s.set("wear", "clothing", cl)
        acc = _guarded(t, maps.ACCESSORY, _g_accessory)
        if acc:
            s.set("wear", "accessory", acc)
        for target in (cl, acc):
            if not target:
                continue
            m = _wear_colour_re(target).search(t)
            if m and m.group(1) not in NOUN_COLOURS and s.set("wear", "colour", COLOUR_WORDS[m.group(1)]):
                break
    # the thing: the first concrete noun (worn things only when nobody wears them), places last
    skip = WEAR_WORDS if persons else set()
    cands = [(i, m) for i, m in nouns if m[2] not in skip]
    cands = [x for x in cands if x[1][4] != "place"] + [x for x in cands if x[1][4] == "place"]
    for i, m in cands:
        setting_word = maps.first(m[2], maps.SETTING)
        if setting_word and m[4] == "place":
            continue
        if s.set("thing", "name", m[2]):
            info["thing"], info["animal"] = m[2], m[4] == "animal"
            c, col = _lookback(toks_by[i], m[0])
            if c and not (m[3] and c == 1):
                s.set("thing", "count", str(c))
            if col:
                s.set("thing", "colour", col)
            rest = " ".join(toks_by[i][m[1]:m[1] + 8])
            for phrase, pos in POSITIONS:
                if re.match(r"(?:\w+\s+){0,3}" + re.escape(phrase) + r"\b(?!\s+of\b)", rest):   # 'to the left of X' is a relation
                    s.set("thing", "position", pos)
                    break
            break
    # relations between two mentions of a clause
    for i, toks in toks_by.items():
        ms = ment_by[i]
        clause = " ".join(toks)
        for st, en, phrase, rel in _hits(clause, LOCAL_RELATION):
            if phrase == "over" and re.match(r"(the shoulder|and)\b", clause[en:].lstrip()):
                continue
            ws, we = len(clause[:st].split()), len(clause[:en].split())
            a = [m for m in ms if m[1] <= ws and ws - m[1] <= 4]
            b = [m for m in ms if m[0] >= we and m[0] - we <= 3]
            if not a or not b:
                continue
            a, b = a[-1], b[0]
            if rel in ("holding", "looking at", "facing") and a[4] not in ("person", "animal"):
                continue
            wa = (a[5][0] or a[2].rstrip("s")) if a[4] == "person" else a[2]
            wb = (b[5][0] or b[2]) if b[4] == "person" else b[2]
            s.relate(wa, rel, wb)
            if len(s.rels) >= 3:
                break
    # the scene, the shot, the form
    v = _guarded(t, maps.SETTING, _g_setting)
    if v:
        s.set("scene", "setting", v)
    v = _guarded(t, maps.TIME, _g_time)
    if v:
        s.set("scene", "time", v)
    v = _guarded(t, WEATHER_X, _g_weather)
    if v:
        s.set("scene", "weather", v)
    if re.search(r"\b(a crowd|crowds|crowded with people|a throng)\b", t):
        s.set("scene", "layout", "crowd")
    v = _guarded(t, maps.LIGHT, _g_light)
    if v:
        s.set("shot", "light", v)
    v = _guarded(t, maps.ANGLE, _g_angle)
    if v:
        s.set("shot", "angle", v)
    v = maps.first(t, maps.FRAMING)
    if v:
        s.set("shot", "framing", v)
    v = _guarded(t, maps.LENS, _g_lens)
    if v:
        s.set("shot", "lens", v)
    v = maps.first(t, maps.FOCUS)
    if v:
        s.set("shot", "focus", v)
    v = _guarded(t, maps.MEDIUM, _g_medium)
    if v:
        s.set("form", "medium", v)
    v = _guarded(t, maps.STYLE, _g_style)
    if v:
        s.set("form", "style", v)
    v = period_of_text(t)
    if v:
        s.set("form", "period", v)
    tex = None
    if re.search(r"\b(film grain|grainy)\b", t):
        tex = "grainy"
    elif re.search(r"\b(impasto|visible brush ?strokes|thick brush ?strokes|brushy)\b", t):
        tex = "brushy"
    if tex:
        s.set("form", "texture", tex)
    v = maps.first(t.replace("high-contrast", "high contrast").replace("low-contrast", "low contrast"), maps.CONTRAST)
    if v:
        s.set("form", "contrast", v)
    return s, info


def norm_digits(t: str) -> str:
    """Spaced digits joined back ('1 9 2 0 s' -> '1920s', '3 5 mm' -> '35mm', '8 k' -> '8k', '3 d' -> '3d'), as some prompt
    sources store numbers digit by digit."""
    t = re.sub(r"(?<![\d.])((?:\d ){1,5}\d)(?![\d.])", lambda m: m.group(1).replace(" ", ""), t)
    t = re.sub(r"\b(\d+) (s|mm|k|d)\b", r"\1\2", t)
    return t


def period_of_text(t: str) -> str | None:
    for pat, v in ((r"\bfuturistic\b", "futuristic"), (r"\b(victorian|19th century|nineteenth century)\b", "19th century"),
                   (r"\bmedieval\b", "medieval"), (r"\bancient\b", "ancient"), (r"\b(1980s|80s|eighties)\b", "1980s"),
                   (r"\b(1990s|90s|nineties)\b", "1990s"), (r"\b(1950s|1960s|50s|60s|mid-century|mid century)\b", "mid century"),
                   (r"\b(1920s|1930s|1910s|1900s|20s|30s)\b", "early 20th")):
        if re.search(pat, t):
            if v in ("mid century", "early 20th") and re.search(r"\b(in (his|her|their) (20s|30s|50s|60s)|aged)\b", t):
                continue
            return v
    return None


PAINT = re.compile(r"\b(oil painting|oil on canvas|watercolou?r|gouache|acrylic painting|acrylic on canvas|tempera|fresco|"
                   r"(?:a|an|the|oil|acrylic|ink|impressionist|expressionist|abstract|chinese|japanese|anime|surrealist|famous|"
                   r"renaissance|baroque|cubist|realist|landscape|portrait)\s+painting|painting (?:of|in|by)|^painting\b|"
                   r"\bpainting\s*$|paintings? of)\b")


def domain_of(t: str) -> str:
    """photograph when the text asks for a photo; painting for paint media; design for logos, icons and product renders;
    illustration otherwise."""
    t = t.lower()
    if re.search(r"\b(logo|logos|icon|icons|emblem|app icon|sticker design|t-shirt design|product render|product design|"
                 r"packaging design|wordmark|monogram|infographic)\b", t):
        return "design"
    t = MASK.sub(" ", norm_digits(t))                       # 'photo realistic', 'photographic' ask for a look, not a photograph
    if re.search(r"\b(photo|photos|photograph|photographs|photography|dslr|polaroid|snapshot|selfie|film still|"
                 r"35mm film|kodak|portra|fujifilm|canon eos|nikon|leica|hasselblad)\b", t):
        return "photograph"
    if PAINT.search(t):
        return "painting"
    return "illustration"


def is_explicit(t: str) -> bool:
    return bool(EXPLICIT.search(t.lower()))


# ------------------------------------------------------------------ name phrases
NAME_PHRASE = re.compile(r"\b(in the style of|in the manner of|style of|by|after|inspired by)\s+((?:the\s+)?"
                         r"(?:(?:[A-Z]\.\s*)+|[A-Z][\w'\-]*)(?:\s*(?:(?:[A-Z]\.\s*)+|[A-Z][\w'\-]*))*)")
# capitalized words that are not names in a prompt (peoples, periods, media, planets, holidays, a few words written in title case,
# a camera type written in capitals)
ALLOW = {"Egyptian", "Chinese", "Japanese", "French", "Greek", "Roman", "Persian", "Athenian", "Scottish", "Hawaiian", "Italian",
         "Indian", "African", "American", "European", "Victorian", "Renaissance", "Baroque", "Gothic", "Impressionist", "Oil",
         "Watercolor", "Woodcut", "Photograph", "Christmas", "Easter", "Earth", "Mars", "Jupiter", "Moon", "Triceratops",
         "Diplodocus", "Tyrannosaurus", "Rex", "Stegasaurus", "Styracosaurus", "Wide", "Portrait", "Painting", "Drawing",
         "Photo", "Sketch", "Cartoon", "Anime", "Marble", "Meadow", "Koala", "Night", "Rocks", "High", "With", "Downtown", "DSLR"}


def strip_phrases(text: str, allow: set | None = None) -> str:
    """The text without its name phrases ('in the style of <Name>', 'by <Name>'), each replaced by a space; a phrase whose capital
    words are all in `allow` (Egyptian, Chinese) stays."""
    ok = ALLOW | (allow or set())

    def rep(m):
        words = [re.sub(r"'s$", "", w) for w in re.findall(r"[A-Z][\w'\-]*", m.group(2))]
        return m.group(0) if words and all(w in ok for w in words) else " "
    t = NAME_PHRASE.sub(rep, core.ascii_text(text))
    t = re.sub(r"\s{2,}", " ", t)
    return re.sub(r"\s+([.,;:!?])", r"\1", t).strip()


# ------------------------------------------------------------------ the routed spec
def finish(dataset: str, sid: str, s: core.Spec) -> dict:
    """The spec as make_seed will route it, without a wear colour whose garment was a sealed value and was stripped (the colour
    of a text's garment says nothing once the garment is gone). A held seed stays whole. (A thing whose sealed name is stripped
    goes whole in core.strip_sealed.)"""
    raw = s.spec()
    out, held = core.route(f"{dataset}:{sid}", raw)
    if held:
        return raw
    if "wear" in out and not ({"clothing", "accessory"} & set(out["wear"])):
        out["wear"].pop("colour", None)
        if not out["wear"]:
            del out["wear"]
    return out
