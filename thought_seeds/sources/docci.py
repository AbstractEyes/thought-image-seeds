"""thought_seeds.sources.docci - DOCCI (Descriptions of Connected and Contrasting Images) -> hidden picture specs.

Each DOCCI image has one long human description (about 120 words) that opens with a view sentence ("A medium-close-up view of a
real sized stuffed dog with white and black fur ...") and goes on with positions, counts, colours and spatial relations. Per
description: the view phrase gives the shot framing and angle; the first noun phrase after it gives the main subject (the thing:
its name with a material or toy word kept, its count from the number word, its one colour, a state word; or the person system when
the subject is a person); sentences whose subject is that thing give its position ('on the left side of the image'); sentences of
the anchored forms 'A <x> is behind the <y>' and 'Behind the <y> is a <x>' give up to six relations of the trie's list; sky, time
and light words give the scene's weather and time and the shot's light direction and focus. A value is taken only where the phrase
is unambiguous (two colours, two weathers or two settings: none). The description is the hint: every sentence that may hold a name
(core.drop_named_strict with the plain words of all the descriptions: 'Einstein's left arm ...' opens with one), quoted text,
upper-case text or talk of the image as an image is dropped, the rest cut at 600 bytes. Only the description file is read: no image
is downloaded, used or redistributed."""
from __future__ import annotations

import json
import os
import re
from collections import Counter

from .. import core, maps

DATASET = "docci"
LICENSE = "CC BY 4.0"
URL = "https://google.github.io/docci/"
ATTRIBUTION = ("DOCCI: Descriptions of Connected and Contrasting Images (Onoe et al., ECCV 2024), descriptions by Google LLC, "
               "CC BY 4.0; descriptions only, no image used or redistributed")
CITATION = r"""@inproceedings{OnoeDocci2024,
  author    = {Yasumasa Onoe and Sunayana Rane and Zachary Berger and Yonatan Bitton and Jaemin Cho and Roopal Garg and Alexander Ku and Zarana Parekh and Jordi Pont-Tuset and Garrett Tanzer and Su Wang and Jason Baldridge},
  title     = {{DOCCI}: Descriptions of Connected and Contrasting Images},
  booktitle = {Computer Vision -- ECCV 2024},
  year      = {2024},
  eprint    = {2404.19753},
  archivePrefix = {arXiv}
}"""
TAKEN = ("records + hint: from the human description, the view phrase (shot framing, angle), the main subject (thing name, count, "
         "colour, state, position; or person count, gender, age, role, wear, pose), anchored spatial relations, sky / time / light "
         "words (scene weather, time; shot light, focus), form medium photograph; hint = the description without any sentence that "
         "may hold a name, quoted text, upper-case text or talk of the image as an image, cut to 600 bytes")
MODIFIED = ("modified by this dataset: values extracted from the descriptions and mapped to the dataset's closed lists; the hint is "
            "an excerpt of the description (sentences removed as stated, the rest cut to fit 600 bytes)")

FILE = "docci_descriptions.jsonlines"
FILE_URL = "https://storage.googleapis.com/docci/data/docci_descriptions.jsonlines"
FILE_BYTES = 11000214
DOMAIN = "photograph"
MIN_RECORDS = 3

STATS: Counter = Counter()          # the last seeds() run: rows seen, seeds, the drop reasons


