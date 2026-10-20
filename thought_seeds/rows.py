"""thought_seeds.rows - drawing the specs of a generation batch and checking the rows written from them.

A BATCH is the unit the writing model works in: a specs file (one JSON object a line, each a series of three nested specs or a single
spec with its depth, its domain, its ids already allotted) and the rows file written from it. The checker runs the dataset's own row
validator (thought_tools.validate, validate_series) and adds what a curator needs on top: ids unique and inside the batch's range, every
series whole (ranks 1-3 = simple, medium, deep), a seeded row keeping every record of its seed, the license field, and a list of
possible real names (capitalized words inside a sentence) for review.

    thought-seeds --draw=<batch number> --series=10 --singles=0 --rows-dir=<dir> [--rng=<seed>] [--seeds=<seed files or glob>]
    thought-seeds --check-rows=<rows.jsonl> [--specs=<specs.jsonl>]

Ids: series s-BBBNN (batch BBB, series NN < 100), rows art-BBBKKK (row KKK < 1000 within the batch)."""
from __future__ import annotations

import json
import os
import re
from collections import Counter

from . import core
from .core import HELD, tp
from .io import read_seeds

PILOT_DOMAINS = (("photograph", 0.45), ("painting", 0.25), ("illustration", 0.20), ("sculpture", 0.05), ("design", 0.05))
PILOT_DEPTHS = (("simple", 0.30), ("medium", 0.45), ("deep", 0.25))
# a sampled spec is a person in a scene: it can be a photograph, a painting or an illustration; sculpture and design come from seeds
DRAWN_DOMAINS = (("photograph", 0.50), ("painting", 0.28), ("illustration", 0.22))
PHOTO_MEDIA = {"photograph", "silver print", "cyanotype", "polaroid", "film still"}
PAINT_MEDIA = {"oil painting", "watercolour", "gouache", "acrylic", "fresco", "tempera", "pastel", "ink", "charcoal", "pencil"}
SCULPT_MEDIA = {"bronze", "marble", "clay"}
ILLUS_MEDIA = {"digital painting", "3d render", "pixel art", "vector art", "collage", "woodcut", "etching", "linocut", "lithograph"}
DESIGN_MEDIA = {"mosaic", "tapestry", "stained glass"}
PERMISSIVE_ROW = "Apache-2.0"
ATTRIBUTION_LICENSES = ("CC BY", "ODC-By")      # a row from such a seed keeps the seed's license (attribution travels with it)


ADULT_AGES = {"20s", "30s", "40s", "50s", "60s", "elderly", "young adult"}
YOUNG_AGES = {"child", "baby", "teen"}
INDOOR = {"kitchen", "studio", "subway", "cathedral", "cafe", "library", "ballroom", "classroom", "greenhouse", "workshop",
          "laboratory", "temple", "hospital ward", "attic", "cave"}
TIGHT_FRAMING = {"macro", "extreme close", "detail"}
NO_SKY = {"subway", "cave"}                   # no sun, moon or horizon reaches them
STREET_LIT = {"market street", "alley", "bridge", "bus stop", "harbour", "pier", "rooftop", "courtyard", "night market", "skate park"}
SKY_LIGHTS = {"hard sun", "golden", "dappled", "moonlight"}
SKY_HOURS = {"dawn", "golden hour", "dusk", "blue hour"}                 # hours named by the colour of the sky
WET_OR_WINDY = {"rain", "storm", "wind", "drizzle", "sleet", "snow"}
DAY_HOURS = {"morning", "noon", "afternoon"}
FLAT_THINGS = {"window", "mirror", "painting", "poster", "flag", "map", "sign"}     # nothing is 'inside' them
DARK_HOURS = {"blue hour", "night", "midnight", "late evening"}
WIDE_COMPOSE = {"frame in frame", "horizon high", "horizon low", "leading lines"}      # compositions a macro frame cannot hold
WATER = {"beach", "river bank", "harbour", "pier", "swamp"}                            # where a person floats
PERSON_DETAILS = (("look", "hair"), ("look", "expression"), ("look", "eyes"), ("wear", "clothing"), ("wear", "colour"),
                  ("wear", "accessory"))
