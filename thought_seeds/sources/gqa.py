"""thought_seeds.sources.gqa - GQA scene graphs (train + val, over Visual Genome images) -> hidden picture specs.

Per image: the person objects (man, woman, skier, people ...) are merged by box overlap into persons; the largest person is the main
one and fills the person system (count, gender when every gendered person agrees or the main one is clearly larger, age, role), its
pose and gesture (attributes and 'sitting on' / 'standing in' style predicates), its look (a smile or an open mouth, the hair style of
a hair object linked to it) and its wear (clothing and accessory from 'wearing' / 'has' / 'on' links, one hop through a body part, or
a garment box held by one person only; the wear colour is the colour of the listed garment, or of the dominant garment when no
listed one is worn). The most salient non-person object (largest box with a bonus for its annotated relations; never a body part,
a garment, a word or the backdrop unless nothing else is there) fills the thing system (name, count of that name, its one colour, a
state word, its position from the box centre). Up to six relations through maps.RELATION and a table of GQA's compound predicates
('standing next to' -> beside), preferring the ones that touch the main person or the thing. The scene: a setting word among the
object names (beach, kitchen, harbor ...), the weather from the graph's weather field or the sky's attributes, snow on the ground.
No text: GQA has none (the Visual Genome region file was not joined, see TAKEN). Only the scene-graph zip is read: no image is
downloaded, used or redistributed."""
from __future__ import annotations

import io
import json
import os
import zipfile
from collections import Counter, defaultdict

from .. import core, maps

DATASET = "gqa"
LICENSE = "CC BY 4.0"
URL = "https://cs.stanford.edu/people/dorarad/gqa/download.html"
ATTRIBUTION = ("GQA scene graphs v1.1 (Hudson and Manning, Stanford University, 2019), built on Visual Genome (Krishna et al. 2017), "
               "CC BY 4.0; annotations only, no image used or redistributed")
CITATION = r"""@inproceedings{hudson2019gqa,
  title     = {{GQA}: A New Dataset for Real-World Visual Reasoning and Compositional Question Answering},
  author    = {Hudson, Drew A. and Manning, Christopher D.},
  booktitle = {Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR)},
  pages     = {6700--6709},
  year      = {2019}
}

@article{krishna2017visual,
  title   = {Visual Genome: Connecting Language and Vision Using Crowdsourced Dense Image Annotations},
  author  = {Krishna, Ranjay and Zhu, Yuke and Groth, Oliver and Johnson, Justin and Hata, Kenji and Kravitz, Joshua and Chen, Stephanie and Kalantidis, Yannis and Li, Li-Jia and Shamma, David A. and Bernstein, Michael S. and Fei-Fei, Li},
  journal = {International Journal of Computer Vision},
  volume  = {123},
  number  = {1},
  pages   = {32--73},
  year    = {2017},
  doi     = {10.1007/s11263-016-0981-7}
}"""
TAKEN = ("records only: object names, attributes, boxes and relations of the train + val scene graphs and the graph weather field "
         "(person, look, wear, body, scene, thing, relations; form medium photograph); no hint (GQA has no free text; the Visual "
         "Genome region descriptions were not joined)")
MODIFIED = ("modified by this dataset: annotations extracted from the scene graphs and mapped to the dataset's closed lists; no text "
            "taken")

ZIP = "sceneGraphs.zip"
ZIP_URL = "https://downloads.cs.stanford.edu/nlp/data/gqa/sceneGraphs.zip"
ZIP_BYTES = 44824862
MEMBERS = ("train_sceneGraphs.json", "val_sceneGraphs.json")
DOMAIN = "photograph"
MIN_RECORDS = 3

STATS: Counter = Counter()          # the last seeds() run: images seen, seeds, the drop reasons


