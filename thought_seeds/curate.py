"""Curating written rows between the writer and a release: detectors for the faults a read by eye finds, the acceptance read of a
range of batches, patches to row files that are checked before anything is written, the audit of a release, and seed pools that
give each batch a known mix of sources.

The detectors read; the eye decides. Every hit is shown, and a false hit costs less than a missed fault.
  gloss   a thought that defines a word instead of looking at the picture: 'Robe: a long, loose outer garment.', 'A sink is a fixed
          basin with a tap.', 'Turquoise is a blue-green.' A sentence that opens on a term and then observes this picture
          ('Backlit: the lamps sit behind her') is not one, and neither is an observation shaped like one ('Neon is the main light').
  remark  a thought about the writing or the specification instead of the picture: 'an inference', 'the one named colour'.
  kind    the genre names a kind of picture: one of the vocabulary's genres, two of them together ('street portrait'),
          'environmental portrait' or 'figure study'. A sealed genre is never a training row's genre.
"""
import glob
import json
import os
import random
import re
import shutil
from collections import Counter, defaultdict

from .core import HELD, tp
from .rows import check_rows, has_subject, seed_depth

SEALED_GENRES = set(HELD.get("genre", ()))
KINDS = [g for g in tp.VOCAB["genre"] if g not in SEALED_GENRES] + ["environmental portrait", "figure study"]
THOUGHTS = {d: c["thoughts"] for d, c in tp.COUNTS.items()}          # (fewest, most) thoughts a row of the depth holds

_PICTURE = re.compile(r"\b(he|she|they|his|her|their|him|them|it|its|here|this|these|the (man|woman|boy|girl|person|figure|frame|"
                      r"picture|scene|face|subject|light|eye|coat|robe|parka|apron|cloak|vest|suit|gown)|so |which |so the|in the|"
                      r"on the|at the)\b", re.I)
_GLOSS = [re.compile(r"^(?:[A-Z][a-z]+(?:[ -][a-z]+){0,2}): (?:a|an|the|one|hair|light|cloth|more|less|lower|higher|long|short|"
                     r"tight|wide|bright|dark|cut|tied|loose|strands|only)\b"),                  # 'Robe: a long, loose outer garment.'
          re.compile(r"^(?:A|An) [a-z]+(?: [a-z]+)? is (?:a|an|the) "),                         # 'A sink is a fixed basin'
          re.compile(r"^(?!(?:The|This|That|These|Those|Her|His|Their|Its|One|Each|Every|Both)\b)"
                     r"[A-Z][a-z]+(?: [a-z]+)? (?:is|means) (?:a|an|the|only|that|light|hair)\b")]  # 'Turquoise is a blue-green.'
_OBSERVATION = re.compile(r"^[A-Z][\w'-]*(?: [\w'-]+){0,2} (?:is|are) (?:the|its|their|her|his) (?:only|main|key|single|one|sole|whole|"
                          r"first|brightest|strongest|last|same|chief|dominant|warmest|coldest|darkest)\b")
_REMARK = re.compile(r"\b(an inference|by inference|proves little|painterly licen[cs]e|I would say|dreamlike liberty|the spec\b|"
                     r"the record\b|the hint|the seed\b|the caption\b|the prompt|the annotat|the description says|as written|"
                     r"the data\b|the label\b|generated|the model\b|text-to-image|named\b|the whole report)", re.I)
_SENTENCE = re.compile(r"(?<=[.;!?])\s+")


def gloss(text: str) -> bool:
    """Does the thought open by defining a word, with nothing in that sentence tied to this picture?"""
    first = _SENTENCE.split(text.strip())[0]
    if _OBSERVATION.search(first) or not any(p.search(first) for p in _GLOSS):
        return False
    _, _, rest = first.partition(":")
    return not _PICTURE.search(rest or first)


def gloss_kind(text: str) -> str | None:
    """'bare' (the whole thought defines words), 'mixed' (a definition, then an observation) or None."""
    if not gloss(text):
        return None
    rest = [s for s in _SENTENCE.split(text.strip())[1:] if s and not gloss(s)]
    return "mixed" if rest else "bare"


def remark(text: str) -> bool:
    """Does the thought talk about the writing or the specification instead of the picture?"""
    return bool(_REMARK.search(text))


