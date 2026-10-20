"""thought_seeds.core - the seed contract of the art thought dataset (AbstractPhil/thought-symbolic-image-captions).

A SEED is the hidden picture spec a generating model writes thought rows from: the FACTS of one picture in the systems trie of the
trainer's thought_pack (0.1.62 lists, seal(frac=0.1, seed=2026)), never mood, intent or story (the generating model adds those, the mood
with the record it is read from). One JSON object a line:

    {"seed_id": "<source>:<id>", "domain": "photograph|painting|illustration|sculpture|design", "genre": "<one or two words>",
     "spec": {system: {attribute: value}, "relation": [{"a", "rel", "b"}]}, "hint": "<optional source text, <= 600 bytes>",
     "source": {"dataset", "id", "license", "url"}, "held": true|false}

Every value is plain lower-case ASCII of at most 20 bytes, key + value at most 27 bytes (one 32-byte frame slice); a closed-list key
takes a value of its list; a seed whose records use a sealed value feeds the held split only. The trainer module is loaded from a
pinned clone (THOUGHT_TRAINER_REF), never from a working checkout."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import sys
import types
import unicodedata
from collections import Counter

TRAINER_REF = os.environ.get("THOUGHT_TRAINER_REF", r"X:\thought_seeds\trainer_ref\geolip\nano_beatrix")


def _load_thought_pack():
    name = "thought_seeds_tpref"
    if name not in sys.modules:
        pkg = types.ModuleType(name)
        pkg.__path__ = [TRAINER_REF]
        sys.modules[name] = pkg
    return importlib.import_module(f"{name}.thought_pack")


tp = _load_thought_pack()
assert tuple(int(x) for x in tp.VERSION.split(".")) >= (0, 1, 62), f"thought_pack {tp.VERSION}: the lists changed names at 0.1.62"
HELD = tp.seal()                                    # the seals of the 0.1.62 lists (final, Fable 2026-10-19)
KEYS = set(tp.keys())
DOMAINS = tp.DOMAINS
INTERPRETIVE = ("mood", "intent", "story")          # the generating model's systems: never in a seed
SEED_MAX_RECORDS = 24                               # the deep row holds 14-30 records; the model's mood / intent / story fill the rest
MAX_RELATIONS = 6
HINT_MAX = 600
HELD_PERCENT = 10                                   # of the seeds that use a sealed value, the share kept whole for the held split
REJECTED: Counter = Counter()                       # make_seed's rejections by first problem (the build prints them per source)


def clean(s) -> str:
    """A plain lower-case ASCII value: accents folded, punctuation to spaces (hyphen and apostrophe kept), spaces collapsed."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("_", " ")
    s = re.sub(r"[^a-z0-9 '\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -'")


def closed_list(key: str) -> list | None:
    name = tp.KEY_LIST.get(key)
    return tp.VOCAB[name] if name else None


class Spec:
    """A seed spec under construction: the first value set for a key wins unless overwrite; values outside a closed list, over the
    budget or past the record cap are dropped and counted (self.dropped)."""

    def __init__(self):
        self.d: dict = {}
        self.rels: list = []
        self.dropped: Counter = Counter()

    def n(self) -> int:
        return sum(len(a) for a in self.d.values()) + len(self.rels)

    def has(self, system: str, attr: str) -> bool:
        return attr in self.d.get(system, {})

    def set(self, system: str, attr: str, value, overwrite: bool = False) -> bool:
        key = f"{system} {attr}"
        if system in INTERPRETIVE:
            raise ValueError(f"{key}: a seed carries facts only (mood, intent, story are the generating model's)")
        if key not in KEYS or system == "relation":
            raise KeyError(f"{key} is not a key of the trie")
        v = clean(value)
        if not v:
            return False
        lst = closed_list(key)
        if lst is not None and v not in lst and v != "none":
            self.dropped[f"not in list: {key}"] += 1
            return False
        if len(v) > tp.VAL_MAX or len(key) + len(v) > tp.REC_MAX:
            self.dropped[f"over budget: {key}"] += 1
            return False
        if self.has(system, attr) and not overwrite:
            return False
        if not self.has(system, attr) and self.n() >= SEED_MAX_RECORDS:
            self.dropped["record cap"] += 1
            return False
        self.d.setdefault(system, {})[attr] = v
        return True

    def relate(self, a, rel: str, b) -> bool:
        a, b, rel = clean(a), clean(b), clean(rel)
        if rel not in tp.RELATIONS:
            self.dropped[f"relation not in list: {rel}"] += 1
            return False
        if not a or not b or a == b:
            return False
        key_len = len("rel9 a")
        if max(len(a), len(b)) > tp.VAL_MAX or key_len + max(len(a), len(b), len(rel)) > tp.REC_MAX:
            self.dropped["over budget: relation"] += 1
            return False
        r = {"a": a, "rel": rel, "b": b}
        if r in self.rels:
            return False
        if len(self.rels) >= MAX_RELATIONS or self.n() >= SEED_MAX_RECORDS:
            self.dropped["relation cap"] += 1
            return False
        self.rels.append(r)
        return True

    def spec(self) -> dict:
        out = {s: dict(a) for s, a in self.d.items() if a}
        if self.rels:
            out["relation"] = [dict(r) for r in self.rels]
        return out


