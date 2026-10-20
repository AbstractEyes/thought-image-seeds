"""thought_seeds.textspec - the prompt-text parser the prompt and label sources share (parti, diffusiondb, wikidata).

spec_from_text(text) reads the records a text states: the closed lists of the trie (maps.py) found in the text, each with a context
guard where a word has a second sense ('studio lighting' is a light, not a setting; 'pastel colours' is not a pastel medium; 'wine
glasses' are not glasses; 'a jungle gym' is no forest), never when negated ('no rain') and never for a picture shown inside the
scene ('a wall with a framed oil painting', 'a television that displays an image of a city at night', 'two paintings on the wall.
The one on the left a detailed oil painting of ...'); the thing is the first
concrete noun of a fixed vocabulary (animals, vehicles, objects, buildings, food, plants), with its count, bound colour and position
when the text gives them (a number counts the noun it stands before: never an age, a measure or a title's number, '25 year old
man', 'six meters tall', 'metin 2'); persons come from the gender / age / role / kin words, and a person word that names no person
of the picture is passed over (a modifier, 'baby elephant'; a chess piece; an animal's title or guise, 'raccoon king', 'frog
knight'; a guise after 'as', 'a corgi as a knight'; what a thing is shaped like or a statue shows; the maker of the picture, 'a
drawing by a child'); words side by side describe one person ('an elderly woman', 'a female knight'), and a gender or a role is
kept only when it holds for every person the text names ('a girl and a boy' has none); clothing, hair, expression, pose and gesture only
when a person is present and the word sits near the person word; relations from the trie's relation phrases between a phrase's own
subject and the noun right after the relation word, never a negated one ('facing away from'). Titles of paintings, books, films and
games ('American Gothic', 'Animal Farm', 'Elden Ring') give nothing. A record is set only when the words state it; nothing is guessed.

Beside it: domain_of (the picture's domain a text asks for; a photo or a painting shown in the scene asks for none), is_explicit,
norm_digits (digits a source stores one by one), strip_phrases (the 'in the style of <Name>' / 'by <Name>' phrases) and finish
(the routed spec without an orphaned wear colour).

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
MASK = re.compile(r"\b(pen and ink|pen-and-ink|pen & ink|matte painting|concept art|key art|key visual|splash art|fan art|line art|pixel art|"
                  r"album cover|book cover|movie poster|film still|movie still|lens flare|depth of field|ray tracing|light rays|"
                  r"god rays|star wars|tarot card|playing card|trading card|card game|master painter|photo realistic|"
                  r"path tracing|mental ray|subsurface scattering|dragon ball|"
                  r"comic book (?:style|art|artwork|illustration|panel|cover|page|character|drawing)s?|"
                  r"magazine cover|cover of (?:an? |the )?(?:[a-z\-]+ ){0,3}magazine|vogue magazine|time magazine|"
                  r"substance (?:3d )?(?:painter|designer)|corel painter|cinema 4d|3ds max|"     # software, not a person or a thing
                  r"american gothic|mona lisa|starry night|the last supper|the night watch|persistence of memory|"
                  r"birth of venus|girl with a pearl earring|the great wave|the son of man|garden of earthly delights|"
                  r"creation of adam|school of athens|"                                        # titles of paintings
                  r"photo-realistic|photo real|photo quality|photographic)\b")    # phrases whose nouns are not the picture's things
HEAD_AFTER = {"ears", "ear", "tail", "tails", "mask", "costume", "onesie", "skull", "horns", "horn", "wings", "scales", "fur",
              "feathers", "paw", "paws", "claws", "eyes", "blond", "blonde", "colored", "coloured", "color", "colour", "shaped",
              "flavored", "flavoured", "scented", "themed", "style", "styled", "like", "print", "pattern", "patterned", "skin",
              "head", "hybrid", "girl", "boy", "man", "woman", "warrior", "knight", "king", "queen", "god", "goddess", "lord", "rider",
              "pelt", "hide", "leather", "bone", "bones", "teeth", "tooth", "shell", "egg", "eggs", "mane", "hair", "face", "pose",
              "poses", "position"}
PERSON_EXTRA = {"person": None, "people": None, "astronaut": None, "knight": None, "wizard": None, "witch": None, "pirate": None,
                "warrior": None, "king": "man", "queen": "woman", "prince": "man", "princess": "woman", "businessman": "man",
                "businesswoman": "woman", "policeman": "man", "policewoman": "woman", "fireman": "man", "firefighter": None,
                "cowboy": "man", "cowgirl": "woman", "grandma": "woman", "grandpa": "man", "grandmother": "woman",
                "grandfather": "man", "nun": "woman", "priest": "man", "doctor": None, "scientist": None, "teacher": None,
                "cricketer": None, "husband": "man", "wife": "woman", "actress": "woman", "actor": "man", "waitress": "woman",
                "waiter": "man", "mom": "woman", "mother": "woman", "dad": "man", "father": "man", "monk": "man", "bride": "woman",
                "groom": "man", "gentleman": "man", "lady": "woman", "ladies": "woman", "skier": None, "surfer": None,
                "goddess": "woman", "human": None, "someone": None, "humans": None,
                # kin words: each names a person, so a count covers every person a text names ('a father and a son' is two); a
                # son or a daughter may be a child or an adult, so no gender word is read from them
                "son": None, "sons": None, "daughter": None, "daughters": None, "grandson": None, "grandsons": None,
                "granddaughter": None, "granddaughters": None, "brother": None, "brothers": None, "sister": None,
                "sisters": None, "nephew": None, "niece": None, "cousin": None, "cousins": None, "uncle": "man", "aunt": "woman",
                "husbands": "man", "wives": "woman", "boyfriend": "man", "girlfriend": "woman"}
ROLE_EXTRA = {"cricketer": "athlete"}
# person words that name no person in the picture ------------------------------------------------------------------------------------
NOT_PERSON_BEFORE = {"chess", "puppet", "puppets", "toy", "toys", "lego", "plastic", "paper", "cardboard", "wooden", "stone", "clay",
                     "marble", "bronze", "porcelain", "ceramic", "ice", "chocolate", "gingerbread", "cookie", "jello", "jelly",
                     "balloon", "inflatable", "stuffed", "plush", "origami", "tin", "wax", "scarecrow", "snow", "sand", "straw",
                     "stick", "wicker", "crash", "action", "emoji", "cutout", "cut-out", "robot", "robotic", "android",
                     "mechanical", "clockwork", "animatronic"}
HEAD_AFTER_PERSON = {"college", "colleges", "school", "schools", "academy", "university", "size", "sized", "piece", "pieces",
                     "costume", "costumes", "outfit", "outfits", "cosplay", "statue", "statues", "statuette", "figurine", "figurines",
                     "doll", "dolls", "puppet", "puppets", "game", "board", "card", "cards", "emoji", "icon", "icons", "logo", "tattoo",
                     "sticker", "mannequin", "bust", "busts", "skull", "skulls", "skeleton", "hand", "hands", "heart", "brain",
                     "foot", "feet", "arm", "arms", "leg", "legs", "finger", "fingers", "torso", "organ", "organs", "rib", "ribs",
                     "spine", "flesh", "blood", "remains", "shape", "shapes", "shaped", "suit", "armor", "armour", "helmet", "crown",
                     "cake", "museum", "magazine", "figure", "figures", "face", "faces", "head", "heads", "vibe", "vibes",
                     "aesthetic", "fashion", "attire", "clothes", "clothing", "gear", "uniform", "uniforms"}
NOT_PERSON_PHRASES = {"father christmas", "father time", "mother goose", "mother nature", "mother earth", "mother ship",
                      "mother board", "mother of pearl", "king size", "queen size", "queen anne", "king cobra", "baby blue", "baby pink",
                      "baby shower", "baby powder", "baby oil", "baby food", "baby grand", "baby teeth", "boy band", "girl power",
                      "girl scout", "girl scouts", "man cave", "man bun", "man made", "guard rail", "guard rails", "uncle sam"}
# a person word after one of these is no person of the picture: what a thing is shaped like, what a statue shows, who made the
# picture ('in the shape of a man', 'a puppet that looks like a king', 'a drawing by a child')
NOT_PERSON_PREFIX = re.compile(
    r"(?:^|\s)(?:shape of|shaped like|form of|looks? like|looking like|resembl(?:e|es|ing)|statues? of|sculptures? of|"
    r"figurines? of|busts? of|carvings? of|effig(?:y|ies) of|dolls? of|puppets? of|mannequins? of|cut-?outs? of|toys? of|"
    r"costumes? of|masks? of|(?:made|drawn|painted|done|created|sketched|photographed|taken|designed|written|illustrated|"
    r"sculpted|carved|built|crafted|rendered|art|artwork|drawing|painting|photo|photograph|photography|illustrations?|"
    r"render|rendering|images?|film|movie|comics?|designs?|poster|cover|sketch|work|works|picture|portrait) by)"
    r"(?: (?!(?:and|or|nor|but|of|with|in|on|at|for|from|to|while|is|are|was|were|who|that|which)\b)[a-z0-9'\-]+){0,3}$")
GUARD_NOT_PERSON = {"closed", "open", "half", "full", "shin", "mud", "hand", "chin", "mouth", "knee", "elbow", "splash", "fender",
                    "sword", "nose", "neck", "chest", "arm", "leg", "finger", "rash", "cheek", "face", "cross", "point", "life",
                    "color", "colour", "crash", "brush", "bumper", "hilt", "blade", "stair", "bed", "wheel", "chain", "toe",
                    "shoulder", "mouthguard", "cage", "spark", "heat", "dust", "wind", "rain", "sun", "lens", "corner"}
ROYAL_TITLES = {"king", "kings", "queen", "queens", "prince", "princes", "princess", "emperor", "empress"}
# person words that, right after an animal word, name a person who works with the animal ('horse rider', 'chicken farmer', 'fish
# vendor'); any other person word there is the animal's guise ('frog knight', 'gorilla astronaut', 'cat chef'): the animal, no person
ANIMAL_AGENTS = {"rider", "riders", "jockey", "farmer", "farmers", "vendor", "vendors", "merchant", "cowboy", "cowgirl", "lady",
                 "ladies"}
# person words that, after an animal word, make a hybrid ('cat girl', 'wolf man'): neither the animal nor a person
HYBRID_HEADS = {"girl", "girls", "boy", "boys", "man", "men", "woman", "women", "guy", "guys", "person", "people", "kid", "kids",
                "child", "children", "human", "humans", "goddess", "male", "female"}
# kin words: two of them side by side name two people ('a mother daughter photo'); any other person word right before another
# describes the same person ('an elderly woman', 'a female knight', 'a baby girl', 'an astronaut girl', 'a warrior woman')
KIN = {"mother", "father", "mom", "dad", "son", "sons", "daughter", "daughters", "brother", "brothers", "sister", "sisters", "husband",
       "husbands", "wife", "wives", "grandmother", "grandfather", "grandma", "grandpa", "grandson", "grandsons", "granddaughter",
       "granddaughters", "aunt", "uncle", "nephew", "niece", "cousin", "cousins", "boyfriend", "girlfriend", "bride", "groom"}
# words before a person word that make it another person than the one before it ('a man and a woman', 'a mother holding her baby',
# 'a doctor talking with a nurse')
OTHER_PERSON_BEFORE = {"and", "&", "or", "nor", "with", "his", "her", "their", "its", "my", "our", "your", "plus", "versus", "vs",
                       "than"}
# words that end the look back from a person word for 'as' ('a corgi as a knight' is a guise; 'a man and a woman' is two people)
AS_GAP_STOP = {"and", "or", "nor", "but", "with", "of", "in", "on", "at", "by", "from", "to", "for", "while", "is", "are", "was",
               "were", "who", "that", "which"}
VIEWPOINT_WORDS = {"at", "into", "towards", "toward", "from", "facing", "faces", "to", "for"}
BABY_NEXT = {"in", "on", "at", "with", "and", "or", "is", "was", "are", "were", "of", "to", "from", "by", "under", "near", "next",
             "inside", "between", "behind", "beside", "who", "that", "while", "as", "for", "into", "onto", "has", "have", "sits",
             "lies", "sleeps", "cries", "smiles", "laughs", "plays", "holds", "wears", "looks", "being", "itself", "alone"}
# the words of a count: a number counts the noun it stands before, never an age, a measure or a title ---------------------------------
AGE_UNITS = {"year", "years", "yr", "yrs", "yo", "month", "months", "week", "weeks", "day", "days", "decade", "decades",
             "century", "centuries"}
MEASURES = {"mm", "cm", "m", "km", "meter", "meters", "metre", "metres", "ft", "foot", "feet", "inch", "inches", "mile", "miles",
            "yard", "yards", "kg", "lb", "lbs", "pound", "pounds", "ton", "tons", "tonne", "tonnes",
            "story", "stories", "storey", "storeys", "floor", "floors", "percent", "degree", "degrees", "x",
            "times", "piece", "pieces", "pack", "mph", "hour", "hours", "minute", "minutes", "second", "seconds", "liter", "liters",
            "litre", "litres", "gallon", "gallons", "oz", "ounce", "ounces", "step", "steps", "dollar", "dollars", "point",
            "points", "bit", "bits", "th", "st", "nd", "rd", "k", "d", "gb", "mb", "megapixel", "megapixels", "fps"}
ED_COMPOUNDS = {"armed", "winged", "legged", "headed", "eyed", "tailed", "horned", "faced", "handed", "footed", "sided", "wheeled",
                "storied", "tiered", "layered", "toed", "fingered", "pointed", "petaled", "petalled", "masted", "decked", "barreled",
                "barrelled", "bladed", "edged", "hooved", "clawed", "fanged", "tusked", "toothed", "spoked", "stringed", "engined",
                "seated", "doored", "roomed", "bedroom", "door", "seater", "speed", "wheel", "cylinder", "lane", "star", "course"}
TRANSITIVE_ING = {"eating", "holding", "carrying", "riding", "wearing", "playing", "reading", "watching", "drinking", "using",
                  "throwing", "catching", "pulling", "pushing", "chasing", "feeding", "petting", "hugging", "driving", "fighting",
                  "hunting", "killing", "attacking", "selling", "buying", "making", "building", "painting", "drawing", "cooking",
                  "baking", "cutting", "kicking", "hitting", "admiring", "fishing", "planting", "picking", "grabbing", "kissing",
                  "touching", "climbing", "crossing", "sharing", "serving", "having", "taking", "giving", "wielding", "brandishing",
                  "swinging", "sipping", "smoking", "juggling", "loading", "washing", "cleaning", "fixing", "repairing",
                  "examining", "inspecting", "studying", "observing", "photographing", "filming", "guarding", "protecting",
                  "herding", "leading", "following", "approaching", "entering", "leaving", "visiting", "exploring", "overlooking",
                  "surrounding", "flanking"}
ING_COMPOUNDS = {"fishing", "drinking", "dining", "living", "sleeping", "swimming", "hunting", "riding", "climbing", "walking",
                 "running", "cooking", "baking", "sewing", "shopping", "parking", "waiting", "washing", "writing", "reading",
                 "playing", "dancing", "boxing", "racing", "sailing", "skating", "skiing", "bowling", "camping", "hiking",
                 "fighting", "gaming", "working", "dressing", "changing", "frying", "cutting", "mixing", "rolling", "landing",
                 "sitting", "colouring", "coloring", "wrapping", "carving", "drawing", "painting", "building", "serving",
                 "smoking", "chopping", "spinning", "rocking", "flying", "sporting", "farming", "mining", "trading",
                 "training", "teaching", "wedding", "steering", "pruning", "watering", "measuring", "sliding"}
# words that name an amount or a container of what follows 'of' ('a piece of cheese', 'a glass of orange juice'): the noun after
# 'of' belongs to the same phrase
QUANTITY_WORDS = {"piece", "pieces", "slice", "slices", "bunch", "bunches", "pair", "pairs", "handful", "stack", "stacks", "pile",
                  "piles", "bouquet", "sheet", "sheets", "lot", "lots", "couple", "set", "sets", "row", "rows", "cluster", "chunk",
                  "chunks", "scoop", "scoops", "stick", "sticks", "roll", "rolls", "spoonful", "armful", "bit", "bits", "strip",
                  "strips", "wedge", "wedges", "loaf", "bar", "bars", "block", "blocks", "tray", "trays", "can", "cans", "carton",
                  "cartons", "sack", "sacks", "crate", "crates", "glass", "cup", "cups", "bowl", "bowls", "plate", "plates", "bag",
                  "bags", "box", "boxes", "basket", "baskets", "bottle", "bottles", "jar", "jars", "mug", "mugs", "pot", "pots",
                  "bucket", "buckets", "herd", "flock", "pack", "swarm", "school", "group", "groups", "team", "family", "crowd"}
DIGIT_BEFORE_OK = {"of", "with", "and", "or", "are", "is", "were", "was", "be", "been", "there", "here", "has", "have", "had", "by",
                   "on", "in", "at", "to", "for", "from", "these", "those", "the", "his", "her", "their", "its", "my", "our", "your",
                   "featuring", "showing", "shows", "show", "including", "includes", "plus", "only", "just", "exactly", "about",
                   "around", "nearly", "almost", "approximately", "roughly", "some", "than", "between", "among", "all", "into",
                   "onto", "under", "over", "behind", "near", "beside", "while", "as", "holding", "carrying", "feeding", "chasing",
                   "watching", "see", "sees"}
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
for form in ("tyrannosaurus rex", "t-rex", "t rex"):
    NOUNS.setdefault(form, ("tyrannosaurus", False, "animal"))
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


def _kind(word: str) -> str:
    return NOUNS.get(word, (0, 0, ""))[2]


def _played_as(toks: list, i: int) -> bool:
    """Whether the person word at toks[i] comes after 'as' (a guise or a comparison, no other person: 'a corgi as a knight', 'a
    woman dressed as a pirate', 'as tall as a man'); 'as well as' and 'such as' join people and keep them."""
    for k in range(i - 1, max(-1, i - 5), -1):
        w = toks[k]
        if w == "as":
            return toks[max(0, k - 2):k] != ["as", "well"] and (k == 0 or toks[k - 1] != "such")
        if w in AS_GAP_STOP or w in PERSON_WORDS or _kind(w):
            return False
    return False


def _is_person(toks: list, i: int, n: int, form: str) -> bool:
    """Whether the person word toks[i:i + n] names a person of the picture: not a modifier of a noun ('cowboy hats', 'baby
    elephant', 'a human white skull', 'wizard college'; 'woman warrior' keeps the woman), not a chess piece, an animal's title or
    guise ('raccoon king', 'frog knight', 'the king of all the mice'), a toy or a statue of one, not what a thing is shaped like
    ('in the shape of a man', 'looks like a king'), not a guise after 'as' ('a corgi as a knight'), not the maker of the picture
    ('a drawing by a child'), not 'baby' as an adjective ('baby daikon radish'), not 'man' as a verb ('the old man the boat'), not
    a title of a name ('father christmas')."""
    nxt = toks[i + n] if i + n < len(toks) else ""
    nxt2 = toks[i + n + 1] if i + n + 1 < len(toks) else ""
    prev = toks[i - 1] if i > 0 else ""
    if f"{form} {nxt}" in NOT_PERSON_PHRASES or f"{form} {nxt} {nxt2}" in NOT_PERSON_PHRASES:
        return False
    if _kind(nxt) not in ("", "place") or NOUNS.get(f"{nxt} {nxt2}", (0, 0, ""))[2] == "animal":
        return False
    if (nxt in HEAD_AFTER and nxt not in PERSON_WORDS) or nxt in HEAD_AFTER_PERSON:
        return False
    if nxt == "look" and not (form.endswith("s") and not form.endswith("ss")) and form not in ("men", "women", "people", "children"):
        return False                                      # 'a modern tourist look' ('two men look at the sea' keeps them)
    if nxt in COLOUR_WORDS and _kind(nxt2) not in ("", "place") and nxt2 not in WEAR_WORDS:
        return False                                      # 'a human white skull' ('a woman red dress' keeps the woman)
    if (form in ("man", "men") and prev in NOT_A_MAN) or prev in NOT_PERSON_BEFORE:
        return False
    if _kind(prev) == "animal" and form not in ANIMAL_AGENTS:
        return False                                      # 'raccoon king', 'cat girl', 'frog knight'; 'horse rider' keeps its person
    if nxt in ("made", "nature", "earth") or (form == "nurse" and nxt == "shark") or (form == "monk" and nxt == "seal"):
        return False
    if form in ("baby", "babies") and nxt and nxt not in BABY_NEXT and nxt not in PERSON_WORDS and not re.search(r"(ing|ed)$", nxt):
        return False
    if form in ("man", "men", "old man", "old men") and nxt == "the":
        return False
    if form in ("guard", "guards") and prev in GUARD_NOT_PERSON:
        return False
    if nxt == "of" and any(_kind(w) == "animal" for w in toks[i + n + 1:i + n + 4]):
        return False
    if NOT_PERSON_PREFIX.search(" ".join(toks[max(0, i - 6):i])) or _played_as(toks, i):
        return False
    return True


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
                if n > 1 and toks[i] in ("old", "older") and i > 0 and toks[i - 1] in AGE_UNITS:
                    continue                                  # '25 year old man': an age, not 'old man' (elderly)
                if not _is_person(toks, i, n, form):
                    continue
                hit = (i, i + n, form, form.endswith("s") and not form.endswith("ss"), "person", PERSON_WORDS[form])
                break
            if form in NOUNS:
                w, pl, kind = NOUNS[form]
                nxt = toks[i + n] if i + n < len(toks) else ""
                if form == "camera" and i >= 1 and (toks[i - 1] in VIEWPOINT_WORDS or
                                                    (i >= 2 and toks[i - 1] == "the" and toks[i - 2] in VIEWPOINT_WORDS)):
                    hit = (i, i + n, None, False, "modifier", None)       # 'facing the camera': the viewer, no thing
                    break
                nxt2 = toks[i + n + 1] if i + n + 1 < len(toks) else ""
                if kind == "animal" and (nxt in ROYAL_TITLES or (nxt in PERSON_WORDS and nxt not in ANIMAL_AGENTS and
                                                                 nxt not in HYBRID_HEADS)) \
                        and _kind(nxt2) in ("", "place") and nxt2 not in HEAD_AFTER_PERSON:
                    hit = (i, i + n, w, pl, kind, None)       # 'the raccoon king', 'a gorilla astronaut': the animal, no person
                    break                                     # ('a wombat warrior statue' is a statue)
                if nxt in HEAD_AFTER or (nxt in NOUNS and NOUNS[nxt][2] != "place") or nxt in PERSON_WORDS:
                    hit = (i, i + n, None, False, "modifier", None)       # 'dog house', 'cat ears', 'strawberry blonde'
                    break
                hit = (i, i + n, w, pl, kind, None)
                break
        if hit:
            if hit[4] != "modifier" and not NEGATION & set(toks[max(0, i - 3):i]):   # 'without any boats': not in the picture
                p = out[-1] if out else None
                said = p is not None and p[2] in maps.GENDER and hit[2] not in maps.GENDER   # 'a female cowboy', 'a woman priest'
                if hit[4] == "person" and p and p[4] == "person" and p[1] == hit[0] and not (p[2] in KIN and hit[2] in KIN) \
                        and (said or not (p[5][0] and hit[5][0] and p[5][0] != hit[5][0])):
                    a, b = p[5], hit[5]                   # 'an elderly woman', 'two female soldiers': one person, its words joined;
                    g = a[0] if said else (b[0] or a[0])  # a gender word before a role word outranks the role's usual gender
                    out[-1] = (p[0], hit[1], hit[2], hit[3], "person", (g, a[1] or b[1], b[2] or a[2]))
                else:
                    out.append(hit)
            i = hit[1]
        else:
            i += 1
    return out


NUMBER_WORDS = {w for w in NUMBERS if w not in ("a", "an", "single", "a pair of", "twin")}


def _counts_the_noun(toks: list, j: int, start: int) -> bool:
    """Whether the number toks[j] counts the noun at `start`: no measure, age unit or '-ed' compound between them ('six meters
    tall mech', 'a 8 winged 4 armed angel'), no verb taking an object between them ('a family of 6 eating pizza'), and a digit
    opens its phrase (after a function word, never after a title: 'metin 2 warrior')."""
    between = toks[j + 1:start]
    if between and between[-1] in ING_COMPOUNDS:
        between = between[:-1]                            # 'a fishing village', 'a hunting dog': a kind of noun, not a verb
    if any(b in TRANSITIVE_ING for b in between):
        return False
    if toks[j] in ("a", "an", "single"):
        return True                                       # an article: 'a horned owl', 'a tall man' are one
    if between and (between[0] in ED_COMPOUNDS or between[0] in AGE_UNITS):
        return False
    if any(b in MEASURES or b in AGE_UNITS for b in between):
        return False
    if toks[j].isdigit() and j > 0 and toks[j - 1] not in DIGIT_BEFORE_OK and toks[j - 1] not in NUMBERS:
        return False
    return True


def _lookback(toks: list, start: int) -> tuple:
    """(count, colour) from the words just before a mention: a number or an article, and a colour adjective. An age before the
    noun ('a 25 year old man', 'a twelve years old girl') is passed over, never read as a count; a number that does not count the
    noun (_counts_the_noun) ends the search with no count."""
    count = colour = None
    j = start - 1
    steps = 0
    end = start                                           # where the counted phrase ends (before an age passed over)
    while j >= 0 and steps < 4:
        w = toks[j]
        two = " ".join(toks[j - 1:j + 1]) if j >= 1 else ""
        if w in NOUN_COLOURS and toks[j + 1:j + 2] not in (["colored"], ["coloured"], ["color"], ["colour"]):
            j -= 1                                        # 'wine bottles': a kind of bottle, not a colour
            steps += 1
            continue
        if w in ("old", "aged") or w in AGE_UNITS:
            k = j
            while k >= 0 and (toks[k] in AGE_UNITS or toks[k] in ("old", "aged")):
                k -= 1
            if k >= 0 and k < j and (toks[k].isdigit() or toks[k] in NUMBER_WORDS):
                j = end = k                               # '25 year old': an age, passed over whole
                j -= 1
                steps += 1
                continue
        if two in COLOUR_WORDS and colour is None:
            colour = COLOUR_WORDS[two]
            j -= 2
            steps += 2
            continue
        if w in COLOUR_WORDS and colour is None:
            colour = COLOUR_WORDS[w]
        elif w in NUMBERS or (w.isdigit() and 0 < int(w) < 100):
            if _counts_the_noun(toks, j, end):
                count = NUMBERS[w] if w in NUMBERS else int(w)
            break
        elif w.isdigit() or w in STOP_LOOKBACK or w in NOUNS or w in PERSON_WORDS:
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


# a phrase after one of these words names a thing inside the scene, not the picture itself: 'a wall with a large framed oil
# painting', 'a cat reading a comic book', 'a man holding a photo' (unless the words ask for the picture's look: 'in the style of
# an oil painting', 'as a watercolour')
IN_SCENE = re.compile(r"(?<![\w\-])(?:framed|with|reading|reads|displays?|displaying|holding|holds|hanging|hangs|showing|shows|"
                      r"carrying|carries|admiring|admires|looking at|looks at|watching|watches|beside|behind|near|next to|on|of|"
                      r"onto|into|like)\s+(?:(?:a|an|the|his|her|their|its|two|"
                      r"three|some|several|many|large|small|big|huge|giant|little|old|vintage|famous|framed|beautiful|new|blank|"
                      r"torn|wooden|colou?rful|hanging|unfinished|antique|classic)\s+)*$")
STYLE_OF = re.compile(r"\b(?:style|manner|form|look|technique|medium)\s+of\s+(?:an?\s+|the\s+)?$|\b(?:as|in)\s+(?:an?\s+|the\s+)?$")
# a scene word inside a picture shown in the scene ('a television that displays an image of a cityscape at night'): the time, the
# weather, the setting, the light and the form of that picture, not of this one
IMAGE_OF = re.compile(r"\b(?:displays?|displaying|showing|shows|depicting|depicts|projecting|projects|with|framed|hanging|"
                      r"holding|holds|reading|reads|watching|watches|on)\s+(?:an?\s+|the\s+|two\s+|some\s+)?(?:[a-z\-]+\s+){0,3}?"
                      r"(?:image|picture|photo|photograph|painting|poster|drawing|print|video|film|movie|reflection|screen|"
                      r"postcard|map|mural|portrait)s?\s+(?:of|showing|with|depicting)\b")
ICON_WORDS = re.compile(r"\b(?:sign|signs|logo|logos|icon|icons|sticker|stickers|decal|emblem|symbol|flag|t-shirt|shirt|poster|"
                        r"stamp|badge|tattoo|stencil|label|coin|medal|patch|banner|plaque|placard)\b")
THREE_QUARTER = re.compile(r"\b(?:three[- ]quarters?|3/4)\s+(?:front\s+|back\s+|rear\s+|side\s+)?"
                           r"(?:view|angle|shot|portrait|profile|pose|turn)\b")
# titles of paintings, books and films that hold scene, style or person words: never read as the picture's facts
TITLES = re.compile(r"\b(?:american gothic|mona lisa|(?:the|style of|says|reads|called|titled|named) starry night|starry night(?=\")|"
                    r"the last supper|the night watch|(?:the )?persistence of "
                    r"memory|(?:the )?birth of venus|girl with a pearl earring|the great wave(?: off kanagawa)?|the son of man|"
                    r"(?:the )?garden of earthly delights|(?:the )?creation of adam|(?:the )?school of athens|the scream|"
                    r"animal farm|"
                    # games, films and books whose names hold such words
                    r"elden ring|(?:the )?lord of the rings|game of thrones|league of legends|world of warcraft|(?:the )?lion king|"
                    r"(?:the )?little mermaid|(?:the )?jungle book|(?:the )?walking dead|horizon zero dawn|horizon forbidden west|"
                    r"dark souls|demon'?s souls|god of war|(?:the )?last of us|red dead redemption|pirates of the caribbean|"
                    r"toy story|planet of the apes|jurassic (?:park|world)|monster hunter|mass effect|doctor who|"
                    r"(?:teenage mutant )?ninja turtles|winnie the pooh|alice in wonderland|(?:the )?wizard of oz|"
                    r"beauty and the beast|fantastic beasts|how to train your dragon|mad max|"
                    r"blade runner|ghost in the shell|attack on titan|dragon age|fire emblem|(?:the )?elder scrolls|"
                    r"magic the gathering|dungeons (?:and|&) dragons|baby boss|(?:the )?elephant man|king kong|"
                    r"(?:the )?legend of zelda|breath of the wild|final fantasy|kingdom hearts|devil may cry|"
                    r"(?:the )?witcher|resident evil|silent hill|team fortress|half-life|cyberpunk 2077|death stranding|"
                    r"metal gear|street fighter|mortal kombat|star trek|harry potter|(?:the )?hunger games|sailor moon)\b")


def _inside_image(t: str, start: int) -> bool:
    """Whether the phrase at `start` describes a picture shown inside the scene (IMAGE_OF in its sentence before it)."""
    k = max(t.rfind(c, 0, start) for c in ".;!?")
    return bool(IMAGE_OF.search(t[k + 1:start]))


# pictures the scene holds ('two paintings on the wall', 'a framed photo'): with them in the text, a medium or a style word followed
# by what it shows ('The one on the left a detailed oil painting of the royal raccoon king') describes one of them, unless it opens
# the text before they are named ('An oil painting of a hall with two paintings on the wall')
SCENE_PICTURES = re.compile(r"\b(?:paintings?|portraits?|pictures?|posters?|photos?|photographs?|drawings?|prints?|canvases|artworks?)"
                            r"\s+(?:on|hanging on|hung on)\s+(?:the|a|its|their)\s+walls?\b|\bframed\s+(?:[a-z]+\s+){0,2}"
                            r"(?:paintings?|portraits?|pictures?|photos?|photographs?|posters?|drawings?|prints?)\b|"
                            r"\b(?:hanging|hung)\s+(?:paintings?|portraits?|pictures?|photos?|photographs?)\b")
# a form word after one of these is a thing in the scene ('a man holding a photo', 'a dog with a polaroid camera'); the narrower
# list of IN_SCENE that the picture's domain is judged by ('shot on kodak', 'scratches on photo' speak of this picture)
HELD_PICTURE = re.compile(r"(?<![\w\-])(?:framed|with|reading|reads|displays?|displaying|holding|holds|hanging|hangs|showing|shows|"
                          r"carrying|carries|admiring|admires|looking at|looks at|watching|watches)\s+(?:(?:a|an|the|his|her|their|"
                          r"its|two|three|some|several|many|large|small|big|huge|giant|little|old|vintage|famous|framed|beautiful|"
                          r"new|blank|torn|wooden|colou?rful|hanging|unfinished|antique|classic|bunch|lot|lots|pile|stack|set|"
                          r"collection|couple|series|of|oil|watercolou?r|acrylic|ink|pencil|charcoal|pastel|gouache)\s+)*$")


def _among_pictures(t: str, start: int, end: int) -> bool:
    m = SCENE_PICTURES.search(t)
    if not m or (m.start() >= end and not re.search(r"[.;!?]", t[:start])):
        return False
    return bool(re.match(r"\s*(?:of|showing|depicting)\b", t[end:]))


def _guarded(t: str, mapping: dict, guard, scene: bool = False, form: bool = False) -> str | None:
    """The first value of the mapping in the text whose guard accepts its context; a blocking phrase is passed over, and so is a
    negated one ('no rain', 'without a hat') and, for the picture's scene, light and form (`scene`), one inside a picture shown in
    the scene; for the picture's form (`form`), one that may speak of a picture the scene holds (_among_pictures)."""
    for s, e, phrase, value in _hits(t, mapping):
        if value is None:
            continue
        before = _before(t, s)
        clause = re.split(r"[,.;:!?()\[\]\"|]", before)[-1]          # a negation of the same clause only
        if NEGATION & set(clause.split()[-3:]) or (scene and _inside_image(t, s)) or (form and _among_pictures(t, s, e)):
            continue
        if guard(phrase, value, before, _after(t, e)):
            return value
    return None


def _in_scene(before: str) -> bool:
    b = before + " "
    return bool(IN_SCENE.search(b)) and not STYLE_OF.search(b)


def _g_medium(phrase, value, before, after):
    if value in ("bronze", "marble", "clay"):
        return False                                          # the material of a depicted object, not the picture's medium
    if phrase == "wood engraving":
        return False                                          # an engraving, not a woodcut; the list has no value for it
    if _in_scene(before):
        return False                                          # 'a wall with a large framed oil painting of a car'
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
    if _in_scene(before):
        return False                                          # 'a cat reading a comic book'
    if value == "gothic" and before.endswith("american"):
        return False                                          # 'American Gothic' is a painting's title
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
    if value == "silhouette" and (ICON_WORDS.search(before) or ICON_WORDS.match(after) or
                                  re.search(r"\bwith\s+(?:an?\s+|the\s+)?(?:[a-z\-]+\s+)?$", before + " ")):
        return False                                          # 'a sign with a deer silhouette': a shape on a thing, not the light
    return True


def _g_angle(phrase, value, before, after):
    if value == "profile" and (re.match(r"(picture|pic|photo|image)\b", after) or not re.search(r"\b(side|in|from the)$", before)):
        return False
    if value == "overhead" and re.match(r"(light|lights|lighting|lamp)\b", after):
        return False
    if value == "frontal" and re.search(r"\b(three[- ]quarters?|3/4|quarter)$", before):
        return False                                          # 'three-quarters front view' is not frontal
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
    # a compound or a title that names no place: a jungle gym, a windmill farm, farm animals, Animal Farm, subway tile, a
    # reliquary shrine, a beach-themed party
    if phrase == "jungle" and re.match(r"(gym|gyms|juice|book|fever|cat|cats|print|pattern|fowl|bird|birds)\b", after):
        return False
    if value == "farm" and (re.search(r"\b(windmill|windmills|wind|solar|server|ant|worm|data|link|bot|troll|click|content|crypto|"
                                      r"animal|turbine|turbines)$", before) or
                            re.match(r"(animals?|fresh|hands?|boy|girl|house|stand|table|equipment|tractor|toys?|set|playset|"
                                     r"life)\b", after)):
        return False
    if value == "subway" and re.match(r"(tiles?|tiled|sandwich(?:es)?|maps?|surfers?|logo|signs?|posters?|ads?|font|style|art|"
                                      r"ticket|tokens?)\b", after):
        return False
    if phrase == "shrine" and (before.endswith("reliquary") or re.match(r"(box|cabinet|model|miniature)\b", after)):
        return False
    if re.match(r"-?(themed|style|styled|print|pattern|patterned|wallpaper|decor)\b", after):
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


PREPOSITIONS = {"of", "in", "on", "at", "by", "with", "from", "to", "into", "onto", "under", "over", "behind", "near", "beside", "next",
                "above", "below", "between", "among", "through", "across", "around", "inside", "outside", "toward", "towards",
                "against", "along", "beneath", "underneath", "for", "during", "without", "within", "upon", "off", "out", "up",
                "down", "past", "beyond", "like", "as"}
CONJUNCTIONS = {"and", "or", "but", "nor", "yet", "so", "then", "who", "that", "which", "where", "when", "while"}
# words that may stand between a relation's subject and the relation word ('a dog sitting next to a cat', 'a cat is under a table')
A_GAP_OK = {"is", "are", "was", "were", "be", "being", "sits", "sit", "sitting", "seated", "sat", "stands", "stand", "standing",
            "placed", "located", "positioned", "set", "lies", "lie", "lying", "laying", "seen", "shown", "that", "which", "who",
            "just", "directly", "right", "slightly", "far", "very", "also", "both", "all", "together", "alone", "here", "there",
            "now", "still", "posed", "posing", "floating", "hovering", "parked", "perched", "waiting", "resting", "hanging",
            "flying", "walking", "running", "swimming", "kneeling", "crouching", "leaning", "mounted", "hiding", "peeking",
            "lurking", "hidden", "partly", "partially", "mostly", "completely", "closely", "gently", "proudly", "happily",
            "quietly", "calmly", "slowly", "casually", "sleeping", "smiling", "grinning", "laughing", "playing", "dancing",
            "jumping", "glowing", "shining", "stood", "lay", "rises", "rising", "looms", "looming", "towers", "towering",
            "hangs", "floats", "flies", "glows", "shines", "appears", "emerges", "rests", "waits", "perches", "hovers", "hides",
            "peeks", "lurks", "poses", "swims", "walks", "runs", "dances", "jumps", "plays", "sleeps", "grows", "growing",
            "flows", "flowing", "lands", "landing"} | set(maps.POSE)
# a word that makes the noun after it an object, not a relation's subject ('wearing headphones and glasses standing in front of')
OBJECT_MARKERS = (TRANSITIVE_ING | (PREPOSITIONS - {"as"}) |
                  {"wears", "wear", "holds", "carries", "eats", "reads", "rides", "plays", "uses", "has", "have", "had", "having",
                   "facing", "faces", "looking", "watching", "pointing", "aiming", "shooting"})
PICTURE_WORDS = {"photo", "photograph", "picture", "image", "painting", "drawing", "illustration", "portrait", "render", "rendering",
                 "sketch", "still", "shot", "closeup", "close-up", "view", "scene", "art", "artwork", "poster", "watercolor",
                 "watercolour", "print", "engraving", "etching", "woodcut", "lithograph", "cartoon", "animation", "comic", "concept",
                 "photography", "depiction", "study"}
PRONOUN_OBJECTS = {"them", "him", "it", "us", "me", "you", "each", "itself", "himself", "herself", "themselves", "one", "another",
                   "everyone", "everything", "something", "anyone", "anything", "nothing"}
B_GAP_BAD = PREPOSITIONS | CONJUNCTIONS | {"is", "are", "was", "were", "away", "not", "no", "never"}
B_END_OK = PREPOSITIONS | CONJUNCTIONS | {"is", "are", "was", "were", "has", "have", "had", "being", "be", "together", "alone",
                                          "here", "there", "nearby", "too", "again", "now", "today", "close", "very", "all",
                                          "both", "whose"} | set(maps.POSE) | set(maps.GESTURE)


def _singular(form: str) -> str:
    return form[:-1] if form.endswith("s") and not form.endswith("ss") else form


def _is_object(toks: list, start: int) -> bool:
    """Whether the noun phrase that starts at `start` is the object of a verb or a preposition before it, read back over its
    determiners and adjectives and over coordinated nouns ('wearing headphones and glasses'): never a relation's subject. 'A
    photo of a cat beside a dog' keeps the cat: 'of' after a picture word opens the picture's subject."""
    j = start - 1
    for _ in range(7):
        if j < 0:
            return False
        w = toks[j]
        if w == "of" and j > 0 and toks[j - 1] in QUANTITY_WORDS:
            j -= 2                                        # 'a glass of orange juice': read on before 'a glass'
            continue
        if w in OBJECT_MARKERS:
            return not (w == "of" and j > 0 and toks[j - 1] in PICTURE_WORDS)
        if (w in NOUNS or w in PERSON_WORDS) and toks[j + 1] not in ("and", "or"):
            return False                                  # another noun's phrase: this one is not its object
        j -= 1
    return False


def _gap_ok(gap: list) -> bool:
    """The words between a relation's subject and the relation word: none, or a phrase that keeps the subject ('sitting', 'is',
    'with long hair', 'breaching', 'stands a few feet'), never a verb taking an object, a conjunction or a negation, and never an
    unknown word right after the subject (a compound: 'sea agate')."""
    if not gap:
        return True
    first = gap[0]
    if not (first in A_GAP_OK or first in ("with", "in", "on", "at") or A_GAP_OK_LY.fullmatch(first) or
            (first.endswith("ing") and (first not in TRANSITIVE_ING or len(gap) == 1))):
        return False                                      # 'a man driving inside a car': a verb right before the relation
    return not any(w in CONJUNCTIONS or w in NEGATION for w in gap) and not any(w in TRANSITIVE_ING for w in gap[:-1])


A_GAP_OK_LY = re.compile(r"[a-z]+ly$")                    # an adverb between the subject and the relation: 'rises majestically'


def _relation_ends(toks: list, ms: list, ws: int, we: int, rel: str):
    """(a, b): the mentions a relation word at toks[ws:we] binds, or None. Side a is the phrase's own subject: it stands just
    before the relation word (only a verb of placement or posture between: 'a dog sitting next to a cat'), it is no modifier of
    another noun ('sea agate beside'), and it is no object of a verb before it. Side b is the noun right after the relation word,
    a whole noun phrase ('under street lights' names no street), never a pronoun ('in front of them') or a noun after another
    phrase ('watching fireworks by a city'). A negated relation ('not holding', 'facing away from') gives none, and so does
    'facing the camera' (the viewer, not a thing of the picture)."""
    if NEGATION & set(toks[max(0, ws - 3):ws]) or toks[we:we + 1] == ["away"]:
        return None
    a = [m for m in ms if m[1] <= ws and ws - m[1] <= 4]
    b = [m for m in ms if m[0] >= we and m[0] - we <= 3]
    if not a or not b:
        return None
    a, b = a[-1], b[0]
    if not _gap_ok(toks[a[1]:ws]) or _is_object(toks, a[0]):
        return None
    gap = toks[we:b[0]]
    if (gap and gap[0] in PRONOUN_OBJECTS) or any(w in B_GAP_BAD and not (w == "of" and k and gap[k - 1] in QUANTITY_WORDS)
                                                  for k, w in enumerate(gap)):
        return None
    nxt = toks[b[1]] if b[1] < len(toks) else ""
    if nxt and nxt not in B_END_OK and not re.search(r"(ing|ed|ly)$", nxt):
        return None
    if rel in ("facing", "looking at") and b[2] == "camera":
        return None
    return a, b


def spec_from_text(text: str, spec: core.Spec | None = None) -> tuple:
    """-> (Spec, info): the records the text states. info: persons (bool), thing (str|None), animal (bool), nouns (list)."""
    s = spec or core.Spec()
    t = TITLES.sub(" , ", norm_digits(core.ascii_text(text).lower()))
    clauses = [c for c in re.split(r"[.;:!?\n()\[\]{}\"|]+|,", MASK.sub(" , ", t)) if c.strip()]
    toks_by = {i: _tokens(c) for i, c in enumerate(clauses)}
    ment_by = {i: _mentions(toks) for i, toks in toks_by.items()}
    persons = [(i, m) for i, ms in ment_by.items() for m in ms if m[4] == "person"]
    nouns = [(i, m) for i, ms in ment_by.items() for m in ms if m[4] != "person"]
    info = {"persons": bool(persons), "thing": None, "animal": False, "nouns": [m[2] for _, m in nouns]}
    # persons
    if persons:
        counts, genders, ages, roles = [], [], [], []
        others = False                                    # a person word that names another person than the one before it
        for k, (i, m) in enumerate(persons):
            if k and persons[k - 1][0] == i:              # 'and', 'her' between them, or two kin words side by side
                end = persons[k - 1][1][1]
                others = others or end == m[0] or bool(OTHER_PERSON_BEFORE & set(toks_by[i][max(end, m[0] - 3):m[0]]))
            g, a, r = m[5]
            c, _ = _lookback(toks_by[i], m[0])
            if m[3] or m[2] in ("people", "children", "men", "women", "gentlemen", "folk", "old men", "young men", "young women"):
                c = c if c and c > 1 else None            # a plural without a number: no count
            counts.append(c)
            genders.append(g)
            ages.append(a)
            roles.append(r if r and _g_role(m[2], r, " ".join(toks_by[i][max(0, m[0] - 2):m[0]]),
                                           " ".join(toks_by[i][m[1]:m[1] + 2])) else None)
        if all(counts):
            s.set("person", "count", str(sum(counts)))
        # a gender or a role: words that disagree give none ('a man and a woman', 'a princess girl'); for two people or more it must
        # hold for every one of them ('a father and a son' has no gender and no role, 'a mother holding her baby' no gender); several
        # words for one person give theirs ('a young female elven warrior'); an age goes with a single person (core.cohere)
        several = others or (all(counts) and sum(counts) > 1)

        def held_by_all(vals):
            named = {x for x in vals if x}
            if len(named) != 1:
                return None
            return (vals[0] if all(x == vals[0] for x in vals) else None) if several else named.pop()

        g = held_by_all(genders)
        if g:
            s.set("person", "gender", g)
        a = next((x for x in ages if x), None)
        if a:
            s.set("person", "age", a)
        r = held_by_all(roles)
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
    # the thing: the first concrete noun (worn things only when nobody wears them: no person, and no person-shaped figure such as
    # a statue, a puppet or a cat girl), places last
    figures = persons or any(w in PERSON_WORDS for toks in toks_by.values() for w in toks)
    skip = WEAR_WORDS if figures else set()
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
    # relations between two mentions of a clause: the subject before the relation word and the noun right after it
    for i, toks in toks_by.items():
        ms = ment_by[i]
        clause = " ".join(toks)
        for st, en, phrase, rel in _hits(clause, LOCAL_RELATION):
            if phrase == "over" and re.match(r"(the shoulder|and)\b", clause[en:].lstrip()):
                continue
            ws, we = len(clause[:st].split()), len(clause[:en].split())
            ends = _relation_ends(toks, ms, ws, we, rel)
            if not ends:
                continue
            a, b = ends
            if rel in ("holding", "looking at", "facing") and a[4] not in ("person", "animal"):
                continue
            wa = (a[5][0] or _singular(a[2])) if a[4] == "person" else a[2]
            wb = (b[5][0] or b[2]) if b[4] == "person" else b[2]
            s.relate(wa, rel, wb)
            if len(s.rels) >= 3:
                break
    # the scene, the shot, the form
    v = _guarded(t, maps.SETTING, _g_setting, scene=True)
    if v:
        s.set("scene", "setting", v)
    v = _guarded(t, maps.TIME, _g_time, scene=True)
    if v:
        s.set("scene", "time", v)
    v = _guarded(t, WEATHER_X, _g_weather, scene=True)
    if v:
        s.set("scene", "weather", v)
    if re.search(r"\b(a crowd|crowds|crowded with people|a throng)\b", t):
        s.set("scene", "layout", "crowd")
    v = _guarded(t, maps.LIGHT, _g_light, scene=True)
    if v:
        s.set("shot", "light", v)
    if THREE_QUARTER.search(t):
        s.set("shot", "angle", "three quarter")
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
    v = _guarded(t, maps.MEDIUM, _g_medium, scene=True, form=True)
    if v:
        s.set("form", "medium", v)
    v = _guarded(t, maps.STYLE, _g_style, scene=True, form=True)
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


PHOTO = re.compile(r"\b(photo|photos|photograph|photographs|photography|dslr|polaroid|snapshot|selfie|film still|35mm film|kodak|"
                   r"portra|fujifilm|canon eos|nikon|leica|hasselblad)\b")


def _own_form(t: str, m) -> bool:
    """Whether the form word of match m speaks of this picture, not of one shown inside the scene ('a man holding a photo', 'a
    wall with a framed oil painting', 'two paintings on the wall')."""
    before = _before(t, m.start()) + " "
    bare = re.search(r"\bwith\s+$", before) and not re.match(r"(?:a|an|the)\s", m.group(0))
    held = HELD_PICTURE.search(before) and not bare and \
        not re.search(r"\b(?:made|shot|taken|captured|photographed|filmed)\s+with\s+(?:an?\s+|the\s+)?$", before)
    return not (held or _inside_image(t, m.start()) or _among_pictures(t, m.start(), m.end()))   # 'shot with a leica', 'line art
    # with watercolor': how this picture was made


def domain_of(t: str) -> str:
    """photograph when the text asks for a photo; painting for paint media; design for logos, icons and product renders;
    illustration otherwise. A photo or a painting shown inside the scene says nothing of this picture's domain."""
    t = t.lower()
    if re.search(r"\b(logo|logos|icon|icons|emblem|app icon|sticker design|t-shirt design|product render|product design|"
                 r"packaging design|wordmark|monogram|infographic)\b", t):
        return "design"
    t = MASK.sub(" ", norm_digits(t))                       # 'photo realistic', 'photographic' ask for a look, not a photograph
    if any(_own_form(t, m) for m in PHOTO.finditer(t)):
        return "photograph"
    if any(_own_form(t, m) for m in PAINT.finditer(t)):
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
def finish(dataset: str, sid: str, s: core.Spec, group: str | None = None) -> dict:
    """The spec as make_seed will route it, without a wear colour whose garment was a sealed value and was stripped (the colour
    of a text's garment says nothing once the garment is gone). A held seed stays whole. (A thing whose sealed name is stripped
    goes whole in core.strip_sealed.) `group`: the same picture's id that make_seed is given, so both draw the same way."""
    raw = s.spec()
    out, held = core.route(f"{dataset}:{sid}", raw, group)
    if held:
        return raw
    if "wear" in out and not ({"clothing", "accessory"} & set(out["wear"])):
        out["wear"].pop("colour", None)
        if not out["wear"]:
            del out["wear"]
    return out