def kind_ok(genre: str) -> bool:
    """Is the genre a kind of picture: one kind, or two together, every word covered, none sealed?"""
    words = (genre or "").lower().split()

    def cover(i, used):
        if i == len(words):
            return used >= 1
        return used < 2 and any(words[i:i + len(k.split())] == k.split() and cover(i + len(k.split()), used + 1) for k in KINDS)
    return cover(0, 0)


def read_rows(path: str) -> list:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _specs_of(rows_path: str) -> str | None:
    specs = rows_path.replace(".rows.jsonl", ".specs.jsonl")
    return specs if os.path.exists(specs) else None


def _problems(rows_path: str) -> list:
    return [p for p in check_rows(rows_path, _specs_of(rows_path))["problems"] if p[1] != "missing"]   # a skipped seed is by design


# ---------------------------------------------------------------------------------------------------------------- the acceptance read
def accept(rows_dir: str, first: int, last: int, n_sample: int = 8, rng_seed: int | None = None) -> dict:
    """The acceptance read of batches first..last: the validator per batch; over the rows, the detectors, thought counts outside
    the depth's range, the steps used, the genres chosen, seeded genres that differ from the seed's, a series with two genres;
    and a sample of rows to read whole."""
    out = dict(batches={}, flags=defaultdict(list), steps=Counter(), drawn_genres=Counter(), seeded_genres=Counter(), sample=[])
    rows, specs = [], {}
    for b in range(first, last + 1):
        path = os.path.join(rows_dir, f"batch_{b:03d}.rows.jsonl")
        if not os.path.exists(path):
            out["batches"][b] = None
            continue
        rep = check_rows(path, _specs_of(path))
        out["batches"][b] = dict(rows=rep["rows"], unparsed=rep["unparsed"], by_depth=rep["by_depth"], warnings=rep["warnings"],
                                 problems=[p for p in rep["problems"] if p[1] != "missing"],
                                 missing=[p[2] for p in rep["problems"] if p[1] == "missing"])
        if _specs_of(path):
            for it in read_rows(_specs_of(path)):
                for rid in it["ids"]:
                    specs[rid] = it
        rows += read_rows(path)
    series = defaultdict(set)
    for r in rows:
        lo, hi = THOUGHTS[r["depth"]]
        if not lo <= len(r["thoughts"]) <= hi:
            out["flags"]["thought count"].append((r["id"], r["depth"], len(r["thoughts"])))
        for t in r["thoughts"]:
            out["steps"][t["step"]] += 1
            if gloss(t["text"]):
                out["flags"]["gloss"].append((r["id"], t["step"], t["text"]))
            if remark(t["text"]):
                out["flags"]["remark"].append((r["id"], t["step"], t["text"]))
        g = (r.get("genre") or "").strip()
        if not kind_ok(g):
            out["flags"]["genre"].append((r["id"], g))
        if (r.get("source") or {}).get("kind") == "seeded":
            out["seeded_genres"][g.lower()] += 1
            seed_genre = (specs.get(r["id"]) or {}).get("genre")
            if seed_genre and seed_genre.lower() != g.lower():
                out["flags"]["seeded genre changed"].append((r["id"], seed_genre, g))
        else:
            out["drawn_genres"][g.lower()] += 1
            if r.get("series"):
                series[r["series"]].add(g.lower())
    out["flags"]["series with two genres"] = sorted((s, sorted(g)) for s, g in series.items() if len(g) > 1)
    out["rows"] = len(rows)
    out["sample"] = random.Random(rng_seed if rng_seed is not None else first * 1000 + last).sample(rows, min(n_sample, len(rows)))
    return out


def format_row(r: dict, hint: str = "") -> str:
    """A row as lines to read: identity, the spec, each thought, the wordings, the questions, the seed's hint."""
    src = r.get("source") or {}
    out = [f"{r['id']} {r.get('series')} rank {r.get('rank')} {r['depth']} {r['domain']}/{r.get('genre')} | {src.get('kind')} "
           f"{src.get('seed_id') or ''} {src.get('license') or ''}",
           "  SPEC " + json.dumps(r["spec"], ensure_ascii=False)]
    out += [f"  - {t['step']}: {t['text']}" for t in r["thoughts"]]
    out += [f"  [{k}] {v}" for k, v in (r.get("wordings") or {}).items()]
    out.append("  Q " + "; ".join(f"{q['key']}={q['value']} ({q['needs']})" for q in r.get("questions", [])))
    if hint:
        out.append("  HINT " + hint[:420])
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------------------------------- patches
def _batch_file(rows_dirs: list, rid: str) -> str:
    name = f"batch_{rid.split('-')[1][:3]}.rows.jsonl"
    for d in rows_dirs:
        if os.path.exists(os.path.join(d, name)):
            return os.path.join(d, name)
    raise FileNotFoundError(f"{rid}: no {name} in {rows_dirs}")