def check_spec(spec: dict) -> list:
    """The spec's problems (empty when it passes): rule 2 of the row validator on the records, no interpretive system, the record
    count. The whole seed then passes the trainer's own gate, thought_pack.validate_seed (0.1.64), in make_seed."""
    p = []
    for system, attrs in spec.items():
        if system in INTERPRETIVE:
            p.append(f"interpretive system {system!r} in a seed")
        elif system == "relation":
            for r in attrs or []:
                if not isinstance(r, dict) or set(r) != {"a", "rel", "b"}:
                    p.append(f"a relation needs exactly a, rel, b: {r!r}")
                elif r["rel"] not in tp.RELATIONS:
                    p.append(f"relation {r['rel']!r} not in the list")
        elif system not in tp.SYSTEMS:
            p.append(f"unknown system {system!r}")
        else:
            for a in attrs:
                if f"{system} {a}" not in KEYS:
                    p.append(f"unknown key {system} {a}")
    for k, v in tp.records(spec):
        if not isinstance(v, str) or not v or v != clean(v):
            p.append(f"value of {k!r} is not plain lower-case ASCII: {v!r}")
        elif len(v) > tp.VAL_MAX or len(k) + len(v) > tp.REC_MAX:
            p.append(f"record {k!r} = {v!r} over the budget")
        if len(k) > tp.KEY_MAX:
            p.append(f"key {k!r} over {tp.KEY_MAX} bytes")
        lst = closed_list(k)
        if lst is not None and v not in lst and v != "none":
            p.append(f"value of {k!r} not in its closed list: {v!r}")
    n = tp.n_records(spec)
    if not 1 <= n <= SEED_MAX_RECORDS:
        p.append(f"{n} records (a seed holds 1-{SEED_MAX_RECORDS})")
    return p


def sealed(spec: dict) -> list:
    return tp.sealed_used(tp.records(spec), HELD)


def strip_sealed(spec: dict) -> dict:
    """The spec without every record whose value is sealed (a relation goes whole when its rel or an end is sealed)."""
    out = {}
    for system, attrs in spec.items():
        if system == "relation":
            keep = []
            for i, r in enumerate(attrs, 1):
                recs = [(f"rel{i} a", r["a"]), (f"rel{i} rel", r["rel"]), (f"rel{i} b", r["b"])]
                if not tp.sealed_used(recs, HELD):
                    keep.append(r)
            if keep:
                out["relation"] = keep
        else:
            kept = {a: v for a, v in attrs.items() if not tp.sealed_used([(f"{system} {a}", v)], HELD)}
            if kept:
                out[system] = kept
    return out


def held_pick(seed_id: str, percent: int = HELD_PERCENT) -> bool:
    """A stable draw by the seed's id: the seeds that use a sealed value and fall in this share stay whole for the held split."""
    return int(hashlib.sha1(seed_id.encode("utf-8")).hexdigest()[:8], 16) % 100 < percent


def route(seed_id: str, spec: dict) -> tuple:
    """-> (spec, held). A spec without sealed values is a training seed; with them, a stable tenth stays whole as a held seed and
    the rest lose the sealed records (a training row never carries a sealed value)."""
    if not sealed(spec):
        return spec, False
    if held_pick(seed_id):
        return spec, True
    return strip_sealed(spec), False


def ascii_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip()


_SENT = re.compile(r"(?<=[.!?])\s+")
_CAP = re.compile(r"\b[A-Z][a-z]+")
COMMON_CAPS = {"I", "The", "A", "An", "In", "On", "At", "This", "That", "These", "Those", "It", "Its", "He", "She", "They", "We",
               "His", "Her", "Their", "There", "Here", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
               "Behind", "Above", "Below", "To", "From", "With", "Without", "Under", "Over", "Near", "Next", "Left", "Right", "Front",
               "Back", "Top", "Bottom", "Center", "Centre", "Middle", "Several", "Many", "Some", "Each", "Both", "All", "Most",
               "Inside", "Outside", "Beside", "Between", "Along", "Across", "Around", "As", "And", "But", "Or", "If", "When",
               "While", "After", "Before", "During", "For", "Of", "By", "Is", "Are", "Was", "Were", "Be", "No", "Not", "Only",
               "Also", "Then", "Now", "Today", "Close", "Far", "Large", "Small", "Big", "Little", "Old", "New", "Young",
               "Black", "White", "Red", "Blue", "Green", "Yellow", "Brown", "Grey", "Gray", "Orange", "Pink", "Purple"}