TIGHT_DETAILS = {"extreme close": 3, "macro": 1, "detail": 1}      # an extreme close of a face shows hair, expression and eyes
DEEP_MIN_DRAWN = 10       # a deep spec keeps 10 drawn records after tighten(); the writer's mood, intent and story reach the deep count


def nested(specs: dict) -> bool:
    """A series' ranks are nested: every record of the simple spec is in the medium spec, and every record of the medium in the deep."""
    rec = {d: set(map(str, tp.records(s))) for d, s in specs.items()}
    return rec["simple"] <= rec["medium"] <= rec["deep"]


def tighten(specs: dict) -> dict:
    """A drawn series at a tight framing, made one picture: the relations go (a macro frame shows one small part, not two things in
    a relation) and the person keeps only the details the framing can show (the first in PERSON_DETAILS order). The framing words
    stay in the drawn rows instead of being redrawn away. The cut is decided on the fullest rank and applied to every rank, so the
    ranks stay nested (each a subset of the next). -> the series' specs, changed only when a rank's framing is tight."""
    tight = [s.get("shot", {}).get("framing") for s in specs.values() if s.get("shot", {}).get("framing") in TIGHT_FRAMING]
    if not tight:
        return specs
    fr = tight[0]
    full = max(specs.values(), key=tp.n_records)
    cut = set([k for k in PERSON_DETAILS if full.get(k[0], {}).get(k[1])][TIGHT_DETAILS[fr]:])
    big = tp.SIZE.get(full.get("thing", {}).get("name"), 2) > 1          # a whole dog does not fit a macro frame: the thing goes
    out = {}
    for depth, spec in specs.items():
        s = {k: dict(v) if isinstance(v, dict) else v for k, v in spec.items() if k != "relation" and not (big and k == "thing")}
        for sys_, attr in cut:
            if attr in s.get(sys_, {}):
                del s[sys_][attr]
                if not s[sys_]:
                    del s[sys_]
        out[depth] = s
    return out
NOT_DRAWN_MEDIA: set = set()                # media the validator cannot pass (none since tools 0.1.1)


