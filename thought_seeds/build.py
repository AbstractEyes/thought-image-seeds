"""thought_seeds.build - run source importers into seed shards, and write the attribution files.

    python -m thought_seeds.build --sources=coco,gqa --raw=<dir> --out=<dir> [--limit=N] [--fetch=1]
    python -m thought_seeds.build --docs=<out dir>      # LICENSES.md, CITATIONS.bib, seeds/README.md from the source modules

Every run lowers its own priority and sets a memory ceiling where the platform allows (Windows job objects), prints the job size,
the time spent and the time left per source, and writes seeds/<source>/stats.json beside the shards."""
from __future__ import annotations

import importlib
import json
import os
import pkgutil
import sys
import time

from . import core

ORDER = ("coco", "localized_narratives", "gqa", "docci", "met", "aic", "nga", "cleveland", "wikidata", "parti", "diffusiondb")


def available() -> list:
    from . import sources
    names = {m.name for m in pkgutil.iter_modules(sources.__path__)}
    return [n for n in ORDER if n in names] + sorted(names - set(ORDER))


def module(name: str):
    return importlib.import_module(f"thought_seeds.sources.{name}")


def _lower_priority(gb: float) -> str:
    if sys.platform != "win32":
        try:
            os.nice(10)
        except (AttributeError, OSError):
            pass
        return "nice 10"
    import ctypes
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)
    from .limits import hard_memory_limit
    hard_memory_limit(gb)
    return f"below normal, {gb:.0f} GB ceiling"