def drop_named(text: str, allow: set | None = None) -> str:
    """The text without every sentence that holds a capitalized word past its first word (a name of a person, a place, a brand or a
    title: the dataset carries no real person's name, so a sentence that may hold one is dropped whole). `allow`: extra capitalized
    words that are not names in this source (a museum's 'Virgin' is a name and is not allowed)."""
    ok = COMMON_CAPS | (allow or set())
    keep = []
    for s in _SENT.split(str(text).strip()):
        words = s.split()
        caps = [w for w in _CAP.findall(" ".join(words[1:]))]
        if all(c in ok for c in caps):
            keep.append(s)
    return " ".join(keep)


def make_hint(parts, limit: int = HINT_MAX) -> str:
    """The hint: source sentences, each once, ASCII, joined and cut at a sentence boundary within `limit` bytes."""
    out, seen = [], set()
    for p in parts:
        t = ascii_text(p)
        if not t:
            continue
        if t[-1] not in ".!?":
            t += "."
        key = t.lower()
        if key in seen:
            continue
        if len(" ".join(out + [t])) > limit:
            if not out:                                     # a single long text: cut at the last sentence end inside the limit
                cut = t[:limit]
                j = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
                if j > limit // 3:
                    out.append(cut[:j + 1])
            break
        seen.add(key)
        out.append(t)
    return " ".join(out)


def make_seed(dataset: str, sid: str, domain: str, genre: str, spec: Spec | dict, hint: str, license: str, url: str,
              min_records: int = 1) -> dict | None:
    """The seed object (the contract's fields), routed by the seal; None when the spec is empty or fails the checks."""
    if domain not in DOMAINS:
        raise ValueError(f"domain {domain!r}")
    seed_id = f"{dataset}:{sid}"
    raw = spec.spec() if isinstance(spec, Spec) else spec
    s, held = route(seed_id, raw)
    if tp.n_records(s) < min_records:
        REJECTED["too few records"] += 1
        return None
    probs = check_spec(s)
    if probs:
        REJECTED[f"spec: {probs[0]}"[:90]] += 1
        return None
    out = {"seed_id": seed_id, "domain": domain, "genre": clean(genre)[:24] or domain, "spec": s}
    if hint:
        out["hint"] = hint[:HINT_MAX]
    out["source"] = {"dataset": dataset, "id": str(sid), "license": license, "url": url}
    out["held"] = held
    if hasattr(tp, "validate_seed"):                 # the trainer's gate (0.1.64): the contract, the license, the seal
        probs = list(tp.validate_seed(out, HELD))
        if probs:
            REJECTED[f"gate: {probs[0]}"[:90]] += 1
            return None
    return out


class Shards:
    """seeds/<source>/<source>-NNNNN.jsonl under `root`, `size` lines a shard, plus seeds/<source>/stats.json on close."""

    def __init__(self, root: str, source: str, size: int = 10000):
        self.dir = os.path.join(root, "seeds", source)
        os.makedirs(self.dir, exist_ok=True)
        self.source, self.size = source, size
        self.n, self.fh, self.shard = 0, None, -1
        self.stats = dict(seeds=0, held=0, by_domain=Counter(), by_genre=Counter(), records=Counter(), keys=Counter(),
                          with_hint=0, relations=0)

    def add(self, seed: dict) -> None:
        if self.n % self.size == 0:
            if self.fh:
                self.fh.close()
            self.shard += 1
            self.fh = open(os.path.join(self.dir, f"{self.source}-{self.shard:05d}.jsonl"), "w", encoding="utf-8", newline="\n")
        self.fh.write(json.dumps(seed, ensure_ascii=True, separators=(",", ":")) + "\n")
        self.n += 1
        st = self.stats
        st["seeds"] += 1
        st["held"] += bool(seed["held"])
        st["by_domain"][seed["domain"]] += 1
        st["by_genre"][seed["genre"]] += 1
        st["records"][tp.n_records(seed["spec"])] += 1
        st["with_hint"] += bool(seed.get("hint"))
        st["relations"] += len(seed["spec"].get("relation", []))
        for k, _ in tp.records(seed["spec"]):
            st["keys"][re.sub(r"^rel\d+ ", "rel ", k)] += 1

    def close(self, extra: dict | None = None) -> dict:
        if self.fh:
            self.fh.close()
        st = dict(self.stats)
        for k in ("by_domain", "records", "keys"):
            st[k] = dict(sorted(st[k].items(), key=lambda kv: (-kv[1], str(kv[0])) if k != "records" else (kv[0], 0)))
        st["by_genre"] = dict(st["by_genre"].most_common(40))
        st["shards"] = self.shard + 1
        st["thought_pack"] = tp.VERSION
        if extra:
            st.update(extra)
        with open(os.path.join(self.dir, "stats.json"), "w", encoding="utf-8") as fh:
            json.dump(st, fh, indent=1)
        return st