def incoherent(spec: dict) -> list:
    """The reasons a drawn spec cannot be one picture (the sampler draws each value on its own): an age that contradicts the gender
    word, a two shot of one person, a tight framing of a whole-body pose, weather inside, a medium the validator cannot pass."""
    why = []
    p = spec.get("person", {})
    g, a = p.get("gender"), p.get("age")
    if g in ("boy", "girl") and a in ADULT_AGES:
        why.append(f"{g} aged {a}")
    if g in ("man", "woman") and a in YOUNG_AGES:
        why.append(f"{g} aged {a}")
    fr = spec.get("shot", {}).get("framing")
    if fr == "two shot" and p.get("count") == "1":
        why.append("a two shot of one person")
    if fr in TIGHT_FRAMING and spec.get("body", {}).get("pose"):
        why.append(f"{fr} framing of a {spec['body']['pose']} pose")
    rels = spec.get("relation") or []
    if fr in TIGHT_FRAMING and rels:
        why.append(f"{fr} framing of a relation between two things")          # a macro frame shows one small part
    details = [k for k in PERSON_DETAILS if spec.get(k[0], {}).get(k[1])]
    if fr in TIGHT_FRAMING and len(details) > TIGHT_DETAILS[fr]:
        why.append(f"{fr} framing of {len(details)} details of a person")
    sc = spec.get("scene", {})
    st = sc.get("setting")
    if st in INDOOR and sc.get("weather"):
        why.append(f"{sc['weather']} weather inside a {st}")
    light = spec.get("shot", {}).get("light")
    if light == "soft window" and st and st not in INDOOR:
        why.append(f"window light outdoors ({st})")
    if light == "street lamp" and st and st not in STREET_LIT:
        why.append(f"a street lamp at a {st}")
    if st in NO_SKY and light in SKY_LIGHTS:
        why.append(f"{light} light in a {st}")
    if st in NO_SKY and sc.get("time") in SKY_HOURS:
        why.append(f"{sc['time']} in a {st}")                                  # the hour of the sky's colour, where no sky shows
    if light == "candle" and st and st not in INDOOR and sc.get("weather") in WET_OR_WINDY:
        why.append(f"candle light in {sc['weather']} at a {st}")
    if light == "fluorescent" and st and st not in INDOOR and sc.get("time") in DAY_HOURS:
        why.append(f"tube light at a {st} in the {sc['time']}")                 # daylight outdoors drowns a tube light
    if st in INDOOR and spec.get("form", {}).get("compose") in ("horizon high", "horizon low"):
        why.append(f"a horizon inside a {st}")
    for r in rels:
        if r.get("rel") == "inside" and r.get("b") in FLAT_THINGS:
            why.append(f"{r.get('a')} inside a {r['b']}")
    held = {r.get("b") for r in rels if r.get("rel") == "holding"}
    for r in rels:
        if r.get("a") in held and r.get("rel") in ("inside", "on", "under", "leaning on"):
            why.append(f"{r['a']} held and {r['rel']} a {r.get('b')}")              # a held cup is not also in a suitcase
    tm, wx = sc.get("time"), sc.get("weather")
    if light == "high key" and (tm in DARK_HOURS or wx in ("storm", "rain", "fog", "sleet")):
        why.append(f"high key light at {tm or wx}")
    if wx == "heat shimmer" and tm in DARK_HOURS | {"dusk", "dawn"}:
        why.append(f"heat shimmer at {tm}")
    if light == "silhouette" and any(r.get("rel") == "same colour as" for r in rels):
        why.append("a colour relation under a silhouette")
    form = spec.get("form", {})
    if spec.get("shot", {}).get("lens") and form.get("medium") and form["medium"] not in PHOTO_MEDIA | {"3d render", "digital painting"}:
        why.append(f"a {spec['shot']['lens']} lens on a {form['medium']}")       # a lens is the camera's, not a lithograph's
    if fr in TIGHT_FRAMING and form.get("compose") in WIDE_COMPOSE:
        why.append(f"{form['compose']} at a {fr} framing")
    if fr in TIGHT_FRAMING and spec.get("shot", {}).get("angle") == "over the shoulder":
        why.append(f"over the shoulder at a {fr} framing")
    thing = spec.get("thing", {}).get("name")
    if fr in TIGHT_FRAMING and thing and tp.SIZE.get(thing, 2) > 1:
        why.append(f"a whole {thing} in a {fr} frame")                         # a macro frame holds a hand-sized thing
    if light == "silhouette" and form.get("contrast") in ("low", "gentle", "tonal"):
        why.append(f"{form['contrast']} contrast under a silhouette")
    if spec.get("body", {}).get("pose") == "floating" and st and st not in WATER:
        why.append(f"floating at a {st}")
    if spec.get("form", {}).get("medium") in NOT_DRAWN_MEDIA:
        why.append(f"medium {spec['form']['medium']}")
    return why


def thin(spec: dict, depth: str) -> bool:
    """A drawn spec too thin for its depth: a simple spec of one record (nothing to observe beyond a word), a medium spec with no shot
    or form record (the medium row speaks of the form)."""
    if depth == "simple":
        return tp.n_records(spec) < 2
    if depth == "medium":
        return not (spec.get("shot") or spec.get("form"))
    return False


COCO_FAMILY = ("coco", "localized_narratives")


def picture_of(seed: dict) -> str:
    """The picture a seed describes: COCO captions and Localized Narratives share the COCO image ids."""
    ds = seed["source"]["dataset"]
    return f"coco-image:{seed['source']['id']}" if ds in COCO_FAMILY else seed["seed_id"]