def run(names, raw: str, out: str, limit: int | None = None, fetch: bool = False) -> dict:
    t0 = time.time()
    results = {}
    for i, name in enumerate(names):
        m = module(name)
        t1 = time.time()
        if fetch:
            got = m.fetch(raw)
            print(f"[{name}] fetched {len(got)} files, {sum(got.values()) / 2**20:.1f} MB", flush=True)
        sh = core.Shards(out, m.DATASET)
        core.REJECTED.clear()
        core.COHERED.clear()
        core.PICTURES.clear()
        for k, seed in enumerate(m.seeds(raw, limit=limit), 1):
            sh.add(seed)
            if k % 20000 == 0:
                print(f"[{name}] {k} seeds, {time.time() - t1:.0f} s", flush=True)
        st = sh.close(dict(license=m.LICENSE, url=m.URL, taken=getattr(m, "TAKEN", ""), rejected=dict(core.REJECTED.most_common(20))))
        pics = os.path.join(out, "seeds", m.DATASET, core.PICTURES_FILE)
        if core.PICTURES:                  # the seeds whose picture another source describes too (read by rows.picture_of)
            with open(pics, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(dict(sorted(core.PICTURES.items())), fh, indent=0)
            print(f"[{name}] {len(core.PICTURES)} seeds share their picture with another source ({core.PICTURES_FILE})", flush=True)
        elif os.path.exists(pics):
            os.remove(pics)
        if core.COHERED:
            print(f"[{name}] facts removed as incoherent: {dict(core.COHERED)}", flush=True)
        if core.REJECTED:
            print(f"[{name}] rejected {sum(core.REJECTED.values())}: {core.REJECTED.most_common(5)}", flush=True)
        done = time.time() - t0
        left = done / (i + 1) * (len(names) - i - 1)
        print(f"[{name}] {st['seeds']} seeds ({st['held']} held) in {time.time() - t1:.0f} s; job {i + 1}/{len(names)}, "
              f"{done / 60:.1f} min spent, about {left / 60:.1f} min left (by the mean so far)", flush=True)
        results[name] = st
    return results


# the license texts the LICENSES.md cells link (CC BY 4.0 section 3(a)(1)(C) asks for the text or a link to it with every use)
LICENSE_URLS = {"cc0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/", "cc-by-4.0": "https://creativecommons.org/licenses/by/4.0/",
                "apache-2.0": "https://www.apache.org/licenses/LICENSE-2.0", "odc-by-1.0": "https://opendatacommons.org/licenses/by/1-0/",
                "mit": "https://opensource.org/licenses/MIT"}
# the changes made to a source, for a module without its own MODIFIED text (CC BY 4.0 section 3(a)(1)(B) asks that they be said)
DEFAULT_MODIFIED = ("modified by this dataset: values extracted from the source and mapped to the dataset's closed vocabulary; any hint "
                    "is the source's text or a sentence built from its fields, filtered and shortened")


def license_cell(lic: str) -> str:
    """A module's LICENSE with each license name linked to its text: 'CC0 1.0 (records); CC BY 4.0 (description hints)' ->
    '[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (records); [CC BY 4.0](...) (description hints)'."""
    out = []
    for part in lic.split(";"):
        part = part.strip()
        name = part.split("(")[0].strip()
        url = LICENSE_URLS.get(core.tp.license_key(name))
        out.append(part.replace(name, f"[{name}]({url})", 1) if url else part)
    return "; ".join(out)


def docs(out: str) -> None:
    """LICENSES.md (the dataset's license and every source's), CITATIONS.bib, seeds/README.md (one line per source)."""
    mods = [module(n) for n in available()]
    os.makedirs(os.path.join(out, "seeds"), exist_ok=True)
    lic = ["# Licenses and attributions", "",
           "The dataset's own rows and code: Apache-2.0. Each seed keeps the license of its source in its `source.license` field, and a",
           "row written from a seed carries the stricter of the two. Every source below licenses its data under CC0, CC BY 4.0, ODC-By,",
           "Apache-2.0 or MIT, which allow derived, redistributed and commercial use; no share-alike or non-commercial source is",
           "included. A source that attaches terms of its own names them in its row. Each license cell links the license text, and",
           "each row says how the source's material was changed here.", "",
           "| source | license | attribution | what was taken | changes made | primary page |", "|---|---|---|---|---|---|"]
    bib, readme = [], ["# Seeds", "", "Hidden picture specifications drawn from licensed sources; one JSON object a line "
                       "(`seeds/<source>/<source>-NNNNN.jsonl`).", "", "| source | license | what was taken |", "|---|---|---|"]
    for m in mods:
        lic.append(f"| {m.DATASET} | {license_cell(m.LICENSE)} | {m.ATTRIBUTION} | {getattr(m, 'TAKEN', '')} | "
                   f"{getattr(m, 'MODIFIED', DEFAULT_MODIFIED)} | {m.URL} |")
        readme.append(f"| {m.DATASET} | {license_cell(m.LICENSE)} | {getattr(m, 'TAKEN', '')} |")
        bib.append(m.CITATION.strip())
    with open(os.path.join(out, "LICENSES.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lic) + "\n")
    with open(os.path.join(out, "CITATIONS.bib"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n\n".join(bib) + "\n")
    with open(os.path.join(out, "seeds", "README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(readme) + "\n")


def main(argv=None) -> int:
    args = {a.split("=")[0].lstrip("-"): a.split("=", 1)[1] if "=" in a else "1" for a in (argv or sys.argv[1:])}
    if "docs" in args:
        docs(args["docs"])
        print(f"LICENSES.md, CITATIONS.bib, seeds/README.md written under {args['docs']}")
        return 0
    if "draw" in args:
        from .rows import draw
        doms = {d: float(w) for d, w in (x.split(":") for x in args["domains"].split(","))} if "domains" in args else None
        path = draw(int(args["draw"]), int(args.get("series", 10)), int(args.get("singles", 0)), args["rows-dir"],
                    int(args["rng"]) if "rng" in args else None, args["seeds"].split(",") if "seeds" in args else None, doms,
                    args.get("seed-series") == "1" or int(args.get("seeded-series", 0)))
        print(f"specs written: {path}")
        return 0
    if "check-rows" in args:
        from .rows import check_rows
        rep = check_rows(args["check-rows"], args.get("specs"))
        out = args["check-rows"].replace(".rows.jsonl", "") + ".check.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=1)
        print(f"{rep['rows']} rows, {rep['unparsed']} unparsed, {rep['rows_with_problems']} with problems; by rule {rep['by_rule']}; "
              f"{len(rep['warnings'])} name warnings; depths {rep['by_depth']}; domains {rep['by_domain']}")
        for p in rep["problems"][:60]:
            print("  PROBLEM", *p)
        for w in rep["warnings"][:30]:
            print("  REVIEW ", *w)
        print(f"the full report: {out}")
        return 0 if not rep["problems"] and not rep["unparsed"] else 1
    if "accept" in args:                       # --accept=36-38 --rows-dir=DIR [--sample=8] [--rng=N]: the acceptance read
        from .curate import accept, format_row
        first, last = (int(x) for x in args["accept"].split("-"))
        rep = accept(args["rows-dir"], first, last, int(args.get("sample", 8)), int(args["rng"]) if "rng" in args else None)
        for b, v in rep["batches"].items():
            if v is None:
                print(f"batch {b:03d}: no rows file")
                continue
            print(f"batch {b:03d}: rows {v['rows']} unparsed {v['unparsed']} problems {len(v['problems'])} skipped "
                  f"{v['missing'] or 0} name warnings {len(v['warnings'])} depths {v['by_depth']}")
            for p in v["problems"][:10]:
                print("  PROBLEM", *p)
            for w in v["warnings"][:5]:
                print("  REVIEW ", *w)
        print(f"rows {rep['rows']}; steps {dict(rep['steps'].most_common())}")
        print(f"drawn genres {dict(rep['drawn_genres'].most_common())}")
        print(f"seeded genres {dict(rep['seeded_genres'].most_common())}")
        for name in ("gloss", "remark", "genre", "thought count", "seeded genre changed", "series with two genres"):
            hits = rep["flags"].get(name, [])
            print(f"{name}: {len(hits)}")
            for h in hits[:30]:
                print("   ", h)
        print("\n==== rows to read ====")
        for r in sorted(rep["sample"], key=lambda r: r["id"]):
            print(format_row(r) + "\n")
        bad = [b for b, v in rep["batches"].items() if v is None or v["problems"] or v["unparsed"]]
        return 1 if bad else 0
    if "patch" in args:                        # --patch=FILE --rows-dir=DIR[,DIR] [--log=FILE] [--dry]: a patch, checked first
        from .curate import apply_patch
        with open(args["patch"], encoding="utf-8") as fh:
            patch = json.load(fh)
        res = apply_patch(args["rows-dir"].split(","), patch, args.get("log"), args.get("dry") == "1")
        print(f"changes {res['changes']} in {res['files']} files; written {res['written']}")
        for p in res["problems"]:
            print("  PROBLEM", *p)
        for path, ps in res["new_problems"].items():
            for p in ps[:10]:
                print("  BREAKS", os.path.basename(path), *p)
        return 0 if not res["problems"] and not res["new_problems"] else 1
    if "audit" in args:                        # --audit=ACCEPTED.txt: every accepted row before a release
        from .curate import audit
        rep = audit(args["audit"])
        print(f"rows {rep['rows']}; problems {len(rep['problems'])}; duplicate ids {len(rep['duplicate_ids'])}; genres not a kind "
              f"{len(rep['genre'])}; thought counts out of range {len(rep['thought_count'])}; to read: gloss {len(rep['gloss'])}, "
              f"remark {len(rep['remark'])}")
        print("genres", dict(rep["genres"].most_common()))
        for name in ("problems", "duplicate_ids", "genre", "thought_count", "gloss", "remark"):
            for h in rep[name][:30]:
                print(f"  {name.upper()}", h)
        return 1 if rep["problems"] or rep["duplicate_ids"] or rep["genre"] or rep["thought_count"] else 0
    if "pools" in args:                        # --pools=45-47 --seeds-dir=DIR --rows-dir=DIR[,DIR] --out=DIR --quota=coco:4,...
        from .curate import pools
        first, last = (int(x) for x in args["pools"].split("-"))
        quota = {s: int(n) for s, n in (x.split(":") for x in args["quota"].split(","))}
        res = pools(args["seeds-dir"], args["rows-dir"].split(","), args["out"], first, last, quota,
                    int(args["rng"]) if "rng" in args else None)
        for s in quota:
            print(f"{s:22s} eligible {res['eligible'][s]:9,d} picked {res['picked'][s]}")
        print("pools", *res["pools"])
        return 0
    names =available() if args.get("sources", "all") == "all" else args["sources"].split(",")
    print(f"thought_seeds {sys.modules['thought_seeds'].__version__}; tools {core.tp.VERSION}; sources {names}; "
          f"priority {_lower_priority(float(args.get('gb', 16)))}", flush=True)
    res = run(names, args["raw"], args["out"], int(args["limit"]) if "limit" in args else None, args.get("fetch") == "1")
    print(json.dumps({k: dict(seeds=v["seeds"], held=v["held"]) for k, v in res.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