# ------------------------------------------------------------------ download
def fetch(raw_dir: str) -> dict:
    """The description file (10.5 MB, text only) into raw_dir/docci/; skipped when present at its published size."""
    d = os.path.join(raw_dir, DATASET)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, FILE)
    if not (os.path.exists(path) and os.path.getsize(path) == FILE_BYTES):
        import requests
        tmp = path + ".part"
        with requests.get(FILE_URL, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as fh:
                for b in r.iter_content(1 << 20):
                    fh.write(b)
        os.replace(tmp, path)
    return {FILE: os.path.getsize(path)}


# ------------------------------------------------------------------ words
NUMBERS = {"a": "1", "an": "1", "one": "1", "single": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
           "seven": "7", "eight": "8", "nine": "9", "ten": "10", "several": "several", "many": "many", "multiple": "several",
           "numerous": "many", "some": "several", "few": "several", "various": "several", "dozens": "many", "hundreds": "many"}
for _i in range(2, 13):
    NUMBERS[str(_i)] = str(_i)
# '<quantity> of <noun>': the count it gives ('a pair of shoes' -> 2)
QUANTITY = {"pair": "2", "couple": "2", "group": "several", "row": "several", "set": "several", "bunch": "several",
            "pile": "several", "stack": "several", "line": "several", "herd": "several", "flock": "several", "collection": "several",
            "cluster": "several", "series": "several", "assortment": "several", "variety": "several", "handful": "several",
            "number": "several", "lot": "many", "lots": "many", "crowd": "many", "bundle": "several", "trio": "3",
            # a part of a mass: the noun after it is the subject, without a count ('a piece of fish')
            "piece": None, "slice": None, "chunk": None, "strip": None, "patch": None, "scoop": None, "sprig": None,
            "clump": None, "sheet": None, "bit": None, "portion": None, "section": None, "part": None, "close-up": None,
            "closeup": None}
QUANTITY.update({"pairs": "several", "groups": "several", "rows": "several", "sets": "several", "bunches": "several",
                 "piles": "several", "stacks": "several", "lines": "several", "clusters": "several", "bundles": "several",
                 "pieces": None, "slices": None, "strips": None, "chunks": None, "patches": None, "bits": None, "sheets": None,
                 "clumps": None, "dozens": "many", "hundreds": "many"})
# words that end a noun phrase: a determiner starts a new one ('building the Tower'); 'besides' is written for 'beside'
STOP = set("with on in at of by from near under over above below behind beside between inside against along across through into "
           "onto upon to toward towards for like without that which who whose where while is are was were has have had and or but "
           "as than so then its their his her it they this these those there here can could will would being been be also very "
           "both each all some any no not one next close nearby alongside outside around beneath underneath atop among amongst "
           "amid within beyond past via during after before until since except about off out up down away together apart "
           "whose what when how why the a an another besides throughout".split())
VERBISH = set("sitting standing lying laying sits stands lies lays hanging hangs resting rests placed parked facing looking made "
              "holding wearing seen shown displayed covered filled growing flying floating perched leaning mounted attached painted "
              "carved extending running walking moving swimming sleeping eating drinking reading playing showing visible shining "
              "casting reflecting pointing positioned located set lined surrounded "
              # verbs of the third person that end a subject ('a sign says', 'a lamp shines') and irregular participles that end a
              # phrase after its noun ('a cone held up by a post', 'a shadow cast onto the blinds')
              "says reads shows displays contains appears seems protrudes reflects shines glows overlooks extends stretches leans "
              "rises flows depicts features includes carries wears "
              "cut drawn held taken stuck lit cast torn beat bitten shaken spun sewn thrown blown hung strung swung known".split())
IRREGULAR = set("cut drawn held taken stuck lit cast torn beat bitten shaken spun sewn thrown blown hung strung swung known".split())
# the first word of a compound participle that tells how a thing is made ('hand blown', 'sun dried', 'spray painted')
HOW_MADE = set("hand machine home factory sun wind air pan oven spray water".split())
# makes and brands written in lower case ('a black mini cooper'): never the noun of a subject
BRANDS = set("cooper volkswagen toyota honda ford chevrolet chevy nissan subaru mazda hyundai kia bmw mercedes audi porsche ferrari "
             "lamborghini tesla dodge chrysler cadillac buick lexus acura volvo fiat vespa harley yamaha suzuki kawasaki ducati "
             "oldsmobile nike adidas reebok starbucks coca-cola pepsi ikea nintendo playstation xbox iphone ipad macbook".split())
ADJ = set("large small big tiny little huge giant tall short long wide narrow thin thick round square rectangular circular oval "
          "triangular flat old new young empty full open closed wet dry shiny dull dirty clean broken bright dark light pale deep "
          "real fake sized size medium colored coloured multi-colored multicolored colorful colourful striped spotted patterned "
          "plain simple single double several many few other another different same various some partial partially entire whole "
          "front back rear side top bottom left right upper lower middle center centre far near close distant main tan "
          "slightly very mostly fully half abstract antique vintage modern ornate artistic decorated outdoor indoor daytime "
          "nighttime overhead aerial frontal eye-level low-angle high-angle close-up top-down sized medium-sized life-sized "
          "large-sized small-sized adult baby grown cute beautiful pretty ugly fluffy furry hairy shiny glossy smooth rough "
          "soft hard heavy busy quiet calm worn faded weathered aged rustic ornamental lone lonely tall thin solid hollow "
          "transparent translucent clear opaque bare vast dense sparse curved straight wavy curly pointed pointy visible "
          "invisible noticeable apparent partly barely chrome wicker burgundy broad common semi-transparent mock punk inlaid "
          "morning evening afternoon flush murky bumpy icy midair mid-air clad suburban frenzy rusty dusty muddy sandy "
          "grassy rocky leafy snowy sunny cloudy foggy misty hazy shady woody hilly stony "
          # comparatives and superlatives ('an older red brick building'); 'lighter' is also a noun, so not here
          "older younger newer larger smaller bigger taller shorter longer wider narrower thinner thicker darker brighter "
          "deeper higher closer nearer farther further inner outer oldest youngest newest largest smallest biggest tallest "
          "shortest longest widest darkest lightest brightest highest closest nearest farthest furthest"
          .split()) | set(maps.COLOUR)
GENERIC = set("view image frame photo photograph picture shot close-up closeup rearview sideview overview scene area side top bottom "
              "front back middle center "
              "centre corner edge part portion section surface foreground background distance left right inside outside piece "
              "pieces type types kind kinds variety group pair row set bunch pile stack line number lot lots collection series "
              "assortment angle perspective level ground floor sky thing things object objects item items something camera lens "
              "shadow shadows reflection reflections light lights glare sun sunlight daytime nighttime day night sort way "
              "couple bit amount close impression mixture combination representation pattern patterns scheme schemes unit "
              "units compound course design designs arrangement composition texture shape shapes form forms style version "
              "transport word words letter letters text writing".split())
BODY = set("hand hands arm arms leg legs foot feet finger fingers head face eye eyes ear ears nose mouth neck hair shoulder "
           "shoulders knee knees toe toes paw paws tail wing wings beak fur mane horn horns body back chest belly lap palm thumb "
           "fingertips fingertip wrist elbow lips teeth tongue whiskers claw claws hoof hooves".split())
# words that make the subject a made thing ('stuffed dog', 'toy car'): kept in the name, and no living state for it
MADE = set("stuffed toy plush plastic wooden wood metal metallic stone ceramic porcelain glass paper cardboard bronze marble "
           "inflatable fake artificial miniature model cartoon carved painted rubber knitted origami decorative lego clay "
           "concrete cement iron steel brass copper tin felt fabric cloth paper-mache taxidermied".split())
TOYISH = set("stuffed toy plush inflatable fake artificial miniature model cartoon carved lego origami knitted taxidermied "
             "paper-mache figurine".split())                 # a made likeness, not a made thing: a still life
PERSON_NOUNS = {**{k: (v, None, None) for k, v in maps.GENDER.items() if " " not in k},
                "child": (None, "child", None), "children": (None, "child", None), "kid": (None, "child", None),
                "kids": (None, "child", None), "toddler": (None, "child", None), "toddlers": (None, "child", None),
                "baby": (None, "baby", None), "babies": (None, "baby", None), "teenager": (None, "teen", None),
                "teenagers": (None, "teen", None), "person": (None, None, None), "people": (None, None, None),
                "persons": (None, None, None), "adult": (None, None, None), "adults": (None, None, None)}
for _w in ("surfer", "skier", "skateboarder", "snowboarder", "athlete", "athletes", "cyclist", "cyclists", "biker", "bikers",
           "jockey", "swimmer", "swimmers", "dancer", "dancers", "musician", "musicians", "guitarist", "drummer", "soldier",
           "soldiers", "farmer", "nurse", "chef", "monk", "monks", "vendor", "vendors", "tourist", "tourists", "student",
           "students", "worker", "workers", "bride"):
    PERSON_NOUNS[_w] = (None, None, maps.lookup(_w, maps.ROLE))
PLURAL_PERSONS = {"men", "women", "boys", "girls", "guys", "ladies", "gentlemen", "children", "kids", "toddlers", "babies",
                  "teenagers", "people", "persons", "adults", "athletes", "cyclists", "bikers", "swimmers", "dancers", "musicians",
                  "soldiers", "monks", "vendors", "tourists", "students", "workers"}
# '-ing' and '-ed' words that are nouns (a parser without a lexicon would end the phrase at them)
ING_NOUNS = set("building buildings ceiling ceilings painting paintings drawing drawings railing railings clothing string strings "
                "ring rings wing wings swing swings spring springs wedding morning evening awning awnings siding stuffing "
                "frosting icing topping toppings dumpling dumplings sapling saplings seedling seedlings wiring lighting opening "
                "openings carving carvings sling bedding pudding king lining molding moulding filling fillings sign-ing "
                "landing crossing crossings sibling ceiling-fan".split())
ED_NOUNS = set("bed beds shed sheds sled sleds seed seeds weed weeds reed reeds steed".split())
COMPOUND = set("fire stop street traffic picnic park garden tree palm flower water police race school bus train door window book "
               "wine tea coffee ice cell card chess golf tennis soccer baseball basketball football swimming dining coffee "
               "bird dog cat fish teddy rocking shopping parking mail pine oak maple apple cherry rose christmas easter "
               "pumpkin snow sand rain sun sea table floor wall ceiling desk lamp power phone computer".split())
ADJ_ENDINGS = ("al", "ous", "ive", "ic", "able", "ible", "ful", "less", "ish", "ward", "wards", "ese", "ian", "ent", "ant")
NOUN_EXCEPTIONS = set("animal animals metal pedal pedals petal petals signal signals canal canals crystal crystals mural murals "
                      "festival hospital sandal sandals medal medals pedestal pedestals terminal portal capital rental pebble "
                      "table tables cable cables vegetable vegetables stable stables bible fable turntable mosaic mosaics clinic "
                      "comic comics mechanic picnic arch tunic music attic relic cleric fabric wreath bowl totem cowl jewel "
                      "elephant elephants plant plants giant giants ant ants restaurant pendant pendants faucet tent tents "
                      "cement vent vents student students parent parents agent client orient element elements instrument "
                      "instruments monument monuments ornament ornaments pavement basement garment garments segment fragment "
                      "fragments equipment apartment compartment tournament current accent percent event events comet "
                      "pheasant peasant servant infant tyrant merchant hydrant hydrants sergeant lieutenant pageant "
                      "sealant coolant variant inhabitant assistant crescent rodent rodents serpent advent cent "
                      "lantern magician musician pedestrian pedestrians guardian librarian median valerian "
                      "bowl owl fowl wheel shawl crawl spiral spirals coral corals cereal oval ovals sandal "
                      "dish fish fishes radish wish bush bushes brush brushes squash polish relish jellyfish starfish "
                      "catfish goldfish swordfish dogfish batfish porkfish crayfish shellfish leash sash ash rash cheese "
                      "geese olive olives hive beehive chive traffic garlic seagull seagulls gull gulls".split())
VERB_BASE = set("sit sits stand lie hang rest look looks appear appears seem seems show shows lean extend extends run runs stretch "
                "stretches overwaters cover covers reach reaches sat stood lay hung grow grows protrude protrudes once connect "
                "measure split solo warm dead bent classic built done consists ahead see".split())
# nouns an '-ing' word modifies inside one phrase ('drying rack', 'parking lot', 'dining table')
AFTER_ING = set("rack racks area areas pool pools lot lots table tables room rooms board boards stick sticks machine machines fan "
                "fans boat boats bag bags cart carts chair chairs pan pans sheet sheets sign signs meter meters space spaces "
                "station stations line lines mat mats glass glasses pole poles wheel wheels can cans bowl bowls cup cups bench "
                "benches shoes shoe gear net nets rod rods tackle trail trails path paths range ranges garage spot spots".split())
# relations are not read inside a depicted picture ('in the painting, a ram stands above a rod')
PICTURE_REL = re.compile(r"\b(picture|painting|photo|photograph|drawing|poster|mural|print|illustration|image of|depict\w*|"
                         r"reflection|reflected|reflecting|screen|television|tv|monitor|map|book cover|cover of)\b")
ANIMALS = set("dog dogs puppy puppies cat cats kitten kittens bird birds seagull seagulls pigeon pigeons duck ducks goose geese "
              "swan swans chicken chickens rooster hen horse horses pony cow cows bull sheep goat goats deer squirrel squirrels "
              "rabbit bunny lizard frog toad turtle tortoise fish butterfly bee bees ant ants beetle beetles spider caterpillar "
              "snail crab owl hawk eagle crow raven parrot hummingbird dragonfly moth fly ladybug worm snake mouse rat raccoon "
              "bear lion tiger elephant giraffe zebra monkey labradoodle labradoodles".split())
WILD = set("bird birds seagull seagulls pigeon pigeons duck ducks goose geese swan swans deer squirrel squirrels rabbit lizard frog "
           "toad turtle tortoise butterfly bee bees ant ants beetle beetles spider caterpillar snail crab owl hawk eagle crow "
           "raven hummingbird dragonfly moth fly ladybug worm snake raccoon bear lion tiger elephant giraffe zebra monkey".split())
FOOD = set("pizza sandwich donut donuts cake cupcake cookie cookies bread fruit fruits apple apples banana bananas orange "
           "oranges lemon lemons salad soup burger fries plate bowl meal coffee tea drink cup mug pie dessert taco tacos sushi "
           "noodles pasta rice egg eggs vegetables vegetable tomato tomatoes pepper peppers carrot carrots pumpkin pumpkins "
           "strawberry strawberries grapes".split())
PLANTS = set("tree trees flower flowers plant plants bush bushes cactus succulent succulents leaf leaves rose roses tulip tulips "
             "sunflower sunflowers palm fern ferns moss mushroom mushrooms vine vines grass weeds daisy daisies lily lilies "
             "orchid orchids blossom blossoms".split())
VEHICLES = set("car cars truck trucks bus buses train trains airplane airplanes plane planes jet boat boats ship ships bicycle "
               "bicycles bike bikes motorcycle motorcycles scooter van vans taxi tractor helicopter sailboat canoe kayak "
               "trolley tram jeep suv".split())
BUILDINGS = set("building buildings house houses church tower towers bridge skyscraper skyscrapers barn facade storefront "
                "store shop restaurant cathedral temple castle lighthouse windmill cabin hotel museum station gate archway arch "
                "pillar pillars column columns statue statues sculpture sculptures fountain monument mural".split())
# a thing's state word: kept from the subject's own adjectives, or a living state for a living subject
STATE_ADJ = {"parked": "parked", "open": "open", "opened": "open", "closed": "closed", "empty": "empty", "full": "full",
             "lit": "lit", "lit-up": "lit", "illuminated": "lit", "broken": "broken", "folded": "folded", "stacked": "stacked",
             "wet": "wet", "rusty": "rusty", "rusted": "rusty", "melted": "melted", "frozen": "frozen", "sliced": "sliced",
             "dried": "dried", "dead": "dead", "fallen": "fallen", "bare": "bare", "leafless": "leafless", "blooming": "blooming",
             "ripe": "ripe", "unripe": "unripe", "damaged": "damaged", "cracked": "cracked", "torn": "torn", "crumpled": "crumpled",
             "overturned": "upside down", "upside-down": "upside down", "abandoned": "abandoned", "unlit": "unlit"}
LIVING_STATE = {"sitting": "sitting", "sits": "sitting", "standing": "standing", "stands": "standing", "lying": "lying",
                "laying": "lying", "lies": "lying", "sleeping": "sleeping", "perched": "perched", "flying": "flying",
                "swimming": "swimming", "walking": "walking", "running": "running", "resting": "resting", "eating": "eating",
                "grazing": "grazing", "drinking": "drinking", "curled": "curled up", "crouching": "crouching",
                "jumping": "jumping"}
EXPLICIT = {"nude", "naked", "topless", "penis", "vagina", "genitals", "nipple", "nipples", "breasts", "porn", "pornographic",
            "erotic", "sex", "sexual", "sexy", "condom", "dildo", "lingerie"}

# the view phrase (the words before the first 'of' of the first sentence): framing and angle
FRAMING_VIEW = [(r"extreme(?:ly)?[ -]close[ -]?up", "extreme close"), (r"medium[ -]close[ -]?up|medium[ -]long", None),
                (r"close[ -]?up|up[ -]close|close view|close shot", "close-up"), (r"\bmedium[ -](?:shot|view)", "medium shot"),
                (r"long[ -]shot|wide[ -](?:shot|view|angle)|distant view|far view", "wide"), (r"\bmacro\b", "macro")]
ANGLE_VIEW = [(r"\btop[ -]down\b|\boverhead\b|\bbird'?s[ -]eye\b|\baerial\b|directly above|straight down", "overhead"),
              (r"\bworm'?s[ -]eye\b", "worm's eye"),
              (r"\bhigh[ -]angle|\bangled[ -]down\b|\blooking down\b|\bview down\b|\bdownward\b|\bupper[ -]angle", "high angle"),
              (r"\blow[ -]angle|\bangled[ -]up\b|\blooking up\b|\bupward\b|\bfrom below\b", "low angle"),
              (r"\beye[ -]level\b", "eye level"),
              (r"\bside[ -]view\b|\bprofile\b", "profile"), (r"\bthree[ -]quarter\b|3/4", "three quarter"),
              (r"\bfront(?:al)?[ -]view\b|\bfrontal\b", "frontal")]
TIME_WORDS = [(r"night ?time|at night|night sky|night view|night shot|night scene", "night"),    # not 'night stand', 'night heron'
              (r"\bsunset\b|\bdusk\b|\btwilight\b", "dusk"),
              (r"\bsunrise\b|\bdawn\b", "dawn"), (r"golden hour", "golden hour"), (r"blue hour", "blue hour")]
WEATHER_WORDS = [(r"\bovercast\b|cloudy sky\b|sky is (?:very |completely |fully )?cloudy|cloudy day|(?:gray|grey) sky\b|sky is "
                  r"(?:a )?(?:dull |light |dark )?(?:gray|grey)\b|sky is covered (?:in|with|by) clouds", "overcast"),
                 (r"clear (?:blue )?sky\b|sky is (?:a )?clear|cloudless|clear day|sunny day", "clear"),
                 (r"\bfoggy\b|\bfog\b|\bmisty\b|\bmist\b", "fog"), (r"\bhazy\b|\bhaze\b", "haze"),
                 (r"\braining\b|\brainy\b|raindrops|rain drops|rain is falling|falling rain", "rain"),
                 (r"\bsnowing\b|\bsnowy\b|snow[ -]covered|covered (?:in|with|by) snow|falling snow|snow on the ground|"
                  r"\bsnow\b(?! globe)", "snow"),
                 (r"\bstormy\b|storm clouds|thunderstorm", "storm")]
NOT_OVERCAST = r"partly cloudy|partially cloudy|scattered clouds|few clouds|some clouds|patches of clouds"
# fog, mist and haze are weather only in the open air ('the background is foggy', 'mist over the lake'; not 'foggy headlights',
# 'a foggy glass', 'mist coming from the fan')
OPEN_AIR = re.compile(r"\b(sky|skies|air|atmosphere|distance|distant|horizon|background|landscape|mountains?|hills?|valley|fields?|"
                      r"forest|woods|trees|city|skyline|morning|day|weather|outside|outdoors|lake|river|ocean|sea|bay|harbou?r|"
                      r"shore|coast|road|street|town|buildings|scenery|canyon|aerial|cliffs?|island|countryside|park|beach|desert|"
                      r"meadow|hillside|sunrise|sunset|dawn|dusk|clouds?)\b")
# a fog word that describes an object, not the air ('foggy headlights', 'a misty window'; 'a foggy morning' is weather)
FOGGY_THING = re.compile(r"\b(?:foggy|misty|hazy)\s+(?!(?:day|days|morning|evening|night|afternoon|dawn|dusk|sky|skies|air|weather|"
                         r"atmosphere|background|distance|horizon|mountains?|hills?|valley|fields?|forest|woods|lake|river|sea|ocean|"
                         r"bay|landscape|city|street|road|scene|scenery|light|sunrise|sunset|conditions?)\b)[a-z-]+")
# snow, fog and haze that are not weather: a likeness or a decoration ('painted white to look like snow', 'fake snow blankets')
NOT_WEATHER = re.compile(r"\b(look(?:s|ing)? like|like snow|as snow|resembl\w*|fake|artificial|faux|imitation|decorati\w*|"
                         r"ornaments?|toy|globe|cotton|machine|spray(?:ed|ing)?|smoke)\b")
LIGHT_WORDS = [(r"\bbacklit\b|back[ -]lit", "backlit"), (r"\bsilhouetted\b|in silhouette", "silhouette"),
               (r"\bdappled\b", "dappled"), (r"candle ?light|candlelit", "candle"), (r"moonlight|moonlit", "moonlight"),
               (r"(?:sun ?light|light|the sun)(?: is)? (?:coming|shining|cast|casting|pouring|streaming)(?: in)? from the left|"
                r"lit from the left", "from the left"),
               (r"(?:sun ?light|light|the sun)(?: is)? (?:coming|shining|cast|casting|pouring|streaming)(?: in)? from the right|"
                r"lit from the right", "from the right")]
FOCUS_WORDS = [(r"background is (?:very |slightly |completely |mostly )?(?:blurry|blurred|out of focus)|blurry background|"
                r"blurred background|out[ -]of[ -]focus background", "shallow"), (r"\bbokeh\b", "bokeh"),
               (r"motion blur", "motion blur")]
SETTING_SKIP = {"studio", "lab", "laboratory", "subway", "metro station", "ruins", "temple", "shrine", "workshop", "arena",
                "lighthouse", "cliffs", "cliff", "bridge", "hospital", "hospital room"}
PICTUREISH = re.compile(r"\b(picture|painting|photo|photograph|drawing|poster|mural|print|illustration|screen|reflection|reflected|"
                        r"reflecting|graphic|cartoon|depict\w*|image of|map|television|tv|monitor|postcard|calendar)\b")
REL_WORDS = {"to the left of": "left of", "to the right of": "right of", "behind": "behind", "in front of": "in front of",
             "next to": "beside", "beside": "beside", "above": "above", "below": "below", "under": "under", "underneath": "under",
             "beneath": "under", "on top of": "above", "inside of": "inside", "leaning against": "leaning on"}
_REL = "|".join(sorted((re.escape(k) for k in REL_WORDS), key=len, reverse=True))
_DET = r"(?:a|an|the|one|two|three|four|five|six|seven|eight|nine|ten|several|many|some)"
_BE = (r"(?:is|are|sits|sit|stands|stand|lies|lie|hangs|hang|rests|rest|can be seen|"
       r"(?:is|are) (?:sitting|standing|lying|laying|placed|positioned|located|hanging|resting|parked|visible|seen|mounted|leaning|"
       r"situated|set|perched|growing|floating))")
_ADV = r"(?:(?:slightly|directly|just|partially|mostly|also|immediately|far|right|somewhat|positioned|placed|located)\s+)?"
# groups: the determiner and the phrase of the relation's a, the relation words, the determiner and the rest after b
FORWARD = re.compile(rf"^(?:there (?:is|are) )?({_DET})\s+((?:[a-z][a-z'-]*\s+){{0,5}}?[a-z][a-z-]*)\s+{_BE}\s+{_ADV}({_REL})\s+"
                     rf"({_DET})\s+(.*)$")
THERE = re.compile(rf"^there (?:is|are) ({_DET})\s+((?:[a-z][a-z'-]*\s+){{0,5}}?[a-z][a-z-]*)\s+{_ADV}({_REL})\s+({_DET})\s+(.*)$")
# groups: the relation words, the determiner and the phrase of b, the determiner and the rest after a
INVERTED = re.compile(rf"^(?:directly\s+|just\s+|immediately\s+)?({_REL})\s+({_DET})\s+((?:[a-z][a-z'-]*\s+){{0,5}}?[a-z][a-z-]*)"
                      rf"\s*,?\s+(?:is|are|sits|stands|lies|hangs|rests|there is|there are)\s+({_DET})\s+(.*)$")
INDEFINITE = {"a", "an", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "several", "many", "some"}
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'-]*|\d+|[,;:()\"]")


# ------------------------------------------------------------------ noun phrases
def parse_np(tokens: list) -> dict | None:
    """The noun phrase at the start of `tokens` (original case, after the determiner): {head, name, words, colours}, or None
    when its head is not a plain lower-case noun (a name, a generic word, a body part)."""
    words, seen_noun = [], False
    for i, t in enumerate(tokens):
        lw = t.lower()
        if not t[0].isalpha() or lw in STOP and lw != "and":
            break
        if lw == "and":                                # 'white and black' inside the phrase; 'a cat and a dog' ends it
            nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
            if words and words[-1].lower() in maps.COLOUR and nxt in maps.COLOUR:
                words.append(t)
                continue
            break
        if seen_noun and lw in ("sized", "shaped", "colored", "coloured", "themed", "styled", "patterned", "inspired", "like"):
            words.append(t)                            # 'children sized tutus', 'heart shaped box': an adjective, the noun follows
            seen_noun = False
            continue
        if words and words[-1].lower() in HOW_MADE and (lw in IRREGULAR or lw.endswith("ed")):
            words.append(t)                            # 'hand blown glass mug', 'sun dried tomatoes': how it is made, the noun follows
            seen_noun = False
            continue
        noun_like = lw in ING_NOUNS or lw in ED_NOUNS
        nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
        if lw.endswith("ing") and nxt in AFTER_ING:
            noun_like = True                           # 'dish drying rack': the phrase goes on to its noun
        # a colour word is an adjective, 'red' too, though it ends in -ed
        if seen_noun and not noun_like and (lw in VERBISH or lw.endswith("ing") or
                                            (lw.endswith("ed") and lw not in MADE and lw not in maps.COLOUR)):
            break
        words.append(t)
        shade = nxt in maps.COLOUR and lw not in maps.COLOUR       # 'chalk white', 'brick red', 'sky blue': a colour's modifier
        if noun_like or (not shade and lw not in ADJ and lw not in MADE and not lw.endswith(("ed", "ing", "ly"))):
            seen_noun = True
        if len(words) >= 7:
            break
    while words and (words[-1].lower() in ADJ or words[-1].lower() == "and"):
        if words[-1].lower() in ("light", "lights") and len(words) > 1 and words[-2].lower() in COMPOUND:
            break                                      # 'a stop light', 'a street light': the light is the noun
        if words[-1].lower() in ("square", "squares") and len(words) > 1 and words[-2].lower() not in ADJ:
            break                                      # 'a white chalk square': after a noun, the square is the noun
        words.pop()
    if not words:
        return None
    head = words[-1]
    lh = head.lower()
    compound_light = lh in ("light", "lights") and len(words) > 1 and words[-2].lower() in COMPOUND
    if head != lh or not re.fullmatch(r"[a-z][a-z-]*[a-z]", lh) or (lh in GENERIC and not compound_light) or lh in BODY or \
            lh in STOP or len(lh) < 3:
        return None
    if lh in MADE or lh in VERB_BASE or lh in IRREGULAR or lh in BRANDS or \
            (lh.endswith(("ly", "ed")) and lh not in ED_NOUNS and lh not in ("fly", "butterfly", "dragonfly", "lily", "belly")):
        return None                                    # an adverb, a participle, a material, a brand or a verb is not a head noun
    if (lh.endswith("ing") and lh not in ING_NOUNS) or (lh.endswith(ADJ_ENDINGS) and lh not in NOUN_EXCEPTIONS) or \
            ("-" in lh and lh.split("-")[-1] in ADJ):
        return None                                    # 'flying', 'ellipsoidal', 'jet-black': adjectives by their form
    # a capitalized modifier is a name or a brand ('a white Harlequin cat', 'a Volkswagen car'): it is left out, the noun kept
    low = [w.lower() for w in words[:-1] if w == w.lower()] + [lh]
    mods = low[:-1]
    made = [m for m in mods if m in MADE]
    # the head noun with the word just before it when that word is a material or toy word ('stuffed dog') or a known noun of
    # a compound ('fire hydrant'); never any other word (without a lexicon 'high rise building' would give 'rise building')
    name = lh
    prev = mods[-1] if mods else ""
    if (prev in MADE or prev in COMPOUND) and len(prev) + 1 + len(lh) <= 17:
        name = f"{prev} {lh}"
    colours = []
    # a colour word that is the first noun of a compound is no colour ('a wine cork', 'a wine cellar shelf', 'a sand volleyball
    # court'), nor 'cream' after 'ice' ('an ice cream cone holder')
    cmods = list(mods)
    for i, m in enumerate(mods):
        nxt = mods[i + 1] if i + 1 < len(mods) else lh
        if m in COMPOUND and m in maps.COLOUR and nxt not in maps.COLOUR and \
                nxt not in ("and", "colored", "coloured", "toned", "tinted", "hued"):
            cmods[i] = ""
        elif m == "cream" and i > 0 and mods[i - 1] in ("ice", "whipped", "sour", "shaving", "sun"):
            cmods[i] = ""
    # a colour bound to a part ('a gray tailed squirrel', 'a red haired doll', 'a yellow-crowned heron') is not the subject's colour
    whole = re.sub(r"\b[a-z]+ (?!(?:colou?red|red)\b)[a-z]+ed\b", " ", open_colours(" ".join(m for m in cmods if m)))
    for v in maps.find(whole, maps.COLOUR):
        if v not in colours:
            colours.append(v)
    return dict(head=lh, name=name, mods=mods, made=bool(made), toy=any(m in TOYISH for m in mods), colours=colours)


COLOURED = re.compile(r"\b([a-z]+)-(?:colou?red|painted|toned|tinted)\b")
SHADE = re.compile(r"\b(light|dark)-(?=[a-z])")
TONE = re.compile(r"\b(?:medium|all|jet|pale|bright|deep)-(?=[a-z])")


def open_colours(text: str) -> str:
    """Hyphenated colour compounds that name the whole thing's colour, opened for the colour map (which reads a hyphenated word as
    one word): 'cream-colored' and 'white-painted' -> '<colour> colored', 'light-brown' -> 'light brown', 'all-black' -> 'black'."""
    return TONE.sub("", SHADE.sub(r"\1 ", COLOURED.sub(r"\1 colored", text)))


def _plural(word: str) -> bool:
    return word.endswith("s") and not word.endswith(("ss", "us", "is")) and word not in ("glass", "grass", "bus")


def _tokens(text: str) -> list:
    return _TOKEN.findall(text)


def subject_of(first: str) -> tuple:
    """-> (view words, count, noun phrase) of the view sentence: 'An overhead view of four labradoodle puppies, ...'."""
    view = ""
    first = re.sub(r"\bbod(?:y|ies) of water\b", "water", first, flags=re.I)      # 'a clear body of water' is water
    # ('a view at dusk of a tower': 'at' a time of day is not the of-word, the tower is the subject)
    # ('an indoor top-down view captures a white cat': the verb is the of-word)
    m = re.match(r"^(.{0,140}?)\b(view|views|close-up|closeup|close up|shot|image|photograph|photo|picture|up-close|look)\b"
                 r"(.{0,70}?)\b(?:of|at(?!\s+(?:dusk|dawn|night|nighttime|sunset|sunrise|twilight|noon|midday|daytime|evening|"
                 r"morning|daybreak|golden hour|blue hour)\b)|showing|captures|shows|depicts|features|displays|presents|"
                 r"showcases|reveals)\b\s*(.*)$", first, re.I | re.S)
    rest = first
    if m and not re.search(r"\b(is|are|was|were)\b", m.group(1) + m.group(3)) and \
            not re.search(r"(?<![\w-])(with|on|in|of|showing|displaying|depicting|has|having|from)(?![\w-])", m.group(1), re.I):
        # (a view word after a preposition belongs to a depicted picture: 'a monitor with an image of a tornado')
        view, rest = (m.group(1) + m.group(2) + m.group(3)).lower(), m.group(4)
        vantage = re.search(r"\b(?:from|across|over|through|past|between|behind|beyond|along|into)\b", m.group(3))
        k = None if vantage else re.search(r"\b(?:a|an)\s", m.group(3))
        if k:                                          # 'a view looking up at a pillar ... of concrete': the subject is the pillar
            # ('a side view from a grassy hill of a cliff': the cliff, the hill is where the camera stands)
            view, rest = (m.group(1) + m.group(2) + m.group(3)[:k.start()]).lower(), m.group(3)[k.start():] + " of " + m.group(4)
    rest = re.sub(r"^(?:the\s+)?(?:very\s+)?(?:(?:front|back|rear|top|bottom|left|right|far|upper|lower|outer|inner|near)\s+)?"
                  r"(?:side|end|edge|corner|part|portion|section|half|face|surface|top|bottom|front|back|rear|base|tip|middle|"
                  r"center|centre|interior|exterior|inside|underside|backside)\s+of\s+", "", rest, flags=re.I)
    count, np = counted_np(_tokens(rest))
    return view, count, np


def counted_np(toks: list, det: str | None = None) -> tuple:
    """-> (count, noun phrase) of tokens that start with a determiner (or after `det`, already read), through a quantity
    phrase: 'a group of three ducks', 'a pair of shoes', 'a large number of ants', 'a patch of grass' (no count)."""
    count = NUMBERS.get(det.lower()) if det else None
    if det is None and toks and toks[0].lower() in NUMBERS:
        count = NUMBERS[toks[0].lower()]
        toks = toks[1:]
    elif det is None and toks and toks[0].lower() == "the":
        toks = toks[1:]
    j = 0
    while j < len(toks) and toks[j].lower() in ADJ:
        j += 1
    if j + 1 < len(toks) and toks[j].lower() in QUANTITY and toks[j + 1].lower() == "of":
        count = QUANTITY[toks[j].lower()]
        if toks[j].lower() == "number" and any(t.lower() in ("large", "huge", "big") for t in toks[:j]):
            count = "many"
        toks = toks[j + 2:]
        if toks and toks[0].lower() in NUMBERS and toks[0].lower() not in ("a", "an"):
            count = NUMBERS[toks[0].lower()]
            toks = toks[1:]
        elif toks and toks[0].lower() in ("the", "a", "an"):
            toks = toks[1:]
    np = parse_np(toks)
    if np is not None and count is None and _plural(np["head"]) and (det or "").lower() != "the":
        count = "several"
    return count, np


def _first(patterns, text: str):
    for pat, v in patterns:
        if re.search(pat, text):
            return v
    return False                                        # no phrase at all (None stays 'a phrase that maps to nothing')


def _one(patterns, texts) -> str | None:
    """The one value the patterns give across `texts` (two different values: none)."""
    vals = set()
    for t in texts:
        for pat, v in patterns:
            if re.search(pat, t):
                vals.add(v)
    vals.discard(None)
    return vals.pop() if len(vals) == 1 else None


def weather_of(texts) -> str | None:
    """The one weather the sentences state: fog and haze only in the open air (OPEN_AIR), never of an object ('foggy
    headlights', 'a misty window': FOGGY_THING), and no snow, fog or haze of a likeness or a decoration (NOT_WEATHER); two
    different weathers: none."""
    vals = set()
    for t in texts:
        t = FOGGY_THING.sub(" ", t)
        for pat, v in WEATHER_WORDS:
            if not re.search(pat, t):
                continue
            if v in ("fog", "haze") and not OPEN_AIR.search(t):
                continue
            if v in ("snow", "fog", "haze") and NOT_WEATHER.search(t):
                continue
            vals.add(v)
    return vals.pop() if len(vals) == 1 else None


# ------------------------------------------------------------------ the description -> the spec
def sentences_of(description: str) -> list:
    """The description's sentences (not split after 'St.', 'Mr.', 'Mt.' or an initial: 'Jackson Square in St. Louis.' is one)."""
    return [s.strip() for s in core.sentences(core.ascii_text(description)) if s.strip()]


def _end(np: dict | None, thing: dict | None) -> str | None:
    if np is None:
        return None
    if thing is not None and np["head"] == thing["head"]:
        return thing["name"]
    return np["name"] if len(np["name"]) <= 20 else np["head"]


def relations_of(sents: list, thing: dict | None) -> list:
    """(a, rel, b) of the anchored sentence forms, in text order."""
    out = []
    for s in sents:
        if '"' in s or PICTURE_REL.search(s.lower()):
            continue
        body = s.rstrip(".!?")
        low = body[0].lower() + body[1:] if body else body
        for clause in re.split(r"[;]|, (?:and|while|with) ", low):
            clause = clause.strip()
            m = FORWARD.match(clause) or THERE.match(clause)
            if m:
                da, rel, db = m.group(1), REL_WORDS[m.group(3)], m.group(4)
                a, b = counted_np(_tokens(m.group(2)), da)[1], counted_np(_tokens(m.group(5)), db)[1]
            else:
                m = INVERTED.match(clause)
                if not m:
                    continue
                rel, db, da = REL_WORDS[m.group(1)], m.group(2), m.group(4)
                b, a = counted_np(_tokens(m.group(3)), db)[1], counted_np(_tokens(m.group(5)), da)[1]
            if thing is not None and any(x is not None and x["head"] == thing["head"] and d in INDEFINITE
                                         for x, d in ((a, da), (b, db))):
                continue                               # 'a small building' beside the main building: another one of its name
            na, nb = _end(a, thing), _end(b, thing)
            if na and nb and na != nb:
                out.append((na, rel, nb))
    return out


def _person(s: core.Spec, sents: list, count, np: dict) -> None:
    """The person system of a view sentence whose subject is a person ('A medium view of a young girl in a red dress ...'):
    count, gender, age and role from the phrase; wear and pose (one person only) from the sentences about 'the <noun>' / he /
    she. A person named anywhere else is left to the hint (shadows, posters, the photographer: too easily not in view)."""
    noun = np["head"]
    gender, age, role = PERSON_NOUNS[noun]
    s.set("person", "count", count or ("several" if noun in PLURAL_PERSONS else "1"))
    if gender:
        s.set("person", "gender", gender)
    ages = set(maps.find(" ".join(np["mods"][-1:] + [noun]), maps.AGE)) | ({age} if age else set())
    if len(ages) == 1:
        s.set("person", "age", ages.pop())
    if role:
        s.set("person", "role", role)
    if (count or "1") != "1":
        return
    own = [t.lower() for t in sents if re.search(rf"\b{noun}\b|\b(he|she)\b", t.lower()) and '"' not in t]
    wear = [m.group(1) for t in own for m in re.finditer(r"\b(?:wearing|dressed in)\b([^.;]*)", t)]
    clothes = [v for w in wear for v in maps.find(w, maps.CLOTHING)]
    if clothes:
        s.set("wear", "clothing", clothes[0])
        words = "|".join(sorted((k for k, v in maps.CLOTHING.items() if v == clothes[0]), key=len, reverse=True))
        for w in wear:
            m = re.search(rf"((?:[a-z-]+\s+){{0,3}})({words})\b", w)
            if m:
                cs = {c for c in maps.find(open_colours(m.group(1)), maps.COLOUR) if c not in maps.HAIR_COLOUR_ONLY}
                if len(cs) == 1:
                    s.set("wear", "colour", cs.pop())
                break
    accs = [v for w in wear for v in maps.find(w, maps.ACCESSORY)]
    if accs:
        s.set("wear", "accessory", accs[0])
    poses = set()
    for t in own:
        for m in re.finditer(rf"\b(?:{noun}|he|she)\s+(?:is\s+|appears to be\s+)?([a-z]+)", t):
            if m.group(1) in maps.POSE:
                poses.add(maps.POSE[m.group(1)])
    if len(poses) == 1:
        s.set("body", "pose", poses.pop())


# a person word in a view sentence that names a likeness, not a person ('two large nutcracker soldiers', 'a cutout of a person')
NOT_A_PERSON = re.compile(r"\b(shadows?|silhouettes?|reflections?|statues?|sculptures?|sculpted|graffiti|murals?|toys?|dolls?|"
                          r"figurines?|mannequins?|nutcrackers?|cutouts?|cut-outs?|scarecrows?|effig(?:y|ies)|puppets?|robots?|"
                          r"action figures?)\b")
# where a sentence places its subject: a placement phrase of the frame ('on the left side of the image', 'in the center of the
# frame'); 'to' or 'towards' the left is a direction, not a place
PLACE = re.compile(r"(?:on|in|at)\s+the\s+(?:very\s+|far\s+)?(?:(?:bottom|top|lower|upper)\s+)?(left|right)(?:\s+(?:hand\s+)?"
                   r"(?:side|half|portion|part|corner|edge|third))?\s+of\s+the\s+(?:image|frame|photo|picture|photograph|shot)\b|"
                   r"(?:in|at)\s+the\s+(?:very\s+)?(?:center|centre|middle)\s+of\s+the\s+(?:image|frame|photo|picture|photograph|"
                   r"shot)\b")
# a sentence of a direction or a motion places nothing ('the head pointing towards the lower left corner', 'facing the left side')
MOTION = re.compile(r"\b(?:fac(?:e|es|ed|ing)|point(?:s|ed|ing)?|look(?:s|ed|ing)|swim\w*|driv\w*|extend\w*|curv\w*|span\w*|"
                    r"mov(?:e|es|ed|ing)|head(?:s|ed|ing)|fl(?:y|ies|ying)|walk\w*|run(?:s|ning)?|lean\w*|turn\w*|orient\w*|angled|"
                    r"stretch\w*|reach\w*|lead(?:s|ing)|go(?:es|ing)|travel\w*|toward|towards)\b")
_PLACE_VERB = (r"(?:is|are|sits|sit|stands|stand|lies|lie|rests|rest|hangs|hang|appears|appear|can be seen|"
               r"(?:is|are)\s+(?:sitting|standing|lying|laying|resting|hanging|placed|positioned|located|situated|set|parked|perched|"
               r"mounted|visible|seen|shown|found|centered|centred|growing|floating|hovering))")
_PLACE_ADV = r"(?:(?:slightly|mostly|directly|just|partially|partly|almost|nearly|also|primarily|mainly|placed|positioned|located)\s+)*"
_VIEW_GAP = (r"(?:(?:that|which)\s+)?(?:(?:is|are|sitting|standing|lying|laying|resting|sleeping|perched|parked|placed|positioned|"
             r"located|seen|visible|shown|hanging|mounted|set|situated|centered|centred|growing|floating|hovering)\s+){0,3}")


def placed(tl: str, np: dict, first: bool) -> str | None:
    """left / right / centre when a (lower-case) sentence places the thing itself in the frame: a clause with the thing as its
    plain subject and the placement right after its verb ('The red star is on the left side of the image'; only the thing's own
    modifiers between the article and the noun) or, in the view sentence, the placement right after its noun ('a dog lying on the
    left side of the frame'). A direction or a motion between the noun and the placement places nothing ('the head pointing towards
    the lower left corner'), nor does a placement of another noun ('with the edges of the mat visible on the left side')."""
    h = re.escape(np["head"])
    spans = []                                         # (the text from the noun through the placement, the placement)
    if first:
        for m in re.finditer(rf"\b{h}\s+{_VIEW_GAP}", tl):
            p = PLACE.match(tl, m.end())
            if p:
                spans.append((tl[m.start():p.end()], p))
    else:
        for clause in re.split(r"[;,]\s*", tl):
            clause = re.sub(r"^(?:and|while|but|so|as)\s+", "", clause.strip())
            m = re.match(rf"^(?:the|this|these|that)\s+((?:[a-z-]+\s+){{0,3}}?){h}\s+{_PLACE_VERB}\s+{_PLACE_ADV}", clause)
            if not m or any(w not in ADJ and w not in MADE and w not in np["mods"] and w not in STATE_ADJ
                            for w in m.group(1).split()):
                continue                               # 'the rug the puppies are on': another noun is the subject
            p = PLACE.match(clause, m.end())
            if p:
                spans.append((clause[:p.end()], p))
    found = {"left": "left", "right": "right"}
    vals = {found.get(p.group(1), "centre") for span, p in spans if not MOTION.search(span)}
    return vals.pop() if len(vals) == 1 else None


def said_again(head: str, text: str) -> bool:
    """The description introduces the subject's noun more than once ('a black and white cat and a dark gray cat', 'another cat',
    'two cats', 'both cats'): its count is then not one, and the number is left unknown."""
    h, t = re.escape(head), text.lower()
    intros = re.findall(rf"\b(?:a|an)\s+(?:[a-z-]+\s+){{0,3}}{h}\b(?!['’]s)", t)
    return (len(intros) >= 2 or re.search(rf"\banother\s+(?:[a-z-]+\s+){{0,2}}{h}\b", t) is not None
            or re.search(rf"\b(?:two|three|four|five|six|both|several|many|multiple)\s+(?:[a-z-]+\s+){{0,2}}{h}(?:s|es)?\b", t)
            is not None)


def spec_of(description: str, vocab: set | None = None) -> tuple:
    """-> (core.Spec, genre, hint) for one DOCCI description, or (None, reason, '') when it is skipped. `vocab`: the plain words
    of the descriptions (core.corpus_vocab of the whole file, as seeds passes it; by default those of this description)."""
    sents = sentences_of(description)
    if not sents:
        return None, "empty", ""
    words = set(re.findall(r"[a-z]+", " ".join(sents).lower()))
    if words & EXPLICIT:
        return None, "explicit word", ""
    s = core.Spec()
    first = sents[0]
    view, count, np = subject_of(first)
    plain = [t.lower() for t in sents if not PICTUREISH.search(t.lower()) and '"' not in t]     # scene facts: no pictures, signs
    # ---- the person system: only when the view sentence's subject is a person, in a sentence of no picture, shadow or likeness
    # ('a white stone man', 'two nutcracker soldiers', 'a cutout of a person': no person)
    person_subject = np is not None and np["head"] in PERSON_NOUNS
    if person_subject and not np["made"] and not np["toy"] and not PICTUREISH.search(first.lower()) and \
            not NOT_A_PERSON.search(first.lower()):
        _person(s, sents, count, np)
        # the thing the person holds in the view sentence ('a man holding a red umbrella')
        m = re.search(rf"\b{re.escape(np['head'])}\b[^.;]*?\b(?:holding|carrying)\s+(a|an|one|two|three)\s+(.*)$", first, re.I)
        held_np = parse_np(_tokens(m.group(2))) if m else None
        if held_np is not None and held_np["head"] not in PERSON_NOUNS and s.set("thing", "name", held_np["name"]):
            s.set("thing", "count", NUMBERS[m.group(1).lower()])
            if len(held_np["colours"]) == 1 and held_np["colours"][0] not in maps.HAIR_COLOUR_ONLY:
                s.set("thing", "colour", held_np["colours"][0])
            s.relate(s.d["person"].get("gender") or np["head"], "holding", held_np["name"])
    # ---- the thing: the view sentence's subject when it is not a person
    thing = None
    if np is not None and not person_subject and s.set("thing", "name", np["name"]):       # (a name over budget: no thing)
        thing = np
        if count and not (count == "1" and said_again(np["head"], " ".join(sents))):
            s.set("thing", "count", count)
        if len(np["colours"]) == 1 and np["colours"][0] not in maps.HAIR_COLOUR_ONLY:
            s.set("thing", "colour", np["colours"][0])
        states = [STATE_ADJ[w] for w in np["mods"] if w in STATE_ADJ]
        living = np["head"] in ANIMALS and not np["made"]
        if not states and living and count in (None, "1"):
            after = re.search(rf"\b{re.escape(np['head'])}\b\s+(?:that is\s+|is\s+)?([a-z]+)", first.lower())
            if after and after.group(1) in LIVING_STATE:
                states.append(LIVING_STATE[after.group(1)])
            else:
                for t in sents[1:]:
                    m = re.match(rf"^the {re.escape(np['head'])} (?:is|appears to be) (?:\w+ly )?([a-z]+)", t.lower())
                    if m and m.group(1) in LIVING_STATE:
                        states.append(LIVING_STATE[m.group(1)])
                        break
        if len(set(states)) == 1:
            s.set("thing", "state", states[0])
        # position: a sentence that places the thing itself in the frame (placed)
        places = {p for p in (placed(t.lower(), np, t is first) for t in sents) if p}
        if len(places) == 1:
            s.set("thing", "position", places.pop())
    # ---- the shot: the view phrase's framing and angle; light and focus words
    if view:
        fr = _first(FRAMING_VIEW, view)
        if fr:
            s.set("shot", "framing", fr)
        elev = _first(ANGLE_VIEW[:5], view)
        ang = elev if elev else _first(ANGLE_VIEW[5:], view)
        if ang:
            s.set("shot", "angle", ang)
    light = _one(LIGHT_WORDS, plain)
    if light:
        s.set("shot", "light", light)
    focus = _one(FOCUS_WORDS, [t.lower() for t in sents])
    if focus:
        s.set("shot", "focus", focus)
    # ---- the scene: time, weather and a setting named as the place ('on a beach', 'in a kitchen')
    tm = _one(TIME_WORDS, plain + [view])
    if tm:
        s.set("scene", "time", tm)
    wx = weather_of([re.sub(NOT_OVERCAST, " ", t) for t in plain])
    if wx:
        s.set("scene", "weather", wx)
    keys = "|".join(sorted((re.escape(k) for k in maps.SETTING if k not in SETTING_SKIP), key=len, reverse=True))
    found = set()
    for t in plain:
        for m in re.finditer(rf"\b(?:in|on|at|inside)\s+(?:a|an|the)\s+(?:[a-z-]+\s+){{0,2}}?({keys})\b(?!\s+(?:table|chair|"
                             rf"bench|hose|tool|sign|wall|fence|path|gnome|statue|bed|plant|pot|shed|ball|umbrella|towel|sink|"
                             rf"counter|cabinet|floor|stool|door|window))", t):
            found.add(maps.SETTING[m.group(1)])
    if len(found) == 1:
        s.set("scene", "setting", found.pop())
    if not re.search(r"\bscreen ?shot\b", " ".join(sents).lower()):
        s.set("form", "medium", "photograph")          # (a screenshot is not a photograph)
    # ---- relations: the thing's first, at most six
    rels = relations_of(sents, thing)
    if thing is not None:
        rels.sort(key=lambda r: thing["name"] not in (r[0], r[2]))
    seen = set()
    for a, rel, b in rels:
        pair = frozenset((a, b))
        if pair in seen:
            continue
        if s.relate(a, rel, b):
            seen.add(pair)
        if len(s.rels) >= core.MAX_RELATIONS:
            break
    # ---- the hint: the description without quoted or upper-case text, without its image talk ('the image shows'), then without
    # every sentence that may hold a name (core.drop_named_strict: a capitalized first word that is not a plain word of the
    # descriptions, 'Einstein's left arm ...', is a name too)
    keep = [t for t in sents if '"' not in t and not re.search(r"\b[A-Z]{2,}\b", t)]
    text = core.drop_named_strict(core.without_image_talk(" ".join(keep)),
                                  vocab if vocab is not None else core.corpus_vocab([description])) if keep else ""
    hint = core.make_hint(core.sentences(text)) if text else ""
    return s, _genre(thing, person_subject, sents), hint


def _genre(thing, person_subject, sents) -> str:
    low = " ".join(sents).lower()
    if person_subject:
        return "street" if re.search(r"\b(street|sidewalk|road|crosswalk)\b", low) else "documentary"
    if thing is None:
        return "landscape" if re.search(r"\b(sky|mountain|mountains|hill|hills|field|lake|ocean|horizon)\b", low) else "still life"
    h = thing["head"]
    if thing["toy"] or h in ("statue", "statues", "sculpture", "sculptures", "figurine", "figurines", "toy", "toys"):
        return "still life"
    if h in WILD:
        return "wildlife"
    if h in ANIMALS:
        return "animal"
    if h in FOOD:
        return "food"
    if h in PLANTS:
        return "botanical"
    if h in VEHICLES:
        return "transport"
    if h in BUILDINGS:
        return "architecture"
    if re.search(r"\b(indoor|indoors|inside|room|table|shelf|counter|desk)\b", low):
        return "still life"
    return "documentary"


# ------------------------------------------------------------------ seeds
def rows(raw_dir: str):
    with open(os.path.join(raw_dir, DATASET, FILE), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def seeds(raw_dir: str, limit: int | None = None):
    """Seeds of the 14,847 descriptions in file order (qual_dev, qual_test, test, train as the file holds them); `limit`: at most
    that many (None: all, 0: none). The plain words of all the descriptions are read first, for the name filter of the hints."""
    STATS.clear()
    if limit is not None and limit <= 0:
        return
    vocab = core.corpus_vocab(row.get("description", "") for row in rows(raw_dir))
    n = 0
    for row in rows(raw_dir):
        STATS["rows"] += 1
        spec, genre, hint = spec_of(row.get("description", ""), vocab)
        if spec is None:
            STATS[f"skip: {genre}"] += 1
            continue
        for k, v in spec.dropped.items():
            STATS[f"dropped {k}"] += v
        sid = str(row["example_id"])
        # (a training seed loses a sealed thing name with its whole thing system: core.strip_sealed)
        seed = core.make_seed(DATASET, sid, DOMAIN, genre, spec, hint, LICENSE, URL, min_records=MIN_RECORDS)
        if seed is None:
            STATS["skip: rejected by make_seed"] += 1      # (the reason is counted in core.REJECTED)
            continue
        STATS["seeds"] += 1
        yield seed
        n += 1
        if limit is not None and n >= limit:
            return