def seed_depth(seed: dict) -> str:
    """The depth a seed can carry, by its records and its hint (the writer may add facts the hint states plainly; mood, intent and
    story add their records): deep from 10 records and a 300-byte hint; medium from 5 records (a simple row holds at most 4), or 4
    with a 300-byte hint; three or fewer stay simple (at medium the reading would be mostly the writer's own)."""
    n, h = tp.n_records(seed["spec"]), len(seed.get("hint", ""))
    if n >= 10 and h >= 300:
        return "deep"
    if n >= 5 or (n >= 4 and h >= 300):
        return "medium"
    return "simple"


def _tidy(spec: dict) -> dict:
    """A relation end that is the bare word 'nonbinary' becomes 'person' (the gender word names the subject; 'nonbinary' is not a noun)."""
    for r in spec.get("relation", []) or []:
        for end in ("a", "b"):
            if r.get(end) == "nonbinary":
                r[end] = "person"
    return spec


def domain_for(spec: dict, rng, mix=DRAWN_DOMAINS) -> str:
    """The domain a spec's medium implies, else one drawn by the mix."""
    m = spec.get("form", {}).get("medium")
    for media, dom in ((PHOTO_MEDIA, "photograph"), (PAINT_MEDIA, "painting"), (SCULPT_MEDIA, "sculpture"),
                       (ILLUS_MEDIA, "illustration"), (DESIGN_MEDIA, "design")):
        if m in media:
            return dom
    names, p = zip(*mix)
    return str(rng.choice(names, p=p))


def _medium_in_mix(spec: dict, mix) -> bool:
    """A drawn spec whose medium implies a domain outside the batch's mix (a poster medium in a photograph-painting-illustration
    batch) is drawn again."""
    m = spec.get("form", {}).get("medium")
    allowed = {d for d, _ in mix}
    return all(dom in allowed for media, dom in ((PHOTO_MEDIA, "photograph"), (PAINT_MEDIA, "painting"), (SCULPT_MEDIA, "sculpture"),
                                                (ILLUS_MEDIA, "illustration"), (DESIGN_MEDIA, "design")) if m in media)


def row_license(seed: dict | None) -> str:
    if seed and any(seed["source"]["license"].startswith(a) for a in ATTRIBUTION_LICENSES):
        return seed["source"]["license"]
    return PERMISSIVE_ROW


def pictures_drawn(rows_dir: str, batch: int) -> set:
    """The pictures (picture_of) of every seed already drawn into another batch's specs under rows_dir and its sibling folders."""
    import glob
    out = set()
    parent = os.path.dirname(os.path.abspath(rows_dir))
    for f in glob.glob(os.path.join(parent, "*", "batch_*.specs.jsonl")):
        if os.path.basename(f) == f"batch_{batch:03d}.specs.jsonl":
            continue
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                it = json.loads(line)
                if it.get("seed_id"):
                    ds, _, sid = it["seed_id"].partition(":")
                    out.add(picture_of({"seed_id": it["seed_id"], "source": {"dataset": ds, "id": sid}}))
    return out