def apply_patch(rows_dirs: list, patch: dict, log_path: str | None = None, dry: bool = False) -> dict:
    """Apply a patch to row files, all or nothing. The patch:
        {"note": "...",
         "genre":   {row id: new genre},
         "edits":   {row id: [[old thought text, new step or None, new text or None to drop it], ...]},
         "restore": {row id: [[old thought text, None to put it back as it was, or a new text], ...]}}
    An edit names its thought by the exact old text, found exactly once in the row. A restore takes the thought from the row's
    first backup (<file>.bak, written by the first patch) and puts it after the nearest earlier thought the row still holds.
    The patched rows are checked before any file is replaced: a patch that adds a problem the validator finds (a chain question
    whose value left with a dropped thought) writes nothing. Returns {changes, files, problems, new_problems, written}."""
    genre, edits, restore = patch.get("genre", {}), patch.get("edits", {}), patch.get("restore", {})
    ids = set(genre) | set(edits) | set(restore)
    note = patch.get("note", "")
    log, problems, touched, seen = [], [], {}, set()
    for path in sorted({_batch_file(rows_dirs, i) for i in ids}):
        rows = read_rows(path)
        backup = {r["id"]: r for r in read_rows(path + ".bak")} if os.path.exists(path + ".bak") else {}
        changed = False
        for r in rows:
            rid = r["id"]
            if rid not in ids:
                continue
            seen.add(rid)
            if rid in genre and r.get("genre") != genre[rid]:
                log.append(dict(id=rid, field="genre", old=r.get("genre"), new=genre[rid], note=note))
                r["genre"], changed = genre[rid], True
            for old, step, new in edits.get(rid, []):
                hits = [i for i, t in enumerate(r["thoughts"]) if t["text"] == old]
                if len(hits) != 1:
                    problems.append((rid, f"old text found {len(hits)} times", old[:70]))
                    continue
                i = hits[0]
                if new is None:
                    log.append(dict(id=rid, field="thought", old=r["thoughts"][i], new=None, note=note))
                    del r["thoughts"][i]
                else:
                    t = dict(r["thoughts"][i], text=new, **({"step": step} if step else {}))
                    log.append(dict(id=rid, field="thought", old=r["thoughts"][i], new=t, note=note))
                    r["thoughts"][i] = t
                changed = True
            for old, new in restore.get(rid, []):
                orig = (backup.get(rid) or {}).get("thoughts", [])
                at = [i for i, t in enumerate(orig) if t["text"] == old]
                if len(at) != 1 or any(t["text"] == old for t in r["thoughts"]):
                    problems.append((rid, "not restorable (not once in the backup, or still in the row)", old[:70]))
                    continue
                now = [t["text"] for t in r["thoughts"]]
                pos = next((now.index(orig[j]["text"]) + 1 for j in range(at[0] - 1, -1, -1) if orig[j]["text"] in now), 0)
                t = dict(orig[at[0]], **({"text": new} if new else {}))
                r["thoughts"].insert(pos, t)
                log.append(dict(id=rid, field="thought", old=None, new=t, at=pos, note=note))
                changed = True
        if changed:
            touched[path] = rows
    problems += [(rid, "id not found", "") for rid in sorted(ids - seen)]
    new_problems = {}
    if not problems:
        for path, rows in touched.items():
            with open(path + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            before = set(_problems(path))
            after = [p for p in check_rows(path + ".tmp", _specs_of(path))["problems"] if p[1] != "missing" and p not in before]
            if after:
                new_problems[path] = after
    write = not problems and not new_problems and not dry
    for path in touched:
        if os.path.exists(path + ".tmp"):
            if write:
                if not os.path.exists(path + ".bak"):
                    shutil.copy2(path, path + ".bak")
                os.replace(path + ".tmp", path)
            else:
                os.remove(path + ".tmp")
    if write and log_path:
        with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
            for e in log:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return dict(changes=len(log), files=len(touched), problems=problems, new_problems=new_problems, written=write)


# --------------------------------------------------------------------------------------------------------------------------- audit
def accepted_files(accepted_path: str) -> list:
    """The row files an accepted list names: lines '<folder> <batch>' resolved against the list's own folder; '#' starts a note."""
    root, out = os.path.dirname(os.path.abspath(accepted_path)), []
    with open(accepted_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#")[0].strip()
            if line:
                folder, b = line.split()
                out.append(os.path.join(root, folder, f"batch_{int(b):03d}.rows.jsonl"))
    assert len(set(out)) == len(out), "a batch listed twice"
    return out


def audit(accepted_path: str) -> dict:
    """Every accepted row before a release: the validator's problems, duplicate ids, genres that are no kind of picture, thought
    counts outside the depth's range, and the detectors' hits (to read)."""
    rows, problems = [], []
    for path in accepted_files(accepted_path):
        problems += _problems(path)
        rows += read_rows(path)
    dup = [i for i, n in Counter(r["id"] for r in rows).items() if n > 1]
    return dict(rows=len(rows), problems=problems, duplicate_ids=dup,
                genre=[(r["id"], r.get("genre")) for r in rows if not kind_ok(r.get("genre") or "")],
                thought_count=[(r["id"], r["depth"], len(r["thoughts"])) for r in rows
                               if not THOUGHTS[r["depth"]][0] <= len(r["thoughts"]) <= THOUGHTS[r["depth"]][1]],
                gloss=[(r["id"], t["text"]) for r in rows for t in r["thoughts"] if gloss(t["text"])],
                remark=[(r["id"], t["text"]) for r in rows for t in r["thoughts"] if remark(t["text"])],
                genres=Counter((r.get("genre") or "").lower() for r in rows))


# --------------------------------------------------------------------------------------------------------------------------- pools
MUSEUMS = {"met", "nga", "aic", "cleveland", "wikidata"}


def pools(seeds_dir: str, rows_dirs: list, out_dir: str, first: int, last: int, quota: dict, rng_seed: int | None = None) -> dict:
    """One seed pool a batch for the drawer's seeded rows, so each batch draws a known mix: pool_BBB.jsonl holds twice the batch's
    quota of each source, plus the merged pictures.json (a picture two sources share is drawn once). Kept: training seeds of three
    records or more with a subject (rows.has_subject); museum seeds with a person, a thing or a scene; seeds that fit their depth with room for the writer's mood
    records (a medium row holds 14: at most 12 from the seed); seeds whose picture no batch in rows_dirs has drawn."""
    rng = random.Random(rng_seed if rng_seed is not None else 20261029 + first)
    pictures = {}
    for f in glob.glob(os.path.join(seeds_dir, "*", "pictures.json")):
        with open(f, encoding="utf-8") as fh:
            pictures.update(json.load(fh))

    def picture(sid):
        src, _, num = sid.partition(":")
        return pictures.get(sid) or (f"coco-image:{num}" if src in ("coco", "localized_narratives") else sid)
    drawn = {picture(it["seed_id"]) for d in rows_dirs for f in glob.glob(os.path.join(d, "batch_*.specs.jsonl"))
             for it in read_rows(f) if it.get("seed_id")}
    n_batches, picked, eligible = last - first + 1, {}, {}
    for src, q in quota.items():
        k, reservoir, seen = 2 * q * n_batches, [], 0
        for f in sorted(glob.glob(os.path.join(seeds_dir, src, "*.jsonl"))):
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    s = json.loads(line)
                    if s.get("held"):
                        continue
                    sp, n = s["spec"], tp.n_records(s["spec"])
                    if n < 3 or not has_subject(sp) or (src in MUSEUMS and not any(x in sp for x in ("person", "thing", "scene"))):
                        continue
                    if seed_depth(s) == "medium" and n > 12:
                        continue
                    if picture(s["seed_id"]) in drawn:
                        continue
                    seen += 1
                    if len(reservoir) < k:
                        reservoir.append(line.rstrip("\n"))
                    else:
                        j = rng.randrange(seen)
                        if j < k:
                            reservoir[j] = line.rstrip("\n")
        rng.shuffle(reservoir)
        picked[src], eligible[src] = reservoir, seen
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "pictures.json"), "w", encoding="utf-8") as fh:
        json.dump(pictures, fh)
    paths = []
    for i, b in enumerate(range(first, last + 1)):
        path = os.path.join(out_dir, f"pool_{b:03d}.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for src, q in quota.items():
                for line in picked[src][i * 2 * q:(i + 1) * 2 * q]:
                    fh.write(line + "\n")
        paths.append(path)
    return dict(eligible=eligible, picked={s: len(v) for s, v in picked.items()}, pools=paths)