# ------------------------------------------------------------------ download
def fetch(raw_dir: str) -> dict:
    """The scene-graph zip (42.7 MB: train + val graphs, annotations only) into raw_dir/gqa/; skipped when present at its size."""
    d = os.path.join(raw_dir, DATASET)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, ZIP)
    if not (os.path.exists(path) and os.path.getsize(path) == ZIP_BYTES):
        import requests
        tmp = path + ".part"
        with requests.get(ZIP_URL, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as fh:
                for b in r.iter_content(1 << 20):
                    fh.write(b)
        os.replace(tmp, path)
    return {ZIP: os.path.getsize(path)}


# ------------------------------------------------------------------ a streamed top-level JSON object (the train file is 317 MB)
def iter_object(fh, chunk: int = 1 << 22):
    """(key, value) pairs of a top-level JSON object read from a text stream piece by piece (one graph in memory at a time)."""
    dec = json.JSONDecoder()
    buf, pos, eof = "", 0, False

    def more():                                        # appends only: an index taken before a read stays valid
        nonlocal buf, eof
        piece = fh.read(chunk)
        if not piece:
            eof = True
        buf += piece

    def skip(chars=" \t\r\n"):
        nonlocal pos
        while True:
            while pos < len(buf) and buf[pos] in chars:
                pos += 1
            if pos < len(buf) or eof:
                return
            more()

    skip()
    if pos >= len(buf) or buf[pos] != "{":
        raise ValueError("not a JSON object")
    pos += 1
    while True:
        skip(" \t\r\n,")
        if pos >= len(buf):
            raise ValueError("the object ends early")
        if buf[pos] == "}":
            return
        if pos > chunk:
            buf, pos = buf[pos:], 0                    # drop what was read (the only place the buffer is cut)
        start = pos
        while True:
            try:
                key, end = dec.raw_decode(buf, pos)
                pos = end
                skip()
                if pos >= len(buf) or buf[pos] != ":":
                    raise json.JSONDecodeError("colon", buf, pos)
                pos += 1
                skip()
                value, end = dec.raw_decode(buf, pos)
                pos = end
                break
            except json.JSONDecodeError:
                if eof:
                    raise
                pos = start                            # read more and parse the item again
                more()
        yield key, value


def iter_graphs(zip_path: str, members=MEMBERS):
    with zipfile.ZipFile(zip_path) as z:
        for m in members:
            with z.open(m) as raw:
                yield from iter_object(io.TextIOWrapper(raw, encoding="utf-8"))


# ------------------------------------------------------------------ the word tables of GQA's names
# name -> (gender, age, role, plural): plural None = one person, "group" = two or more, "many" = a crowd, "two" = a couple
PERSON: dict = {}


def _person(names: str, gender=None, age=None, role=None, plural=None):
    for n in names.split(","):
        PERSON[n.strip()] = (gender, age, role, plural)


_person("man,guy,gentleman,male,policeman,businessman,fisherman,cowboy,groom", "man")
_person("men,guys,gentlemen,policemen", "man", plural="group")
_person("woman,lady,female,businesswoman,policewoman,waitress", "woman")
_person("women,ladies", "woman", plural="group")
_person("boy", "boy")
_person("boys", "boy", plural="group")
_person("girl", "girl")
_person("girls", "girl", plural="group")
_person("child,kid,toddler", age="child")
_person("children,kids,toddlers", age="child", plural="group")
_person("baby,infant", age="baby")
_person("babies", age="baby", plural="group")
_person("teenager,teen", age="teen")
_person("teenagers,teens", age="teen", plural="group")
_person("person,human,adult,individual,pedestrian,passenger,customer,shopper,spectator,driver,bus driver,pilot,umpire,referee,"
        "coach,officer,police officer,waiter,parent,lifeguard,hiker")
_person("people,persons,adults,pedestrians,passengers,customers,shoppers,family,team,officers,parents,hikers", plural="group")
_person("crowd,audience,spectators", plural="many")
_person("couple", plural="two")
_person("player,tennis player,baseball player,soccer player,football player,skier,surfer,skateboarder,snowboarder,skater,athlete,"
        "runner,batter,pitcher,catcher", role="athlete")
_person("players,baseball players,tennis players,skiers,surfers,skateboarders,snowboarders,skaters,athletes,runners", role="athlete",
        plural="group")
_person("swimmer", role="swimmer")
_person("swimmers", role="swimmer", plural="group")
_person("biker,cyclist,rider,motorcyclist,jockey,horseback rider", role="rider")
_person("bikers,cyclists,riders,motorcyclists", role="rider", plural="group")
_person("chef,cook", role="chef")
_person("chefs,cooks", role="chef", plural="group")
_person("worker,construction worker", role="worker")
_person("workers,construction workers", role="worker", plural="group")
_person("soldier", role="soldier")
_person("soldiers", role="soldier", plural="group")
_person("farmer", role="farmer")
_person("vendor,seller,merchant", role="vendor")
_person("vendors", role="vendor", plural="group")
_person("tourist,traveler,traveller", role="traveller")
_person("tourists,travelers,travellers", role="traveller", plural="group")
_person("student", role="student")
_person("students", role="student", plural="group")
_person("nurse", role="nurse")
_person("guard,security guard", role="guard")
_person("monk", role="monk")
_person("dancer", role="dancer")
_person("musician,guitarist,drummer,violinist", role="musician")
_person("painter", role="painter")
_person("mother,mom", "woman", role="mother")
_person("father,dad", "man", role="father")
_person("bride", "woman", role="bride")
# names that are a person only in their context: a pitcher of water, cake batter
BASEBALL = {"baseball", "bat", "baseball bat", "home plate", "mound", "dugout", "umpire", "catcher", "batter", "pitcher", "baseball player",
            "baseball players", "baseball glove", "mitt", "batting helmet", "baseball field", "baseball uniform"}
CONTEXT = {"pitcher": BASEBALL, "batter": BASEBALL, "catcher": BASEBALL}

BODY = set("head,hand,hands,hair,leg,legs,ear,ears,eye,eyes,nose,arm,arms,face,foot,feet,mouth,neck,finger,fingers,wrist,wrists,"
           "shoulder,shoulders,knee,knees,beard,mustache,moustache,teeth,tooth,lip,lips,chin,cheek,cheeks,forehead,eyebrow,eyebrows,"
           "thumb,elbow,elbows,body,skin,tail,paw,paws,mane,fur,horn,horns,beak,wing,wings,hoof,hooves,spots,stripes,whiskers,snout,"
           "belly,toe,toes,ankle,ankles,waist,hip,hips,chest,stomach,fist,nails,fingernail,fingernails,claws,claw,feathers,feather,"
           "antler,antlers,tusk,tusks,tongue,back,muzzle,nostril,nostrils,eyelashes,eyelash,lap,palm,calf,thigh,thighs,heel,"
           "tattoo,mohawk".split(","))
HAIR_PART = {"ponytail": "ponytail", "pony tail": "ponytail", "braid": "braided", "braids": "braided", "bangs": "bangs",
             "afro": "afro", "pigtails": "pigtails", "dreadlocks": "locs", "dreads": "locs"}
TEXTISH = set("letter,letters,number,numbers,word,words,writing,text,logo,label,sticker,design,pattern,stripe,line,lines,spot,shadow,"
              "shadows,reflection,part,edge,side,top,bottom,front,corner,background,area,section,surface,air,distance,daytime,photo,"
              "frame,name,graffiti,print,character,characters,symbol,trim,border,hole,crack,cracks,light,lights,sunlight,glare,"
              "shade,game,scene,view,day,night,image,photograph,event,match,place,thing,things,stuff,object,objects,item,items,"
              "piece,pieces,group,bunch,pile,row,set,lot,kind,type,color,colour,structure,display,paint".split(","))
# parts of a larger object: never the thing, never a relation end ('tire below truck', 'frosting' for a cake)
PARTS = set("frosting,icing,crust,topping,toppings,wheel,wheels,tire,tires,windshield,handle,handles,knob,knobs,lid,headlight,"
            "headlights,bumper,license plate,screen,stem,stems,petal,petals,string,propeller,cockpit,tail light,taillight,"
            "tail lights,door handle,spokes,pedal,pedals,kickstand,hubcap,rim,grill,antenna,cord,seat,cushion,base,leg,legs,"
            "drawer,drawers,shelf,key,keys,blade,blades,nozzle,spout,cap,brim,sole,laces,shoelace,strap,straps,zipper,buckle,"
            "button,buttons,pocket,collar,sleeve,sleeves,mane,tail,trunk,tusk,tusks".split(","))
# objects that hold the subject (a plate under the food, a table under the plate): their share counts for less
SUPPORT = set("table,desk,tray,plate,plates,platter,dish,dishes,cutting board,board,napkin,placemat,tablecloth,table cloth,mat,paper,"
              "pan,countertop,counter top,dining table,coffee table,cloth,bowl,box,container,basket".split(","))
BACKDROP = set("sky,ground,grass,floor,wall,walls,ceiling,road,street,sidewalk,pavement,field,water,ocean,sea,lake,river,snow,sand,dirt,"
               "gravel,mud,hill,hills,mountain,mountains,cloud,clouds,tree,trees,bush,bushes,leaves,leaf,branch,branches,building,"
               "buildings,fence,window,windows,roof,rock,rocks,stone,stones,plants,weeds,shrub,shrubs,forest,woods,beach,shore,track,"
               "tracks,rail,rails,railing,pole,poles,post,posts,wire,wires,cord,cords,power lines,power line,tree trunk,trunk,trunks,"
               "hillside,mountain range,waves,wave,dust,smoke,steam,fog,rain,tile,tiles,brick,bricks,carpet,rug,curtain,curtains,"
               "door,doors,doorway,house,houses,tower,cabinet,cabinets,shelf,shelves,counter,countertop,platform,crosswalk,"
               "lawn,yard,park,city,town,parking lot,highway,runway,tarmac,court,tennis court,baseball field,home plate,dirt road,path,"
               "trail,walkway,hedge,hedges,vegetation,foliage,moss,sun,moon,stars,horizon,skyline,surf,ripples,puddle,stairs,steps,"
               "staircase,balcony,pillar,pillars,column,columns,arch,archway,bridge,dock,pier,station,airport,train station,bathroom,"
               "room,kitchen,living room,bedroom,office,store,shop,restaurant,market".split(","))
GROUND_ONLY = {"sky", "ground", "floor", "ceiling", "wall", "walls", "grass", "road", "street", "sidewalk", "pavement", "dirt", "sand",
               "water", "snow", "field", "gravel", "mud", "lawn", "yard", "court", "tennis court", "baseball field", "room",
               "kitchen", "bathroom", "bedroom", "living room", "office", "store", "shop", "restaurant", "market", "station",
               "airport", "train station", "park", "city", "town", "parking lot", "highway", "runway", "tarmac", "path", "trail",
               "walkway", "crosswalk", "dirt road", "horizon", "skyline", "distance", "background", "tiles", "tile", "bricks",
               "brick", "wallpaper", "paint", "cloud", "clouds", "smoke", "steam", "fog"}
GARMENTS = set("shirt,t-shirt,tshirt,tee shirt,pants,trousers,shorts,jeans,skirt,dress,jacket,coat,hat,cap,helmet,shoe,shoes,boot,"
               "boots,sneaker,sneakers,sock,socks,glove,gloves,wetsuit,uniform,jersey,tie,necktie,scarf,glasses,sunglasses,eyeglasses,"
               "goggles,belt,sweater,hoodie,sweatshirt,vest,apron,top,tank top,blouse,suit,bracelet,necklace,watch,wristwatch,ring,"
               "earring,earrings,collar,sleeve,sleeves,hood,headband,bandana,visor,beanie,cardigan,overalls,raincoat,robe,gown,"
               "uniforms,bikini,swimsuit,swim trunks,mask,face mask,veil,crown,tiara,headphones,earphones,backpack,purse,handbag,bag,"
               "shoulder bag,umbrella,cane,wrist band,wristband,mitt,baseball glove,kimono,parka,snow pants,ski pants,ski boots,"
               "snow boots,heels,sandals,sandal,flip flops,slippers,jumpsuit,leggings,stockings,tights,pajamas,bra,underwear,lanyard,"
               "badge,name tag,pocket,button,buttons,zipper,strap,straps,brim,cowboy hat,baseball cap,ski goggles,outfit,clothes,"
               "clothing,costume,eye glasses,sun glasses,shirts,coats,jackets,hats,helmets,caps,boots,gloves,undershirt,blazer,polo,shawl,poncho,scrubs,windbreaker,tuxedo,wetsuits,kerchief,turban,skirts,dresses,pants leg,sweatpants,tracksuit,shirt collar".split(","))
NOT_A_TOP = {"helmet", "shoe", "shoes", "sock", "socks", "boot", "boots", "sneaker", "sneakers", "tie", "necktie", "pocket", "button",
             "buttons", "zipper", "strap", "straps", "collar", "sleeve", "sleeves", "badge", "name tag", "lanyard", "brim", "heels",
             "sandals", "sandal", "flip flops", "slippers", "ski boots", "snow boots", "wrist band", "wristband", "mitt",
             "baseball glove", "headband", "visor", "hood"}       # the wear colour is read from a body garment, never a shoe or a strap
CARRIED = {"umbrella", "bag", "backpack", "purse", "handbag", "shoulder bag", "cane", "walking stick"}
# accessories by object name: the shared map, plus the nouns it leaves out because free text uses them in other senses (to watch, a
# ring of people); an object a person wears in a graph is the thing itself
ACCESSORY = {**maps.ACCESSORY, "watch": "watch", "ring": "ring", "belt": "belt"}
WEAR_OUT = ("wearing", "wears", "wear", "dressed in", "in", "has", "with", "has on")        # person -> garment
WEAR_IN = ("on", "worn on", "worn by", "of", "on top of", "around", "covering", "worn around", "tied around")
CARRY_OUT = ("holding", "carrying", "holds", "carries", "using", "holding onto")
HAS_PART = ("has", "with")                                                                  # person -> body part
PART_OF = ("of", "on", "belonging to")                                                      # body part -> person

# GQA's compound predicates (a posture or a verb before a spatial phrase) -> a relation of the trie list; the plain phrases go
# through maps.RELATION ('on' and 'in' stay unmapped there and here)
REL_EXTRA = {"on top of": "above", "sitting on top of": "above", "lying on top of": "above", "standing on top of": "above",
             "hanging above": "above", "flying above": "above", "flying over": "above", "hanging over": "above",
             "staring at": "looking at", "looking down at": "looking at", "observing": "looking at", "watching": "looking at",
             "holding onto": "holding", "reflecting in": "reflected in", "reflected on": "reflected in", "close to": "beside",
             "parked alongside": "beside", "underneath": "under", "beneath": "under", "bigger than": "larger than"}
POSTURE_VERBS = ("standing", "sitting", "parked", "lying", "walking", "hanging", "growing", "leaning", "running", "flying", "floating",
                 "resting", "waiting", "swimming", "perched", "sleeping", "playing", "mounted", "stacked", "placed")
SPATIAL_TAILS = ("next to", "by", "near", "beside", "behind", "in front of", "under", "below", "above", "inside", "beneath",
                 "underneath")
LEFT_RIGHT = ("to the left of", "to the right of")       # GQA's dense box-centre pairs, every object against every other

# the person's pose from a predicate's first word ('sitting on' -> sitting)
POSE_PRED = {"sitting": "sitting", "standing": "standing", "walking": "walking", "lying": "lying", "laying": "lying",
             "leaning": "leaning", "running": "running", "jumping": "jumping", "kneeling": "kneeling", "climbing": "climbing",
             "crouching": "crouching", "resting": "resting"}
EXPRESSION = {"smiling": "smile", "laughing": "laughing", "frowning": "frown", "crying": "crying", "grinning": "grin"}
EXPRESSION_PART = {("mouth", "open"): "open mouth", ("mouth", "closed"): "closed mouth", ("eyes", "closed"): "closed eyes",
                   ("eyes", "shut"): "closed eyes", ("mouth", "smiling"): "smile", ("face", "smiling"): "smile",
                   ("eyes", "smiling"): "smile"}
HAIR = {"short": "short", "long": "long", "curly": "curly", "straight": "straight", "wavy": "wavy", "braided": "braided",
        "messy": "messy", "wet": "wet", "shaved": "shaved", "buzzed": "buzzed", "slicked back": "slicked"}
# a thing's state: one condition or activity word (colour, size, material and shape words are not states)
STATE = {w: w for w in ("open,closed,empty,full,wet,dry,parked,lit,broken,sliced,cut,cooked,fried,grilled,baked,toasted,melted,frozen,"
                        "stacked,folded,piled,flying,floating,grazing,eating,sleeping,drinking,swimming,lying,sitting,standing,running,"
                        "walking,jumping,resting,docked,bare,leafless,blooming,ripe,unripe,rusty,dirty,clean,cracked,burnt,"
                        "crumpled,wrinkled,torn,damaged,upside down,chopped,shredded,halved,peeled,fallen,tied,rolled,wrapped,splashing,"
                        "choppy,rippled,dead,dried,overgrown,muddy,dusty,snowy,leaning,hanging,crossing,turning,braking,landing,"
                        "taking off,barking,perched,mowed,trimmed,unlit,half full,moving,deflated,inflated").split(",")}
STATE.update({"illuminated": "lit", "lighted": "lit", "glowing": "lit", "turned on": "switched on", "filled": "full",
              "laying": "lying", "leafy": "in leaf", "flowering": "blooming", "bloomed": "blooming", "snow covered": "snowy",
              "lying down": "lying"})
STATE_ORDER = ["grazing", "eating", "drinking", "sleeping", "swimming", "flying", "floating", "running", "walking", "jumping", "lying",
               "sitting", "standing", "resting", "barking", "perched", "landing", "taking off", "crossing", "turning", "braking",
               "moving", "parked", "docked", "open", "closed", "lit", "switched on", "unlit", "empty", "full", "half full",
               "sliced", "cut", "chopped", "halved", "peeled", "shredded", "cooked", "fried", "grilled", "baked", "toasted", "melted",
               "frozen", "stacked", "folded", "piled", "rolled", "wrapped", "tied", "hanging", "leaning", "upside down", "broken",
               "cracked", "torn", "damaged", "crumpled", "wrinkled", "burnt", "rusty", "dirty", "clean", "muddy", "dusty", "snowy",
               "wet", "dry", "dried", "bare", "leafless", "in leaf", "blooming", "ripe", "unripe", "fallen", "dead", "overgrown",
               "mowed", "trimmed", "splashing", "choppy", "rippled", "deflated", "inflated"]
_RANK = {s: i for i, s in enumerate(STATE_ORDER)}
ANIMATE_STATES = {"grazing", "eating", "drinking", "sleeping", "swimming", "running", "walking", "jumping", "lying", "sitting",
                  "standing", "resting", "barking", "perched"}
PAIRS = {"skis", "scissors", "glasses", "binoculars", "pants", "jeans", "shorts", "goggles", "headphones", "tongs", "pliers",
         "sunglasses", "trousers", "earphones", "skates", "ski poles"}
SINGULAR_S = {"bus", "gas", "lens", "news", "series", "species", "canvas", "dress", "glass", "grass", "moss", "cross", "boss", "bass",
              "cactus", "octopus", "hummus", "asparagus", "hippopotamus", "walrus", "iris", "tennis", "chess", "mattress", "harness",
              "compass", "class", "brass", "trellis", "chassis", "hibiscus", "citrus", "circus", "campus", "abacus", "atlas",
              "carcass", "fungus", "lotus", "thermos", "christmas", "status", "gps"}
ANIMALS = set("dog,dogs,cat,cats,horse,horses,cow,cows,sheep,elephant,elephants,giraffe,giraffes,zebra,zebras,bear,bears,bird,birds,"
              "duck,ducks,goose,geese,seagull,seagulls,pigeon,pigeons,animal,animals,cattle,calf,lamb,goat,goats,deer,pony,puppy,"
              "kitten,polar bear,lion,tiger,monkey,swan,swans,chicken,chickens,owl,parrot,crow,eagle,hawk,squirrel,"
              "rabbit,mouse,fish,ox,bull,donkey,pig,pigs,camel,kangaroo,rhino,hippo,dolphin,whale,butterfly,bee,insect,bug,"
              "turtle,frog,lizard,snake,crab".split(","))
WILD = set("elephant,elephants,giraffe,giraffes,zebra,zebras,bear,bears,polar bear,lion,tiger,deer,monkey,owl,eagle,hawk,squirrel,"
           "rhino,hippo,dolphin,whale,kangaroo,camel,swan,swans,seagull,seagulls,bird,birds,duck,ducks,goose,geese".split(","))
FOOD = set("pizza,sandwich,donut,donuts,doughnut,doughnuts,cake,broccoli,banana,bananas,apple,apples,orange,oranges,carrot,carrots,"
           "hot dog,food,bread,cheese,meat,vegetables,vegetable,fruit,salad,soup,dessert,cupcake,cookie,cookies,pie,pasta,rice,egg,"
           "eggs,tomato,tomatoes,onion,pepper,sauce,fries,burger,hamburger,sushi,meal,breakfast,lunch,dinner,muffin,bagel,pastry,"
           "chicken,steak,potato,potatoes,noodles,lettuce,cucumber,lemon,lemons,lime,strawberry,strawberries,grapes,pineapple,"
           "coffee,drink,wine,beer,juice,plate,bowl,tray,dish,dishes,pizza slice,slice,sandwiches,pizzas".split(","))
VEHICLES = set("train,bus,airplane,plane,jet,boat,boats,truck,motorcycle,car,cars,van,taxi,ship,sailboat,helicopter,trolley,tram,"
               "locomotive,bicycle,bike,scooter,trucks,buses,trains,airplanes,motorcycles,suv,jeep,vehicle,vehicles,engine,"
               "tractor,canoe,kayak,yacht,bikes,motorbike".split(","))
SPORT_GEAR = set("skateboard,surfboard,skis,ski,snowboard,racket,tennis racket,racquet,baseball bat,frisbee,tennis ball,baseball,"
                 "soccer ball,football,basketball,volleyball,golf club,hockey stick,baseball glove,mitt,ski pole,ski poles,"
                 "wetsuit,tennis court,home plate,mound,dugout,surf board,skate park".split(","))
STREET = set("street,road,sidewalk,crosswalk,traffic light,street light,street sign,taxi,intersection,stop sign,parking meter,curb,"
             "lamp post,traffic,storefront".split(","))
INDOOR_ONLY = {"ceiling", "couch", "bed", "toilet", "refrigerator", "stove", "oven", "sofa", "bathtub", "fireplace", "fridge",
               "microwave", "carpet", "bookshelf", "pillow", "pillows"}
# setting words among the object names (a name that is a place in view); the big ones only when they fill part of the frame
SETTING = {"beach": "beach", "shore": "beach", "seashore": "beach", "kitchen": "kitchen", "forest": "forest", "woods": "forest",
           "jungle": "forest", "desert": "desert", "harbor": "harbour", "harbour": "harbour", "marina": "harbour",
           "market": "market street", "marketplace": "market street", "farmers market": "market street", "alley": "alley",
           "alleyway": "alley", "courtyard": "courtyard", "stadium": "stadium", "ballpark": "stadium", "skate park": "skate park",
           "skatepark": "skate park", "farm": "farm", "barnyard": "farm", "vineyard": "vineyard", "swamp": "swamp", "marsh": "swamp",
           "cave": "cave", "ruins": "ruins", "library": "library", "temple": "temple", "shrine": "temple", "garden": "garden",
           "meadow": "meadow", "dock": "pier", "pier": "pier", "jetty": "pier", "wharf": "pier", "boardwalk": "pier",
           "bus stop": "bus stop", "greenhouse": "greenhouse", "riverbank": "river bank", "river bank": "river bank",
           "classroom": "classroom", "attic": "attic", "laboratory": "laboratory", "workshop": "workshop",
           "subway station": "subway", "night market": "night market"}
SETTING_LARGE = {"bridge": ("bridge", 0.25), "cliff": ("cliff", 0.15), "cliffs": ("cliff", 0.15), "lighthouse": ("lighthouse", 0.10),
                 "cathedral": ("cathedral", 0.20), "rooftop": ("rooftop", 0.20)}
SETTING_ATTR = {"kitchen": "kitchen"}                     # an attribute naming the room ('kitchen' sink, 'kitchen' counter)
KITCHEN_A = {"stove", "oven", "range", "stovetop", "burner", "burners"}
KITCHEN_B = {"refrigerator", "fridge", "sink", "dishwasher", "microwave", "range hood", "kitchen sink"}
WEATHER_FIELD = {"clear": "clear", "cloudless": "clear", "sunny": "clear", "cloudy": "overcast", "overcast": "overcast",
                 "foggy": "fog", "misty": "fog", "stormy": "storm", "rainy": "rain", "snowy": "snow", "hazy": "haze"}
SKY_WEATHER = {"clear": "clear", "cloudless": "clear", "sunny": "clear", "cloudy": "overcast", "overcast": "overcast",
               "foggy": "fog", "misty": "fog", "hazy": "haze", "stormy": "storm", "rainy": "rain"}
SKY_NAMES = {"sky", "skies"}
SNOWY_GROUND = {"ground", "field", "slope", "ski slope", "hill", "hillside", "road", "street", "sidewalk", "yard", "area", "trees",
                "tree", "bushes", "path", "trail", "park", "lawn", "mountainside"}        # not a far snowy peak
EXPLICIT = {"nude", "naked", "topless", "penis", "vagina", "genitals", "nipple", "nipples", "breasts", "porn", "pornographic", "erotic",
            "sex", "sexy", "condom", "dildo"}
REL_PRIORITY = {"holding": 6, "looking at": 5, "leaning on": 5, "touching": 5, "facing": 4, "reflected in": 4, "inside": 4,
                "in front of": 3, "behind": 3, "above": 3, "below": 3, "under": 3, "beside": 2, "larger than": 2, "smaller than": 2,
                "same colour as": 2, "left of": 0, "right of": 0}
NON_SPATIAL = {"holding", "looking at", "leaning on", "touching", "facing", "reflected in", "inside"}


# ------------------------------------------------------------------ geometry
class Obj:
    __slots__ = ("id", "name", "attrs", "x", "y", "w", "h", "rels")

    def __init__(self, oid, o):
        self.id = oid
        self.name = core.clean(o.get("name", ""))
        self.attrs = [a for a in (core.clean(a) for a in o.get("attributes", []) or []) if a]
        self.x, self.y = float(o.get("x", 0)), float(o.get("y", 0))
        self.w, self.h = max(0.0, float(o.get("w", 0))), max(0.0, float(o.get("h", 0)))
        self.rels = [(core.clean(r.get("name", "")), str(r.get("object"))) for r in o.get("relations", []) or []]

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2


def _inter(a: Obj, b: Obj) -> float:
    iw = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    ih = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return max(0.0, iw) * max(0.0, ih)


def _iou(a: Obj, b: Obj) -> float:
    i = _inter(a, b)
    u = a.area + b.area - i
    return i / u if u > 0 else 0.0


def _inside(a: Obj, b: Obj) -> float:
    """The share of a's box inside b's box."""
    return _inter(a, b) / a.area if a.area > 0 else 0.0


def _same_body(a: Obj, b: Obj) -> bool:
    """Two person boxes of one person (Visual Genome often names one person twice: 'man' and 'skier'); two boxes of one name
    (two 'man' boxes, one behind the other) merge only when they nearly coincide."""
    if a.name == b.name:
        return _iou(a, b) >= 0.7
    if _iou(a, b) >= 0.55:
        return True
    small, big = (a, b) if a.area <= b.area else (b, a)
    return big.area > 0 and small.area / big.area >= 0.45 and _inside(small, big) >= 0.85


# ------------------------------------------------------------------ helpers
def _person_info(o: Obj, names: set):
    info = PERSON.get(o.name)
    if info is None:
        return None
    ctx = CONTEXT.get(o.name)
    if ctx is not None and not (names & (ctx - {o.name})):
        return None
    return info


def _rel_value(pred: str) -> str | None:
    if pred in REL_EXTRA:
        return REL_EXTRA[pred]
    if pred in maps.RELATION:
        return maps.RELATION[pred]
    words = pred.split(" ", 1)
    if len(words) == 2 and words[0] in POSTURE_VERBS and words[1] in SPATIAL_TAILS:
        return REL_EXTRA.get(words[1]) or maps.RELATION.get(words[1])
    return None


def _colours(attrs) -> list:
    out = []
    for a in attrs:
        for v in maps.find(a, maps.COLOUR):
            if v not in maps.HAIR_COLOUR_ONLY and v not in out:
                out.append(v)
    return out


def _one_colour(attrs) -> str | None:
    c = _colours(attrs)
    return c[0] if len(c) == 1 else None


def _not_an_end(name: str) -> bool:
    """A body part, a part of an object, a word or a mark, by the name or its head word ('apple logo', 'giraffe neck', 'door
    frame'): never the thing, never a relation end."""
    head = name.split()[-1]
    return any(n in BODY or n in TEXTISH or n in HAIR_PART or n in PARTS for n in (name, head))


def _garment(name: str) -> bool:
    """A worn thing by its name or its head word ('winter jacket', 'eye glasses'); 'jacket pocket' is a pocket."""
    return name in GARMENTS or name.split()[-1] in GARMENTS


def _wear_value(name: str, mapping: dict) -> str | None:
    """A garment name -> its value in a closed list: the whole name, its last two words, or its head word ('ski goggles' -> glasses)."""
    w = name.split()
    for k in (name, " ".join(w[-2:]), w[-1]):
        if k in mapping:
            return mapping[k]
    return None


def _number(name: str) -> str | None:
    """'single', 'plural' or None (a pair word: a count of skis says little) by the last word of an object name."""
    last = name.split()[-1]
    if last in PAIRS or name in PAIRS:
        return None
    if last.endswith("s") and last not in SINGULAR_S and not last.endswith(("ss", "us", "is")):
        return "plural"
    return "single"


def _out(ids, out_e):
    for i in ids:
        yield from out_e[i]


def _person_name(p) -> str:
    """The relation end of a person without a gender: its role name ('skier') or its first name ('person')."""
    for o in p["objs"]:
        if PERSON.get(o.name, (None,))[0] is None and o.name not in ("person", "human", "individual", "adult"):
            return o.name
    return p["objs"][0].name


def _genre(persons, main_p, thing, names, img, indoors) -> str:
    tname = thing.name if thing is not None else None
    if main_p is not None and (main_p["role"] == "athlete" or names & SPORT_GEAR):
        return "sport"
    if main_p is None:
        if tname in WILD:
            return "wildlife"
        if tname in ANIMALS:
            return "animal"
        if tname in FOOD:
            return "food"
        if tname in VEHICLES:
            return "transport"
        if indoors:
            return "interior"
        if names & STREET:
            return "street"
        if thing is None:
            return "landscape"
        return "documentary"
    if len(persons) == 1 and not main_p["plural"] and main_p["area"] / img >= 0.30:
        return "portrait"
    if names & STREET and not indoors:
        return "street"
    if indoors:
        return "interior"
    return "documentary"


# ------------------------------------------------------------------ the graph -> the spec
def spec_of(graph: dict) -> tuple:
    """-> (core.Spec, genre) for one GQA scene graph, or (None, reason) when the graph is skipped."""
    W, H = float(graph.get("width") or 0), float(graph.get("height") or 0)
    if W <= 0 or H <= 0:
        return None, "no size"
    objs = {str(k): Obj(str(k), v) for k, v in (graph.get("objects") or {}).items()}
    objs = {k: o for k, o in objs.items() if o.name}
    if not objs:
        return None, "no objects"
    names = {o.name for o in objs.values()}
    words = set()
    for o in objs.values():
        words.update(o.name.split())
        for a in o.attrs:
            words.update(a.split())
    if words & EXPLICIT:
        return None, "explicit word"
    img = W * H
    edges = [(o.id, p, t) for o in objs.values() for p, t in o.rels if t in objs and p]
    out_e, in_e = defaultdict(list), defaultdict(list)
    for a, p, b in edges:
        out_e[a].append((p, b))
        in_e[b].append((p, a))

    # ---- persons: person objects merged by box overlap; the largest is the main one
    pobjs = [o for o in objs.values() if _person_info(o, names) is not None]
    person_ids = {o.id for o in pobjs}
    singles = sorted([o for o in pobjs if _person_info(o, names)[3] is None], key=lambda o: -o.area)
    groups = [o for o in pobjs if _person_info(o, names)[3] is not None]
    clusters = []
    for o in singles:
        for c in clusters:
            if _same_body(o, c[0]):
                c.append(o)
                break
        else:
            clusters.append([o])
    persons = []
    for c in clusters:
        infos = [_person_info(o, names) for o in c]
        genders = {i[0] for i in infos if i[0]}
        ages = {i[1] for i in infos if i[1]}
        roles = {i[2] for i in infos if i[2]}
        persons.append(dict(objs=c, ids={o.id for o in c}, gender=next(iter(genders)) if len(genders) == 1 else None,
                            age=next(iter(ages)) if len(ages) == 1 else None, role=next(iter(roles)) if len(roles) == 1 else None,
                            area=c[0].area, plural=None, label=None))
    group_kinds = [_person_info(o, names)[3] for o in groups]
    group_genders = [_person_info(o, names)[0] for o in groups]
    main_p = persons[0] if persons else None
    if main_p is None and groups:                  # only a group ('people', 'crowd'): the group is the person record
        g = max(groups, key=lambda o: o.area)
        gi = _person_info(g, names)
        main_p = dict(objs=[g], ids={g.id}, gender=gi[0], age=gi[1], role=gi[2], area=g.area, plural=gi[3], label=None)

    s = core.Spec()
    worn_ids = set()
    if main_p is not None:
        n_single = len(persons)
        if "many" in group_kinds:
            count = "many"
        elif groups and set(group_kinds) == {"two"} and n_single <= 2:
            count = "2"
        elif groups or n_single >= 4:
            count = "several"
        else:
            count = str(n_single)
        s.set("person", "count", count)
        # with more than one person, a fact of the main one is kept only when the main one is clearly the subject (twice the
        # box of every other person or group) or, for gender / age / role, when every other person agrees
        others = [p for p in persons if p is not main_p]
        other_groups = [g for g in groups if g.id not in main_p["ids"]]
        clear = main_p["plural"] is None and all(main_p["area"] >= 2.0 * p["area"] for p in others) and \
            all(main_p["area"] >= 2.0 * g.area for g in other_groups)
        solo = count == "1" or clear

        def agree(i: int, value) -> bool:
            return all(p[("gender", "age", "role")[i]] == value for p in others) and \
                all(_person_info(g, names)[i] == value for g in other_groups)

        def put(system: str, attr: str, value) -> None:
            if solo:
                s.set(system, attr, value)

        one = count == "1"                             # 'several' + 'man' reads as several men: identity needs every person
        if main_p["gender"] and (one or agree(0, main_p["gender"])):
            s.set("person", "gender", main_p["gender"])
        # age: the names, then '<attribute> <name>' phrases of the main person ('old man', 'little girl')
        age = main_p["age"]
        if age is None:
            ages = set()
            for o in main_p["objs"]:
                for a in o.attrs:
                    ages.update(maps.find(f"{a} {o.name}", maps.AGE))
                    if a == "elderly":
                        ages.add("elderly")
            age = ages.pop() if len(ages) == 1 else None
        if age and (one or agree(1, age)):
            s.set("person", "age", age)
        if main_p["role"] and (one or agree(2, main_p["role"])):
            s.set("person", "role", main_p["role"])
        pid = main_p["ids"]
        pattrs = [a for o in main_p["objs"] for a in o.attrs]
        lone = len(persons) == 1 and not groups
        # the main person's body parts (for the look and the wear): linked by 'of' / 'has', or inside a lone person's box
        parts = {}
        for o in objs.values():
            if o.name in BODY or o.name in HAIR_PART:
                owned = any(t in pid and p in PART_OF for p, t in out_e[o.id]) or \
                        any(sid in pid and p in HAS_PART for p, sid in in_e[o.id])
                if not owned and lone and _inside(o, main_p["objs"][0]) >= 0.9:
                    owned = True
                if owned:
                    parts[o.id] = o
        # look: expression and hair style
        exprs = {EXPRESSION[a] for a in pattrs if a in EXPRESSION}
        for o in parts.values():
            for a in o.attrs:
                if (o.name, a) in EXPRESSION_PART:
                    exprs.add(EXPRESSION_PART[(o.name, a)])
        if "smile" in exprs:
            exprs.discard("open mouth")
        if len(exprs) == 1:
            put("look", "expression", exprs.pop())
        hairs = set()
        for o in parts.values():
            if o.name == "hair":
                hairs.update(HAIR[a] for a in o.attrs if a in HAIR)
            elif o.name in HAIR_PART:
                hairs.add(HAIR_PART[o.name])
        if "bald" in pattrs or any("bald" in o.attrs for o in parts.values()):
            hairs = set()
        if len(hairs) == 1:
            put("look", "hair", hairs.pop())
        # wear: linked garments (direct, through a body part, or a garment box inside the main person's box only)
        worn = {}
        for p, t in _out(pid, out_e):
            o = objs[t]
            if _garment(o.name) and (p in WEAR_OUT or (p in CARRY_OUT and o.name in CARRIED)):
                worn[t] = o
        for t in list(pid) + list(parts):
            for p, sid in in_e[t]:
                if _garment(objs[sid].name) and p in WEAR_IN:
                    worn[sid] = objs[sid]
        for bp in parts:
            for p, t in out_e[bp]:
                if _garment(objs[t].name) and (p in WEAR_OUT or (p in CARRY_OUT and objs[t].name in CARRIED)):
                    worn[t] = objs[t]
        boxes = [p["objs"][0] for p in persons] + groups
        for o in objs.values():
            if _garment(o.name) and o.id not in worn and o.name not in CARRIED and o.area > 0:
                holders = [b for b in boxes if _inside(o, b) >= 0.8]
                if len(holders) == 1 and holders[0] is main_p["objs"][0]:
                    worn[o.id] = o
        worn_ids = set(worn)
        for b in boxes:                                # every person's garments stay out of the thing and the relations
            if b is main_p["objs"][0]:
                continue
            worn_ids.update(o.id for o in objs.values() if _garment(o.name) and o.name not in CARRIED and _inside(o, b) >= 0.8)
        cloth = [(o, _wear_value(o.name, maps.CLOTHING)) for o in worn.values() if _wear_value(o.name, maps.CLOTHING)]
        acc = [(o, _wear_value(o.name, ACCESSORY)) for o in worn.values() if _wear_value(o.name, ACCESSORY)]
        wear_colour = None
        if cloth:
            o, v = max(cloth, key=lambda x: x[0].area)
            put("wear", "clothing", v)
            wear_colour = _one_colour(o.attrs)
        if acc:
            o, v = max(acc, key=lambda x: x[0].area)
            put("wear", "accessory", v)
        if not cloth:
            tops = sorted((o for o in worn.values() if o.name not in CARRIED and not _wear_value(o.name, ACCESSORY)
                           and o.name not in NOT_A_TOP), key=lambda o: -o.area)
            if tops:
                c = _one_colour(tops[0].attrs)
                nxt = tops[1] if len(tops) > 1 else None
                if c and (nxt is None or tops[0].area >= 1.5 * nxt.area or _one_colour(nxt.attrs) == c):
                    wear_colour = c
        if wear_colour:
            put("wear", "colour", wear_colour)
        # body: pose and gesture from the attributes and the predicates of the main person (two poses: none)
        poses = {maps.POSE[a] for a in pattrs if a in maps.POSE}
        for p, _t in _out(pid, out_e):
            w0 = p.split(" ", 1)[0]
            if w0 in POSE_PRED:
                poses.add(POSE_PRED[w0])
        poses &= set(core.closed_list("body pose"))
        if len(poses) == 1:
            put("body", "pose", poses.pop())
        gestures = {maps.GESTURE[a] for a in pattrs if a in maps.GESTURE}
        if any(p.startswith("pointing") for p, _ in _out(pid, out_e)):
            gestures.add("pointing")
        if len(gestures) == 1:
            put("body", "gesture", gestures.pop())
        main_p["label"] = s.d.get("person", {}).get("gender") or _person_name(main_p)

    # ---- the scene
    loc = core.clean(graph.get("location") or "")
    indoors = loc == "indoors" or (loc != "outdoors" and bool(names & INDOOR_ONLY))
    settings = []
    for o in objs.values():
        if o.name in SETTING:
            settings.append(SETTING[o.name])
        elif o.name in SETTING_LARGE and o.area / img >= SETTING_LARGE[o.name][1]:
            settings.append(SETTING_LARGE[o.name][0])
        settings += [SETTING_ATTR[a] for a in o.attrs if a in SETTING_ATTR]
    if names & KITCHEN_A and names & KITCHEN_B:
        settings.append("kitchen")
    if loc:
        settings += maps.find(loc, maps.SETTING)
    settings = list(dict.fromkeys(settings))
    if len(settings) == 1:                         # two setting words (a pier and a beach): left out
        s.set("scene", "setting", settings[0])
    weather = WEATHER_FIELD.get(core.clean(graph.get("weather") or ""))
    if weather is None:
        sky = {SKY_WEATHER[a] for o in objs.values() if o.name in SKY_NAMES for a in o.attrs if a in SKY_WEATHER}
        if len(sky) == 1:
            weather = sky.pop()
    if weather is None and not indoors:
        if "rain" in names or "raindrops" in names:
            weather = "rain"
        elif "fog" in names or "mist" in names:
            weather = "fog"
        elif "snow" in names:
            snow = sum(o.area for o in objs.values() if o.name == "snow") / img
            falling = any(o.name == "snow" and ("falling" in o.attrs or "flying" in o.attrs) for o in objs.values())
            snowy = any(o.name in SNOWY_GROUND and "snowy" in o.attrs for o in objs.values())
            if snow >= 0.05 or falling or snowy:
                weather = "snow"
    if weather and not indoors:
        s.set("scene", "weather", weather)
    if names & {"crowd", "audience", "spectators"}:
        s.set("scene", "layout", "crowd")

    # ---- the thing: the most salient non-person object (box share + a bonus for its annotated relations)
    degree = Counter()
    for a, p, b in edges:
        if p not in LEFT_RIGHT:
            degree[a] += 1
            degree[b] += 1

    def eligible(o, backdrop_ok=False):
        if o.id in person_ids or o.id in worn_ids or o.area <= 0:
            return False
        if len(o.name) > min(core.tp.VAL_MAX, core.tp.REC_MAX - len("thing name")):
            return False                               # a name over the record budget: the next object (never an orphan count)
        if _not_an_end(o.name):                        # a person name outside its context ('pitcher' by a sink) is a thing
            return False
        if _garment(o.name) and o.name not in CARRIED:
            return False
        return backdrop_ok or (o.name not in BACKDROP and o.name.split()[-1] not in BACKDROP)

    main_box = main_p["objs"][0] if main_p is not None else None

    def salience(o) -> float:
        v = o.area / img
        if main_box is not None and main_box.area > 0 and _inside(main_box, o) >= 0.9:
            v *= 0.3                                   # the train car the person sits in is the place, not the subject
        return v + 0.03 * min(degree[o.id], 6)

    def support(o) -> bool:                            # the plate under the food, the table under the plate
        return o.name in SUPPORT or o.name.split()[-1] in SUPPORT

    cands = [o for o in objs.values() if eligible(o)]
    if not cands:
        cands = [o for o in objs.values() if eligible(o, True) and o.name not in GROUND_ONLY and o.area / img >= 0.1]
    held_up = [o for o in cands if not support(o) and o.area / img >= 0.01]
    thing = max(held_up or cands, key=salience) if cands else None
    if thing is not None:
        s.set("thing", "name", thing.name)
        kept = []
        for o in sorted((o for o in objs.values() if o.name == thing.name), key=lambda o: -o.area):
            if not any(_iou(o, k) >= 0.5 or (_inside(o, k) >= 0.9 and o.area >= 0.5 * k.area) for k in kept):
                kept.append(o)
        form = _number(thing.name)
        if form == "plural":
            s.set("thing", "count", "several")
        elif form == "single":
            s.set("thing", "count", str(len(kept)) if len(kept) <= 3 else "several")
        # colour and state: of the one thing, or shared by every one of its name (two cats, one eating: no state)
        c = _one_colour(thing.attrs)
        if c and all(_one_colour(o.attrs) == c for o in kept):
            s.set("thing", "colour", c)
        states = {STATE[a] for a in thing.attrs if a in STATE}
        for o in kept:
            states &= {STATE[a] for a in o.attrs if a in STATE}
        if thing.name not in ANIMALS:
            states -= ANIMATE_STATES                   # 'a cup sitting on a table' is the annotator's verb, not a state
        if states:
            s.set("thing", "state", min(states, key=lambda v: _RANK.get(v, 999)))
        # the position of every box of its name: one side only when all of them are there ('several signs, on the right' is not
        # said of signs spread across the frame)
        sides = {maps.position_of(o.cx / W) for o in kept + [thing]}
        if len(sides) == 1:
            s.set("thing", "position", sides.pop())

    s.set("form", "medium", "photograph")

    # ---- relations: the trie's list only, the main person's and the thing's first, at most three left / right pairs
    def end_name(o: Obj) -> str | None:
        if main_p is not None and o.id in main_p["ids"]:
            return main_p["label"]
        if _not_an_end(o.name):
            return None
        if _garment(o.name) and o.name not in CARRIED:     # a garment lives in the wear system (or on an unseen person)
            return None
        if o.name in ("camera", "viewer", "photographer") and o.area / img >= 0.5:
            return None                                # 'looking at camera' over the whole frame: the viewer, not an object
        return o.name

    annotated = {frozenset((a, b)) for a, p, b in edges if p not in LEFT_RIGHT}
    cand_rels = []
    for a, p, b in edges:
        rel = _rel_value(p)
        if rel is None:
            continue
        oa, ob = objs[a], objs[b]
        na, nb = end_name(oa), end_name(ob)
        if not na or not nb or na == nb:
            continue
        touches_p = main_p is not None and (a in main_p["ids"] or b in main_p["ids"])
        touches_t = thing is not None and thing.id in (a, b)
        if p in LEFT_RIGHT:
            # GQA computes these for every pair: keep the ones of the main person or the thing, and never for a pair the
            # annotators joined otherwise (a skier 'wearing' a ski, a man 'on' a horse)
            if not (touches_p or touches_t) or frozenset((a, b)) in annotated or min(oa.area, ob.area) / img < 0.01:
                continue
        if rel not in NON_SPATIAL and rel not in ("above", "below", "under") and \
                (_inside(oa, ob) >= 0.9 or _inside(ob, oa) >= 0.9):
            continue                                   # one box inside the other: 'left of' / 'behind' says little or the wrong thing
        if (rel not in ("above", "below", "under", "reflected in", "inside") and (oa.name in GROUND_ONLY or ob.name in GROUND_ONLY)) \
                or (oa.name in GROUND_ONLY and ob.name in GROUND_ONLY):
            continue                                   # 'ground left of crate', 'sidewalk below sky': the ground is everywhere
        score = float(REL_PRIORITY.get(rel, 1))
        if touches_p:
            score += 3
        if thing is not None and thing.id in (a, b):
            score += 2.5
        elif thing is not None and thing.name in (oa.name, ob.name):
            score += 1
        other = ob if (touches_p and a in main_p["ids"]) or (thing is not None and a == thing.id) else oa
        score += min(other.area / img, 0.5)
        cand_rels.append((score, na, rel, nb))
    cand_rels.sort(key=lambda r: -r[0])
    seen_pairs, lr = set(), 0
    for _score, na, rel, nb in cand_rels:
        pair = frozenset((na, nb))
        if pair in seen_pairs or (rel in ("left of", "right of") and lr >= 3):
            continue
        if s.relate(na, rel, nb):
            seen_pairs.add(pair)
            lr += rel in ("left of", "right of")
        if len(s.rels) >= core.MAX_RELATIONS:
            break
    genre = _genre(persons or ([main_p] if main_p else []), main_p, thing, names, img, indoors)
    return s, genre


# ------------------------------------------------------------------ seeds
VG_IMAGES = "image_data.json"       # Visual Genome's image metadata (image id -> coco_id), optional beside the zip


def coco_ids(raw_dir: str) -> dict:
    """{GQA image id: COCO image id} from Visual Genome's image_data.json when it is in raw_dir/gqa/ (GQA's images are Visual
    Genome's, about 51k of them COCO's too); {} without the file."""
    path = os.path.join(raw_dir, DATASET, VG_IMAGES)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    return {str(r.get("image_id", r.get("id"))): r["coco_id"] for r in rows if isinstance(r, dict) and r.get("coco_id")}


def seeds(raw_dir: str, limit: int | None = None, members=MEMBERS):
    """Seeds of the train graphs, then the val graphs (85,638 images in all), in file order; `limit`: at most that many (None:
    all, 0: none). A picture COCO also holds takes COCO's routing group (coco_ids), so its COCO captions, its Localized Narrative
    and its graph make one held / training choice."""
    path = os.path.join(raw_dir, DATASET, ZIP)
    STATS.clear()
    if limit is not None and limit <= 0:
        return
    coco = coco_ids(raw_dir)
    n = 0
    for iid, graph in iter_graphs(path, members):
        STATS["images"] += 1
        spec, genre = spec_of(graph)
        if spec is None:
            STATS[f"skip: {genre}"] += 1
            continue
        for k, v in spec.dropped.items():
            STATS[f"dropped {k}"] += v
        sid = str(iid)
        # (a training seed loses a sealed thing name with its whole thing system: core.strip_sealed)
        group = f"coco-image:{coco[sid]}" if sid in coco else None
        seed = core.make_seed(DATASET, sid, DOMAIN, genre, spec, "", LICENSE, URL, min_records=MIN_RECORDS, group=group)
        if seed is None:
            STATS["skip: rejected by make_seed"] += 1      # (the reason is counted in core.REJECTED)
            continue
        STATS["seeds"] += 1
        yield seed
        n += 1
        if limit is not None and n >= limit:
            return