def draw(batch: int, n_series: int, n_singles: int, rows_dir: str, rng_seed: int | None = None, seeds=None,
         domains: dict | None = None, seed_series: bool = False) -> str:
    """Writes <rows_dir>/batch_BBB.specs.jsonl: n_series series of three nested specs and n_singles single specs (depth by the pilot
    mix). With `seeds` (seed files), every spec is a real seed's spec (a single row at the depth its record count fits, or the deep
    rank of a series whose medium and simple ranks are cut from it by the writer); without, specs are drawn by the tools'
    sampler from the training lists. -> the path."""
    import numpy as np
    assert 0 < batch < 1000 and 0 <= n_series < 100 and n_series * 3 + n_singles < 1000
    rng = np.random.default_rng(rng_seed if rng_seed is not None else 2026 * 1000 + batch)
    lists = tp.lists_for(HELD, "train")
    mix = tuple((d, float(w)) for d, w in (domains or {}).items()) or DRAWN_DOMAINS
    tot = sum(w for _, w in mix)
    mix = tuple((d, w / tot) for d, w in mix)
    pool, used = None, set()
    if seeds:
        pool = [s for s in read_seeds(seeds, held=False) if tp.n_records(s["spec"]) >= 2]
        rng.shuffle(pool)
        used = pictures_drawn(rows_dir, batch)                    # a picture seeds one row in the whole dataset, not one a batch

    def take(pred=lambda s: True):
        """The next seed of the pool that passes `pred` and whose picture is not in the batch yet (COCO captions and Localized
        Narratives describe the same pictures)."""
        for i in range(len(pool) - 1, -1, -1):
            s = pool[i]
            g = picture_of(s)
            if g not in used and pred(s):
                used.add(g)
                return pool.pop(i)
        raise ValueError("the seed pool ran out")

    out, k = [], 0
    for j in range(n_series):
        sid = f"s-{batch:03d}{j:02d}"
        if pool and seed_series:                                  # seeded series need deep-capable seeds; else drawn
            seed = take(lambda s: seed_depth(s) == "deep")
            specs = {"deep": seed["spec"]}
            item = dict(kind="series", series=sid, ids=[f"art-{batch:03d}{k + i:03d}" for i in range(3)], domain=seed["domain"],
                        genre=seed["genre"], specs=specs, seed_id=seed["seed_id"], hint=seed.get("hint", ""),
                        license=row_license(seed), note="the deep spec is the seed: keep every record; cut the medium and simple "
                                                         "specs from it as subsets")
        else:
            for _ in range(400):
                specs = tighten(tp.sample_series(rng, lists))
                if (nested(specs) and not any(incoherent(s) for s in specs.values()) and not thin(specs["simple"], "simple")
                        and not thin(specs["medium"], "medium") and tp.n_records(specs["deep"]) >= DEEP_MIN_DRAWN
                        and _medium_in_mix(specs["deep"], mix)):
                    break
            specs = {d: _tidy(s) for d, s in specs.items()}
            item = dict(kind="series", series=sid, ids=[f"art-{batch:03d}{k + i:03d}" for i in range(3)],
                        domain=domain_for(specs["deep"], rng, mix), genre=None, specs=specs, seed_id=None, license=PERMISSIVE_ROW)
        k += 3
        out.append(item)
    names, p = zip(*PILOT_DEPTHS)
    for j in range(n_singles):
        depth = str(rng.choice(names, p=p))
        if pool:
            seed = take()
            depth = seed_depth(seed)
            item = dict(kind="single", series=f"s-{batch:03d}{n_series + j:02d}" if n_series + j < 100 else None,
                        ids=[f"art-{batch:03d}{k:03d}"], depth=depth, domain=seed["domain"], genre=seed["genre"], spec=seed["spec"],
                        seed_id=seed["seed_id"], hint=seed.get("hint", ""), license=row_license(seed))
        else:
            for _ in range(400):
                spec = tighten({depth: tp.sample_spec(rng, depth, lists)})[depth]
                if (not incoherent(spec) and not thin(spec, depth) and _medium_in_mix(spec, mix)
                        and (depth != "deep" or tp.n_records(spec) >= DEEP_MIN_DRAWN)):
                    break
            spec = _tidy(spec)
            item = dict(kind="single", series=f"s-{batch:03d}{n_series + j:02d}" if n_series + j < 100 else None,
                        ids=[f"art-{batch:03d}{k:03d}"], depth=depth, domain=domain_for(spec, rng, mix), genre=None, spec=spec,
                        seed_id=None, license=PERMISSIVE_ROW)
        k += 1
        out.append(item)
    os.makedirs(rows_dir, exist_ok=True)
    path = os.path.join(rows_dir, f"batch_{batch:03d}.specs.jsonl")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for it in out:
            fh.write(json.dumps(it, ensure_ascii=True) + "\n")
    return path


_NAME = re.compile(r"(?<=[a-z,;:]\s)([A-Z][a-z]{2,})")


def possible_names(row: dict) -> list:
    """Capitalized words inside a sentence of the thoughts or wordings (a real person's name would show here; a place or a style
    name too): for review, not an error."""
    texts = [t.get("text", "") for t in row.get("thoughts", [])] + [str(v) for v in (row.get("wordings") or {}).values()]
    found = set()
    for t in texts:
        for w in _NAME.findall(t):
            if w not in core.COMMON_CAPS:
                found.add(w)
    return sorted(found)


