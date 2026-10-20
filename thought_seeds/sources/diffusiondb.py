"""thought_seeds.sources.diffusiondb - DiffusionDB 2M prompts (Wang et al., CC0 1.0) as hidden picture specs.

The source: metadata.parquet at the root of the Hugging Face dataset poloclub/diffusiondb (2,000,000 Stable Diffusion images from the
official Discord server, their prompts and NSFW scores). Only three columns are read, over HTTP range requests: prompt, prompt_nsfw
(the maximum of Detoxify's toxicity and sexual_explicit scores) and image_nsfw (LAION's image detector; 2.0 = flagged and blurred).
No image, no user hash, no timestamp is downloaded.

A prompt becomes a seed when it survives, in order: the NSFW filter (any of its images with prompt_nsfw >= 0.2 or image_nsfw >= 0.5,
or an explicit word), the name strip (every 'by <name>', 'in the style of <name>', 'art by', platform and resolution words; every
comma segment that holds a name-like word, learned from the corpus itself: the words that follow 'by', and the words writers
capitalize in the middle of a prompt far more often than common words; then core.drop_named), and a length floor (four words left).
The surviving text's words give the records through the shared prompt parser (thought_seeds.textspec), and a record whose value is
open (the thing's name, a relation's ends) is kept only when it is a word of a known object vocabulary (the parser's object words
and the COCO category names), so no name, brand or character can be a record's value.

A DiffusionDB seed carries NO hint: people type names in lower case as often as not, so no name filter over this corpus can be
trusted with its text. Prompts are deduplicated twice: as written, and as cleaned (the text the records are read from)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import Counter
from typing import Iterator

from .. import core, maps, textspec

DATASET = "diffusiondb"
LICENSE = "CC0 1.0"
URL = "https://huggingface.co/datasets/poloclub/diffusiondb"
ATTRIBUTION = ("DiffusionDB (Wang, Montoya, Munechika, Yang, Hoover and Chau, Georgia Tech Polo Club), the 2M subset's prompts and "
               "NSFW scores, under CC0 1.0")
CITATION = """@article{wangDiffusionDBLargescalePrompt2022,
  title   = {{{DiffusionDB}}: {{A}} Large-Scale Prompt Gallery Dataset for Text-to-Image Generative Models},
  author  = {Wang, Zijie J. and Montoya, Evan and Munechika, David and Yang, Haoyang and Hoover, Benjamin and Chau, Duen Horng},
  year    = {2022},
  journal = {arXiv:2210.14896 [cs]},
  url     = {https://arxiv.org/abs/2210.14896}
}"""
TAKEN = ("records only, no hint: the prompt text of the 2M subset read through the closed-list maps and a fixed object vocabulary "
         "(thing names and relation ends only from the parser's object words and the COCO category names; segments that hold a "
         "name-like word learned from the corpus dropped before the read); the prompt text itself is not shipped; prompt_nsfw and "
         "image_nsfw used only to drop prompts")
REPO = "poloclub/diffusiondb"
FILE = "metadata.parquet"
COLUMNS = ["prompt", "prompt_nsfw", "image_nsfw"]
PROMPT_NSFW_MAX = 0.2
IMAGE_NSFW_MAX = 0.5
MIN_WORDS = 4


def fetch(raw_dir: str) -> dict:
    """prompts.parquet: the three columns of metadata.parquet, read by column over HTTP range requests (about 100 MB of the
    file's 195 MB); source.json: the revision read."""
    import pyarrow.parquet as pq
    from huggingface_hub import HfApi, HfFileSystem
    d = os.path.join(raw_dir, DATASET)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, "prompts.parquet")
    meta = os.path.join(d, "source.json")
    if not os.path.exists(out):
        sha = HfApi(token=False).dataset_info(REPO).sha
        fs = HfFileSystem(token=False)
        t0 = time.time()
        with fs.open(f"datasets/{REPO}@{sha}/{FILE}", "rb", block_size=8 * 2 ** 20) as fh:
            pf = pq.ParquetFile(fh)
            tables = []
            for rg in range(pf.num_row_groups):
                tables.append(pf.read_row_group(rg, columns=COLUMNS))
                print(f"[diffusiondb] row group {rg + 1}/{pf.num_row_groups} read, {time.time() - t0:.0f} s", flush=True)
        import pyarrow as pa
        table = pa.concat_tables(tables)
        pq.write_table(table, out + ".part", compression="zstd")
        os.replace(out + ".part", out)
        with open(meta, "w", encoding="utf-8") as fh:
            json.dump({"repo": REPO, "file": FILE, "revision": sha, "columns": COLUMNS, "rows": table.num_rows,
                       "url": f"https://huggingface.co/datasets/{REPO}/blob/{sha}/{FILE}"}, fh, indent=1)
    card = os.path.join(d, "README.md")                      # the dataset card: the license and the citation, kept as provenance
    if not os.path.exists(card):
        with open(card + ".part", "wb") as fh:
            fh.write(HfFileSystem(token=False).cat_file(f"datasets/{REPO}/README.md"))
        os.replace(card + ".part", card)
    return {"prompts.parquet": os.path.getsize(out), "source.json": os.path.getsize(meta), "README.md": os.path.getsize(card)}


# ------------------------------------------------------------------ cleaning: names, platforms, boilerplate
SEGMENT = re.compile(r"[,;|\n]+|\s+-\s+|[()\[\]{}]|::|\s\|\s")
# this corpus writes a hyphen with a space on each side ('spider - man', 'photo - realistic', 'award - winning', 'trs - 8 0'): the
# halves are joined back before the prompt is cut into segments, so a hyphenated word stays one word
SPACED_HYPHEN = re.compile(r"(?<=[A-Za-z0-9']) - (?=[A-Za-z0-9])")
SEGMENTER = 2           # the version of segments(): the learned name list is rebuilt when it changes
FLAGS = re.compile(r"--\w+(?:\s+[\w:.]+)?|:\s*\d+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\s*:\s*\d+\b")
TOKEN = re.compile(r"[A-Za-z][A-Za-z'\-]*")
DETERMINERS = {"the", "a", "an", "his", "her", "their", "its", "my", "your", "our", "this", "that", "these", "those", "some", "night",
               "day", "moonlight", "candlelight", "sunlight", "firelight", "lantern", "hand", "itself", "himself", "herself"}
BY_PHRASE = re.compile(r"\b(?:by|art by|painted by|drawn by|illustrated by|photographed by|photo by|artwork by|style by|inspired by|"
                       r"in the style of|in style of|style of|in the manner of|influenced by|after the style of)\s+(.*)$")
PLATFORM = re.compile(r"\b(trending|tranding|artstation|art station|cgsociety|cg society|deviantart|deviant art|behance|pixiv|pxiv|"
                      r"pixv|fanbox|weasyl|furaffinity|unsplash|500px|high resolution|resolution|rtx|"
                      r"flickr|instagram|reddit|pinterest|zbrush central|polycount|sketchfab|featured on|award[- ]winning|"
                      r"masterpiece|hq|uhd|hdr|\d+k|\d{3,4}p|8 k|4 k|highly detailed|ultra detailed|very detailed|intricate details?|"
                      r"insanely detailed|hyper detailed|hyperdetailed|ultra realistic|ultra-realistic|trending now|nft|opensea)\b")
STOPWORDS = set("""a an the of in on at to and or with without for from by as is are was were be been being it its this that these those
his her their our your my we you they he she i me him them who whom which what when where while into onto over under above below behind
between through across around near next very more most much many some any all each every both few several no not only also just than
then so such too up down out off again further once here there about against during before after same other another own""".split())
ACRONYMS = {"ISO", "DSLR", "SLR", "HD", "HDR", "RAW", "UHD", "PBR", "CGI", "VR", "AI", "UV", "LED", "RGB", "DOF", "TV", "UFO", "LCD",
            "GPU", "CPU", "USB", "BW", "IMAX", "VHS", "DVD", "CD", "NFT", "RPG", "FPS", "UI", "UX", "SFX", "VFX"}
NATIONAL = set("""japanese chinese korean french english british american african indian italian greek roman egyptian russian mexican
spanish german nordic norse viking celtic persian arabic arabian aztec mayan victorian edwardian elizabethan medieval gothic baroque
renaissance rococo byzantine soviet scandinavian dutch flemish polish irish scottish tibetan thai vietnamese brazilian peruvian
hawaiian polynesian moroccan turkish ottoman mongolian siberian alpine tropical mediterranean""".split())


def _safe_words() -> set:
    """Words that are never names in this source: the words of every closed-list phrase, the parser's nouns and person words, the
    stopwords, the nationality and period adjectives."""
    safe = set(STOPWORDS) | NATIONAL
    for mapping in list(maps.ALL.values()) + [maps.RELATION, textspec.EXPRESSION, textspec.PERSON_EXTRA]:
        for phrase in mapping:
            safe.update(TOKEN.findall(phrase.lower()))
    for form in list(textspec.NOUNS) + list(textspec.PERSON_WORDS):
        safe.update(TOKEN.findall(form))
    safe.update("unreal engine octane render blender painting drawing sketch art artwork illustration photo photography portrait "
                "landscape digital concept style detailed realistic cinematic lighting dramatic beautiful cute epic dark light colorful "
                "colourful vibrant soft sharp focus symmetrical centered full body face eyes hair skin smooth".split())
    return safe


def _parts(words: list) -> list:
    """Every word and every hyphen / apostrophe part of it ("<name>'s" -> <name>, '<name>-like' -> <name>, like), so a name
    inside a compound is still a name."""
    out = []
    for w in words:
        out.append(w)
        if "-" in w or "'" in w:
            out += [p for p in re.split(r"['\-]", re.sub(r"'s$", "", w)) if p]
    return out


def segments(prompt: str) -> list:
    """The prompt's comma (and bracket, bar, dash) segments, its spaced hyphens joined back first."""
    return [s.strip() for s in SEGMENT.split(FLAGS.sub(" ", SPACED_HYPHEN.sub("-", core.ascii_text(prompt)))) if s.strip()]


def strip_segment(seg: str, names: set = frozenset()) -> str:
    """One comma segment (lower case) without its 'by <name>' / 'in the style of <name>' tail, its platform and resolution words.
    A tail is kept when it names nobody: 'surrounded by flowers', 'lit by a lantern' (a bare 'by' after a word that is not an
    artist's verb, with no name-like word in the tail); a tail that names a closed-list style or medium leaves that word."""
    low = seg.lower()
    m = BY_PHRASE.search(low)
    if m:
        tail = m.group(1).strip()
        words = TOKEN.findall(tail)
        trigger = low[m.start():m.start(1)].strip()
        before = TOKEN.findall(low[:m.start()])
        named = any(w in names or w in NAMES_BACKSTOP for w in _parts(words))
        agent = trigger == "by" and bool(before) and before[-1] not in ARTIST_VERBS and bool(words) and words[0] not in ARTIST_VERBS
        if named or not (agent or (words and words[0] in DETERMINERS)):
            keep = low[:m.start()].strip()
            style = maps.first(tail, maps.STYLE) or maps.first(tail, maps.MEDIUM)
            low = (keep + " " + style).strip() if style else keep
    low = re.sub(r"\s+", " ", PLATFORM.sub(" ", low)).strip(' "')             # a quote around a segment is no part of it
    low = re.sub(r"\b(on|by|in|of|at|and|with)\s*$", "", low).strip(" -'\"")
    return low


def clean_prompt(prompt: str, names: set, totals: Counter, safe: set, pairs: set = frozenset()) -> str:
    """The prompt as a hint: every segment stripped of its name tail and platform words; a segment dropped whole when it still holds
    a name-like word, a name pair, a backstop name, an unknown word (written fewer than NAME_MIN times in the corpus), or, by
    core.drop_named, a capitalized word that is not a common word of the corpus. Lower case, segments joined by commas."""
    out = []
    for seg in segments(prompt):
        low = strip_segment(seg, names)
        if not low:
            continue
        words = TOKEN.findall(low)
        parts = _parts(words)
        if not words or any(w in names or w in NAMES_BACKSTOP for w in parts) or \
                any(w not in safe and totals.get(w, 0) < NAME_MIN for w in words):
            continue
        if any(f"{a} {b}" in pairs for a, b in zip(parts, parts[1:])):
            continue
        cased = [t for t in TOKEN.findall(seg) if t.lower() in set(words)]
        allow = {t for t in cased if t[:1].isupper() and not t.isupper() and t.lower() not in names} | ACRONYMS
        if not core.drop_named(" ".join(cased), allow=allow):
            continue                                  # an all-capitals word other than a known acronym: a name ('KEROUAC')
        out.append(low)
    text = ", ".join(dict.fromkeys(out))
    return re.sub(r"\s+", " ", textspec.norm_digits(text)).strip(" ,")


GENRE_TEXT = [(r"\bself[- ]portrait\b", "self portrait"), (r"\bportrait\b", "portrait"), (r"\bstill life\b", "still life"),
              (r"\bcityscape|city skyline|skyline\b", "cityscape"), (r"\bseascape\b", "seascape"), (r"\blandscape\b", "landscape"),
              (r"\binterior\b", "interior"), (r"\barchitectur", "architecture"), (r"\bfood photography\b", "food"),
              (r"\bfashion\b", "fashion"), (r"\bproduct (?:photo|shot|render|design)", "product"), (r"\bconcept art\b", "concept art"),
              (r"\bcharacter (?:design|concept|sheet)", "character design"), (r"\bposter\b", "poster"), (r"\blogo\b", "logo"),
              (r"\bbotanical\b", "botanical"), (r"\bwildlife\b", "wildlife"), (r"\bmacro\b", "macro"),
              (r"\bstreet photography\b", "street"), (r"\bsports?\b", "sport"), (r"\b(?:war|battle|battlefield)\b", "war"),
              (r"\babstract\b", "abstract"), (r"\b(?:album|book) cover\b", "cover art"), (r"\bmap\b", "map")]


def genre_of(t: str, info: dict) -> str:
    for pat, g in GENRE_TEXT:
        if re.search(pat, t):
            return g
    if info.get("persons"):
        return "figure"
    if info.get("animal"):
        return "animal"
    if info.get("thing"):
        return "object"
    return "scene"


def name_settings(safe: set) -> dict:
    """The settings the learned name list depends on: the ratios, the floor, the segmenter's version and the safe words (a hash).
    A kept name_words.json whose settings differ is learned again."""
    return {"cap_ratio": CAP_RATIO, "by_ratio": BY_RATIO, "list_ratio": LIST_RATIO, "pair_ratio": PAIR_RATIO, "name_min": NAME_MIN,
            "segmenter": SEGMENTER, "safe_words": hashlib.sha1(" ".join(sorted(safe)).encode("utf-8")).hexdigest()[:16]}


def _names(raw: str, prompts) -> tuple:
    """(name-like words, name pairs, word totals): learned from the corpus, kept as name_words.json beside the prompts, and learned
    again when the kept file's settings are not the module's (name_settings)."""
    path = os.path.join(raw, "name_words.json")
    safe = _safe_words()
    settings = name_settings(safe)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            j = json.load(fh)
        if all(j.get(k) == v for k, v in settings.items()):
            return set(j["names"]), set(j["pairs"]), Counter(j["totals"])
        print(f"[diffusiondb] {path}: learned with other settings, learning the name list again", flush=True)
    t0 = time.time()
    st = word_stats(prompts, safe)
    first = name_words(st, safe)
    names = name_words(st, safe, listed_counts(prompts, first, safe))
    pairs = name_pairs(prompts, safe)
    totals = {w: n for w, n in st["total"].items() if n >= NAME_MIN}
    with open(path + ".part", "w", encoding="utf-8") as fh:
        json.dump({**settings, "names": sorted(names), "pairs": sorted(pairs), "totals": totals}, fh)
    os.replace(path + ".part", path)
    print(f"[diffusiondb] name list learned: {len(names)} words, {len(pairs)} pairs, {time.time() - t0:.0f} s", flush=True)
    return names, pairs, Counter(totals)


def known_things() -> set:
    """The words an open record's value may take in this source: the parser's object words and the COCO category names."""
    from . import coco
    return {w for w, _, _ in textspec.NOUNS.values()} | {name for name, _ in coco.CATS.values()}


def known_ends() -> set:
    """The words a relation's end may take: the known things, the gender words and the parser's person words."""
    persons = set(textspec.PERSON_WORDS) | {w[:-1] for w in textspec.PERSON_WORDS if w.endswith("s") and not w.endswith("ss")}
    return known_things() | set(core.closed_list("person gender")) | persons


def vocab_only(spec: dict, things: set, ends: set) -> dict:
    """The spec without an open record whose value is outside the known vocabularies: the thing goes whole when its name is
    unknown, a relation goes when an end is unknown."""
    out = {k: (dict(v) if isinstance(v, dict) else [dict(r) for r in v]) for k, v in spec.items()}
    if "thing" in out and out["thing"].get("name") not in things:
        del out["thing"]
    if "relation" in out:
        out["relation"] = [r for r in out["relation"] if r["a"] in ends and r["b"] in ends]
        if not out["relation"]:
            del out["relation"]
    return out


_KNOWN: dict = {}


def build(sid: str, prompt: str, names: set, totals: Counter, safe: set, pairs: set = frozenset(),
          text: str | None = None) -> dict | None:
    """One prompt's seed, records only (no hint), or None (an explicit word, fewer than four words left after the name strip, or
    no record). `text`: the prompt as clean_prompt cleans it, when the caller already has it."""
    if textspec.is_explicit(prompt):
        return None
    if text is None:
        text = clean_prompt(prompt, names, totals, safe, pairs)
    if len(text.split()) < MIN_WORDS or textspec.is_explicit(text):
        return None
    s, info = textspec.spec_from_text(text)
    if not s.n():
        return None
    if not _KNOWN:
        _KNOWN.update(things=known_things(), ends=known_ends())
    spec = vocab_only(textspec.finish(DATASET, sid, s), _KNOWN["things"], _KNOWN["ends"])
    if not spec:
        return None
    return core.make_seed(DATASET, sid, textspec.domain_of(text), genre_of(text, info), spec, "", LICENSE, URL)


def seeds(raw_dir: str, limit: int | None = None) -> Iterator[dict]:
    """The distinct prompts in a stable shuffled order (by the hash of the folded prompt), the NSFW-flagged ones dropped, the cleaned
    texts deduplicated (two prompts that read the same once cleaned give one seed); the seed id is the first 16 hex digits of that
    hash."""
    raw = os.path.join(raw_dir, DATASET)
    prompts = unique_prompts(raw_dir)
    names, pairs, totals = _names(raw, prompts)
    safe = _safe_words()
    order = sorted(((hashlib.sha1(k.encode("utf-8")).hexdigest()[:16], p, pn, im) for k, p, pn, im in prompts))
    del prompts
    seen = set()
    n = 0
    for sid, p, pn, im in order:
        if limit is not None and n >= limit:
            return
        if pn >= PROMPT_NSFW_MAX or im >= IMAGE_NSFW_MAX:
            continue
        text = clean_prompt(p, names, totals, safe, pairs)
        key = hashlib.sha1(text.encode("utf-8")).digest()[:10]
        if key in seen:
            continue                                  # the same text once cleaned: the same records
        seed = build(sid, p, names, totals, safe, pairs, text=text)
        if not seed:
            continue
        seen.add(key)
        n += 1
        yield seed


def unique_prompts(raw_dir: str) -> list:
    """[(key, prompt, prompt_nsfw max, image_nsfw max)] per distinct prompt (whitespace and case folded), in file order."""
    import pyarrow.parquet as pq
    t = pq.read_table(os.path.join(raw_dir, DATASET, "prompts.parquet"), columns=COLUMNS)
    seen: dict = {}
    out = []
    for p, pn, im in zip(t.column("prompt").to_pylist(), t.column("prompt_nsfw").to_pylist(), t.column("image_nsfw").to_pylist()):
        if not p:
            continue
        key = re.sub(r"\s+", " ", p.strip().lower())
        pn = 1.0 if pn is None else float(pn)
        im = 0.0 if im is None else float(im)
        j = seen.get(key)
        if j is None:
            seen[key] = len(out)
            out.append([key, p.strip(), pn, im])
        else:
            out[j][2] = max(out[j][2], pn)
            out[j][3] = max(out[j][3], im)
    return [tuple(x) for x in out]


def word_stats(prompts, safe: set) -> dict:
    """Per lower-case word over the distinct prompts: how often it is written, how often capitalized past a segment's first word,
    how often inside a 'by <name>' tail, and how often in a short segment continuing that tail's list ('by <name> <name>,
    <name>, <name> <name>': a segment of at most three words, none of them a safe word)."""
    total, caps, mid, by, cont = Counter(), Counter(), Counter(), Counter(), Counter()
    for _, p, _, _ in prompts:
        in_by = False
        for seg in segments(p):
            toks = TOKEN.findall(seg)
            for k, tok in enumerate(toks):
                w = tok.lower()
                total[w] += 1
                if k:
                    mid[w] += 1
                    if tok[0].isupper():
                        caps[w] += 1
            low = [t.lower() for t in toks]
            m = BY_PHRASE.search(seg.lower())
            if m:
                tail = m.group(1).split()
                if tail and tail[0] not in DETERMINERS:
                    for w in TOKEN.findall(" ".join(tail[:6]).lower()):
                        by[w] += 1
                    in_by = True
                    continue
            if in_by and 0 < len(low) <= 3 and not any(w in safe for w in low):
                for w in low:
                    cont[w] += 1
                continue
            in_by = False
    return {"total": total, "caps": caps, "mid": mid, "by": by, "cont": cont}


def listed_counts(prompts, names: set, safe: set) -> Counter:
    """Per word: how often it fills a short segment (at most three words, none safe) next to a segment that holds a name-like
    word: the artist lists written without 'by' ('<name> ornamentation, <name> <name>, <name> <name>')."""
    listed = Counter()
    for _, p, _, _ in prompts:
        toks = [[t.lower() for t in TOKEN.findall(s)] for s in segments(p)]
        for i, ws in enumerate(toks):
            if 0 < len(ws) <= 3 and not any(w in safe for w in ws):
                around = (toks[i - 1] if i else []) + (toks[i + 1] if i + 1 < len(toks) else [])
                if any(w in names for w in around):
                    for w in ws:
                        listed[w] += 1
    return listed


NAME_MIN = 5            # a word must be written this often before its statistics decide; rarer words are unknown (segment dropped)
CAP_RATIO = 0.15        # capitalized past a segment's first word in this share of those places: a name-like word (measured on
                        # the 2M subset: common words stay at or under about 0.10; first names of public figures .22 to .31; an
                        # artist's first name .12, caught by its .64 inside 'by' tails)
BY_RATIO = 0.15         # inside a 'by <name>' tail in this share of its uses: a name-like word (an artist's or a studio's name
                        # about .20)
LIST_RATIO = 0.5        # in an artist list (after a 'by' tail, or beside a name) in this share of its uses (a listed artist's
                        # name about .90)
NAMES_BACKSTOP = set("""napoleon cleopatra caesar shakespeare mozart beethoven bach gandhi stalin lenin mao churchill elvis madonna
buddha muhammad mohammed confucius socrates plato aristotle hitler jesus christ moses musk trump obama biden putin""".split())
                        # famous single names the statistics may miss (one sits at a capital share of .14); never a name
                        # that is also a common noun
ARTIST_VERBS = {"art", "painted", "drawn", "illustrated", "photographed", "photo", "artwork", "style", "inspired", "influenced",
                "made", "created", "designed", "rendered", "sculpted", "directed", "shot", "painting", "drawing", "illustration",
                "portrait", "sketch", "poster", "cover", "concept"}


PAIR_RATIO = 0.2        # two words written Title Case together in this share of their uses: a name made of two common words


def name_pairs(prompts, safe: set) -> set:
    """Word pairs written Title Case together in at least PAIR_RATIO of their uses (at least NAME_MIN uses): names made of common
    words. A pair of two safe words ('unreal engine', 'golden gate') or with a stopword is never one."""
    capped = Counter()
    for _, p, _, _ in prompts:
        for seg in segments(p):
            toks = TOKEN.findall(seg)
            for a, b in zip(toks, toks[1:]):
                if a[0].isupper() and b[0].isupper():
                    capped[(a.lower(), b.lower())] += 1
    cand = {k for k, n in capped.items() if n >= 3 and not (k[0] in safe and k[1] in safe)
            and k[0] not in STOPWORDS and k[1] not in STOPWORDS}
    total = Counter()
    for _, p, _, _ in prompts:
        for seg in segments(p):
            low = [t.lower() for t in TOKEN.findall(seg)]
            for k in zip(low, low[1:]):
                if k in cand:
                    total[k] += 1
    return {f"{a} {b}" for (a, b) in cand if total[(a, b)] >= NAME_MIN and capped[(a, b)] / total[(a, b)] >= PAIR_RATIO}


def name_words(stats: dict, safe: set, listed: Counter | None = None) -> set:
    """The name-like words: capitalized mid-prompt (CAP_RATIO), inside 'by' tails (BY_RATIO), continuing a 'by' list or listed
    beside names (LIST_RATIO); safe words never."""
    out = set()
    for w, n in stats["total"].items():
        if w in safe or n < NAME_MIN or len(w) < 2:
            continue
        mid = stats["mid"][w]
        if ((mid >= NAME_MIN and stats["caps"][w] / mid >= CAP_RATIO) or stats["by"][w] / n >= BY_RATIO
                or stats["cont"][w] / n >= LIST_RATIO or (listed is not None and listed[w] / n >= LIST_RATIO)):
            out.add(w)
    return out
