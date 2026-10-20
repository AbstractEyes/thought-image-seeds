"""Reading seed files: JSON Lines, one seed a line (local paths, folders or globs)."""
from __future__ import annotations

import glob
import json
import os
from typing import Iterable, Iterator


def _paths(paths) -> list:
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    out = []
    for p in paths:
        p = os.fspath(p)
        if os.path.isdir(p):
            out += sorted(glob.glob(os.path.join(p, "**", "*.jsonl"), recursive=True))
        elif any(c in p for c in "*?["):
            out += sorted(glob.glob(p, recursive=True))
        else:
            out.append(p)
    return out


def read_seeds(paths: str | os.PathLike | Iterable, domain: str | None = None, held: bool | None = None) -> Iterator[dict]:
    """Every seed in the files (a path, a folder searched recursively, a glob, or a list of them), optionally only one domain or
    only the held / training seeds."""
    for path in _paths(paths):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                seed = json.loads(line)
                if domain is not None and seed.get("domain") != domain:
                    continue
                if held is not None and bool(seed.get("held")) != held:
                    continue
                yield seed