def check_rows(rows_path: str, specs_path: str | None = None) -> dict:
    """The batch's report: per row the validator's problems and the curator's checks; the counts by rule; the warnings."""
    rows, unparsed = [], 0
    with open(rows_path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                unparsed += 1
    specs = {}
    if specs_path:
        with open(specs_path, encoding="utf-8") as fh:
            for line in fh:
                it = json.loads(line)
                for rid in it["ids"]:
                    specs[rid] = it
    problems, warnings, by_rule = [], [], Counter()
    m = re.search(r"batch_(\d{3})", os.path.basename(rows_path))
    batch = int(m.group(1)) if m else None
    ids = Counter(r.get("id") for r in rows)
    series = {}
    for r in rows:
        rid = r.get("id")
        for rule, msg in tp.validate(r, HELD):
            problems.append((rid, f"rule {rule}", msg))
            by_rule[f"rule {rule}"] += 1
        if ids[rid] > 1:
            problems.append((rid, "ids", "the id is used twice in the batch"))
            by_rule["ids"] += 1
        if batch is not None and not str(rid).startswith(f"art-{batch:03d}"):
            problems.append((rid, "ids", f"the id is outside batch {batch:03d}'s range (art-{batch:03d}KKK)"))
            by_rule["ids"] += 1
        it = specs.get(rid)
        if specs_path and it is None:
            problems.append((rid, "specs", "no spec of the batch allots this id"))
            by_rule["specs"] += 1
        if it is not None:
            want = it.get("license", PERMISSIVE_ROW)
            if (r.get("source") or {}).get("license") != want:
                problems.append((rid, "license", f"the row's license should be {want!r}"))
                by_rule["license"] += 1
            base = it["specs"]["deep"] if it["kind"] == "series" and it.get("seed_id") and r.get("depth") == "deep" else (
                it.get("spec") if it["kind"] == "single" else (it["specs"].get(r.get("depth")) if not it.get("seed_id") else None))
            if base is not None:
                have = set(tp.records(r.get("spec") or {}))
                lost = [kv for kv in tp.records(base) if kv not in have]
                if lost:
                    problems.append((rid, "spec kept", f"records of the given spec missing or changed: {lost[:4]}"))
                    by_rule["spec kept"] += 1
            if it.get("seed_id") and (r.get("source") or {}).get("seed_id") != it["seed_id"]:
                problems.append((rid, "source", f"a seeded row names its seed: seed_id {it['seed_id']!r}, kind 'seeded'"))
                by_rule["source"] += 1
        names = possible_names(r)
        if names:
            warnings.append((rid, "names?", names))
        if r.get("series"):
            series.setdefault(r["series"], []).append(r)
    for sid, rs in series.items():
        it = specs.get(rs[0].get("id")) if specs else None
        if (it is None or it["kind"] == "series") and len(rs) > 1:
            depths = sorted((int(x.get("rank", 0)), x.get("depth")) for x in rs)
            if depths != [(1, "simple"), (2, "medium"), (3, "deep")]:
                problems.append((sid, "series", f"a series holds ranks 1-3 = simple, medium, deep; it holds {depths}"))
                by_rule["series"] += 1
            for rule, msg in tp.validate_series(rs):
                problems.append((sid, f"rule {rule}", msg))
                by_rule[f"rule {rule}"] += 1
    if specs:
        missing = sorted(set(specs) - set(ids))
        if missing:
            problems.append(("batch", "missing", f"{len(missing)} allotted ids have no row: {missing[:6]}"))
            by_rule["missing"] += 1
    bad_rows = len({p[0] for p in problems if str(p[0]).startswith("art-")})
    return dict(rows=len(rows), unparsed=unparsed, rows_with_problems=bad_rows, by_rule=dict(by_rule), problems=problems,
                warnings=warnings, by_depth=dict(Counter(r.get("depth") for r in rows)),
                by_domain=dict(Counter(r.get("domain") for r in rows)))
