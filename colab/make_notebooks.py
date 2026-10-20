"""Writes the two Colab notebooks (photographs; art and prompts) that run the full seed builds on Colab's CPU. Each notebook installs
this package from GitHub at a tag (no dependency changes: Colab already has numpy, pandas, pyarrow, requests, huggingface_hub), clones
fetches and builds its sources, checks every seed, writes the attribution files and,
only when UPLOAD is set True, uploads seeds/ to the dataset repo with the HF_TOKEN from Colab's secrets.

    python colab/make_notebooks.py --repo=AbstractEyes/<name> --tag=v0.0.1"""
import json
import os
import sys

DATASET_REPO = "AbstractPhil/thought-symbolic-image-captions"
BOOKS = {
    "thought_seeds_photographs": ("Photographs: COCO, Localized Narratives, GQA, DOCCI",
                                  ["coco", "localized_narratives", "gqa", "docci"]),
    "thought_seeds_art_prompts": ("Art and prompts: the Met, Art Institute of Chicago, National Gallery of Art, Cleveland, Wikidata, "
                                  "Parti, DiffusionDB", ["met", "aic", "nga", "cleveland", "wikidata", "parti", "diffusiondb"]),
}


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text.strip("\n").splitlines(True)}


def book(repo, tag, name, title, sources):
    colab = f"https://colab.research.google.com/github/{repo}/blob/main/colab/{name}.ipynb"
    cells = [
        md(f"""
# Thought seeds: {title}
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({colab})

Builds the seeds of these sources on this machine's CPU: downloads their annotations and metadata (never images), turns each picture
into a hidden picture specification in the dataset's attribute systems, checks every seed, and writes `seeds/<source>/` shards with
their statistics, plus LICENSES.md and CITATIONS.bib. The upload to
[{DATASET_REPO}](https://huggingface.co/datasets/{DATASET_REPO}) runs only when `UPLOAD = True` and an `HF_TOKEN` secret is set.
Run the cells in order; nothing needs a GPU.
"""),
        code(f"""
# C1: install the package (no dependency changes; the dataset's tools file travels inside it)
import os, subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "git+https://github.com/{repo}@{tag}"], check=True)
import thought_seeds
from thought_seeds import core
print("thought_seeds", thought_seeds.__version__, "| tools", core.tp.VERSION, "|", len(core.KEYS), "keys")
"""),
        code(f"""
# C2: what this notebook builds
SOURCES = {sources!r}
LIMIT = None            # None = every item of each source; a number = a sample per source
RAW, OUT = "/content/raw", "/content/out"
UPLOAD = False          # True uploads OUT/seeds, LICENSES.md and CITATIONS.bib to the dataset repo
print(SOURCES, "| limit", LIMIT, "| upload", UPLOAD)
"""),
        code("""
# C3: fetch and build (prints the job size, the time spent and the time left per source)
from thought_seeds import build
results = build.run(SOURCES, RAW, OUT, limit=LIMIT, fetch=True)
"""),
        code("""
# C4: check every seed again from the files, and the statistics
import glob, json
from thought_seeds.core import tp, HELD
total, bad = 0, 0
for src in SOURCES:
    files = sorted(glob.glob(f"{OUT}/seeds/{src}/{src}-*.jsonl"))
    n = b = 0
    for f in files:
        for line in open(f, encoding="utf-8"):
            seed = json.loads(line)
            n += 1
            probs = list(tp.validate_seed(seed, HELD)) if hasattr(tp, "validate_seed") else []
            b += bool(probs)
    st = json.load(open(f"{OUT}/seeds/{src}/stats.json"))
    print(f"{src:22s} {n:8d} seeds  {st['held']:6d} held  {b:4d} failing  {len(files)} shards  hint {st['with_hint']}")
    total, bad = total + n, bad + b
print("all:", total, "seeds,", bad, "failing")
assert bad == 0, "a seed fails the gate: do not upload"
"""),
        code("""
# C5: the attribution files
build.docs(OUT)
print(open(f"{OUT}/LICENSES.md").read()[:3000])
"""),
        code(f"""
# C6: upload (only when UPLOAD is True and the HF_TOKEN secret exists)
if UPLOAD:
    from google.colab import userdata
    from huggingface_hub import HfApi
    api = HfApi(token=userdata.get("HF_TOKEN"))
    for src in SOURCES:
        api.upload_folder(folder_path=f"{{OUT}}/seeds/{{src}}", path_in_repo=f"seeds/{{src}}", repo_id="{DATASET_REPO}",
                          repo_type="dataset", commit_message=f"seeds: {{src}}")
        print("uploaded", src)
else:
    print("UPLOAD is False: nothing uploaded")
"""),
    ]
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "name": "python3"},
                                         "language_info": {"name": "python"}, "colab": {"provenance": []}},
            "nbformat": 4, "nbformat_minor": 5}


def main(argv=None):
    args = {a.split("=")[0].lstrip("-"): a.split("=", 1)[1] for a in (argv or sys.argv[1:]) if "=" in a}
    repo, tag = args["repo"], args.get("tag", "main")
    here = os.path.dirname(os.path.abspath(__file__))
    for name, (title, sources) in BOOKS.items():
        with open(os.path.join(here, f"{name}.ipynb"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(book(repo, tag, name, title, sources), fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        print("written", name)


if __name__ == "__main__":
    main()
