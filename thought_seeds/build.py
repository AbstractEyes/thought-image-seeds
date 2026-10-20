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
        for k, seed in enumerate(m.seeds(raw, limit=limit), 1):
            sh.add(seed)
            if k % 20000 == 0:
                print(f"[{name}] {k} seeds, {time.time() - t1:.0f} s", flush=True)
        st = sh.close(dict(license=m.LICENSE, url=m.URL, taken=getattr(m, "TAKEN", ""), rejected=dict(core.REJECTED.most_common(20))))
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


def docs(out: str) -> None:
    """LICENSES.md (the dataset's license and every source's), CITATIONS.bib, seeds/README.md (one line per source)."""
    mods = [module(n) for n in available()]
    os.makedirs(os.path.join(out, "seeds"), exist_ok=True)
    lic = ["# Licenses and attributions", "",
           "The dataset's own rows and code: Apache-2.0. Each seed keeps the license of its source in its `source.license` field, and a",
           "row written from a seed carries the stricter of the two. Every source below allows derived, redistributed and commercial use",
           "under its terms (CC0, CC BY 4.0, ODC-By, Apache-2.0 or MIT); no share-alike or non-commercial source is included.", "",
           "| source | license | attribution | what was taken | primary page |", "|---|---|---|---|---|"]
    bib, readme = [], ["# Seeds", "", "Hidden picture specifications drawn from licensed sources; one JSON object a line "
                       "(`seeds/<source>/<source>-NNNNN.jsonl`).", "", "| source | license | what was taken |", "|---|---|---|"]
    for m in mods:
        lic.append(f"| {m.DATASET} | {m.LICENSE} | {m.ATTRIBUTION} | {getattr(m, 'TAKEN', '')} | {m.URL} |")
        readme.append(f"| {m.DATASET} | {m.LICENSE} | {getattr(m, 'TAKEN', '')} |")
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
                    args.get("seed-series") == "1")
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
    names =available() if args.get("sources", "all") == "all" else args["sources"].split(",")
    print(f"thought_seeds {sys.modules['thought_seeds'].__version__}; tools {core.tp.VERSION}; sources {names}; "
          f"priority {_lower_priority(float(args.get('gb', 16)))}", flush=True)
    res = run(names, args["raw"], args["out"], int(args["limit"]) if "limit" in args else None, args.get("fetch") == "1")
    print(json.dumps({k: dict(seeds=v["seeds"], held=v["held"]) for k, v in res.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
