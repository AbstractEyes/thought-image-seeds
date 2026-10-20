"""thought_seeds.sources.parti - Parti Prompts (Google Research, Apache-2.0) as hidden picture specs.

PartiPrompts.tsv holds about 1,600 English prompts, each with a category (Animals, Artifacts, People, ...) and a challenge (Basic,
Quantity, Perspective, ...). A prompt becomes a seed: the category (and a one-word challenge) gives the genre, the prompt's words give
the records through the shared prompt parser (thought_seeds.textspec), and the prompt itself (names removed) is the hint."""
from __future__ import annotations

import csv
import io
import os
import re
from typing import Iterator

from .. import core
from ..textspec import ALLOW, domain_of, finish, is_explicit, spec_from_text, strip_phrases

DATASET = "parti"
LICENSE = "Apache-2.0"
URL = "https://github.com/google-research/parti"
ATTRIBUTION = ("Parti Prompts (P2), Google Research: Yu et al., 'Scaling Autoregressive Models for Content-Rich Text-to-Image "
               "Generation' (2022); PartiPrompts.tsv under the Apache License 2.0")
CITATION = """@article{yu2022scaling,
  title   = {Scaling Autoregressive Models for Content-Rich Text-to-Image Generation},
  author  = {Yu, Jiahui and Xu, Yuanzhong and Koh, Jing Yu and Luong, Thang and Baid, Gunjan and Wang, Zirui and Vasudevan, Vijay and
             Ku, Alexander and Yang, Yinfei and Ayan, Burcu Karagol and Hutchinson, Ben and Han, Wei and Parekh, Zarana and Li, Xin and
             Zhang, Han and Baldridge, Jason and Wu, Yonghui},
  journal = {Transactions on Machine Learning Research},
  year    = {2022},
  note    = {arXiv:2206.10789}
}"""
TAKEN = ("records + hint: the prompt text (its words through the closed-list maps; the prompt itself, names removed, as the hint), "
         "the category and a one-word challenge as the genre")
TSV_URL = "https://raw.githubusercontent.com/google-research/parti/main/PartiPrompts.tsv"
USER_AGENT = "thought-seeds/0.1 (seed importer for the public dataset AbstractPhil/thought-symbolic-image-captions)"

CATEGORY = {"Abstract": "abstract", "Animals": "animals", "Artifacts": "objects", "Arts": "art", "Food & Beverage": "food",
            "Illustrations": "illustration", "Indoor Scenes": "interior", "Outdoor Scenes": "outdoor scene", "People": "people",
            "Produce & Plants": "plants", "Vehicles": "vehicles", "World Knowledge": "world knowledge"}
SHORT_CHALLENGE = {"Imagination": "imagination", "Perspective": "perspective", "Quantity": "quantity"}
LOWER_NAMES = re.compile(r"\b(mona lisa|van gogh|homer|napoleon|anubis|hanuman|rembrandt|hokusai|dali|monet|da vinci|picasso|"
                         r"beatles?|lincoln|starry night|minecraft|spiderman|superman|rube goldberg)\b")


def strip_names(text: str) -> str:
    """The prompt without its name phrases ('in the style of <Name>', 'by <Name>') and without every sentence that still holds a
    name (capitalized, or one of the lower-case names this source writes)."""
    t = strip_phrases(text)
    sentences = re.split(r"(?<=[.!?])\s+", t)
    keep = [x for x in sentences if not LOWER_NAMES.search(x.lower())]
    return core.drop_named(" ".join(keep), allow=ALLOW)


def fetch(raw_dir: str) -> dict:
    import requests
    d = os.path.join(raw_dir, DATASET)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "PartiPrompts.tsv")
    if not os.path.exists(path):
        r = requests.get(TSV_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
        r.raise_for_status()
        with open(path + ".part", "wb") as fh:
            fh.write(r.content)
        os.replace(path + ".part", path)
    return {"PartiPrompts.tsv": os.path.getsize(path)}


def rows(raw_dir: str) -> list:
    with open(os.path.join(raw_dir, DATASET, "PartiPrompts.tsv"), encoding="utf-8") as fh:
        return list(csv.DictReader(io.StringIO(fh.read()), delimiter="\t", quoting=csv.QUOTE_NONE))


def build(i: int, row: dict) -> dict | None:
    prompt = (row.get("Prompt") or "").strip()
    if not prompt or is_explicit(prompt):
        return None
    clean_text = LOWER_NAMES.sub(" ", strip_phrases(prompt).lower())
    s, info = spec_from_text(clean_text)
    if not s.n():
        return None
    cat = CATEGORY.get((row.get("Category") or "").strip(), core.clean(row.get("Category") or "")) or "illustration"
    ch = SHORT_CHALLENGE.get((row.get("Challenge") or "").strip())
    genre = f"{cat} {ch}" if ch and " " not in cat else cat
    hint = core.make_hint([strip_names(prompt)])
    return core.make_seed(DATASET, str(i), domain_of(clean_text), genre, finish(DATASET, str(i), s), hint, LICENSE, URL)


def seeds(raw_dir: str, limit: int | None = None) -> Iterator[dict]:
    n = 0
    for i, row in enumerate(rows(raw_dir), 1):          # the id is the prompt's line in the file (header = line 0)
        if limit is not None and n >= limit:
            return
        seed = build(i, row)
        if seed:
            n += 1
            yield seed
