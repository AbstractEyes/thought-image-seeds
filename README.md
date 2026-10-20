# thought-image-seeds

[![tests](https://github.com/AbstractEyes/thought-image-seeds/actions/workflows/tests.yml/badge.svg)](https://github.com/AbstractEyes/thought-image-seeds/actions/workflows/tests.yml)
[![Open the photographs build in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/AbstractEyes/thought-image-seeds/blob/main/colab/thought_seeds_photographs.ipynb)
[![Open the art and prompts build in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/AbstractEyes/thought-image-seeds/blob/main/colab/thought_seeds_art_prompts.ipynb)

Licensed image descriptions, scene graphs, museum metadata and prompts, turned into **hidden picture specifications** ("seeds") for
the text-only art thought dataset
[AbstractPhil/thought-symbolic-image-captions](https://huggingface.co/datasets/AbstractPhil/thought-symbolic-image-captions).

A row of that dataset is one act of thinking about a picture nobody sees: the picture's facts as short records, a chain of thoughts at
a stated depth (simple, medium, deep), the wordings an artist would use (caption, prompt, tags, critique) and questions whose answers
sit in the records. A seed is the starting point of such a row: the facts of one real picture, taken from a licensed source, in the
dataset's systems of attributes. No image is downloaded or stored; only annotations, metadata and text.

## Install

```bash
pip install git+https://github.com/AbstractEyes/thought-image-seeds
```

For development: clone, then `pip install -r requirements.txt` (the pinned versions) and `pip install -e ".[test]"`.

## Read the seeds

```python
from thought_seeds import read_seeds
from thought_seeds.hub import seed_files, load

for seed in read_seeds("out/seeds/coco"):          # a file, a folder, a glob or a list of them
    print(seed["spec"])

print(seed_files("met"))                             # the published shards of one source
paintings = list(load("met", domain="painting", held=False))
```

## Build them

```bash
thought-seeds --sources=coco,parti --raw=raw --out=out --fetch=1 --limit=2000
thought-seeds --docs=out                             # LICENSES.md, CITATIONS.bib, seeds/README.md
python -m pytest -q
```

`--sources=all` builds every source; `--fetch=1` downloads what each source needs (annotations and metadata only) into `--raw`. The
full builds run on a Colab CPU with the two notebooks above. Each run prints the job size, the time spent and the time left, and writes
`seeds/<source>/stats.json` (counts, record histogram, key coverage, rejections by reason) beside the shards.

## A seed

```json
{"seed_id": "coco:139", "domain": "photograph", "genre": "interior",
 "spec": {"person": {"count": "2", "gender": "woman"}, "thing": {"name": "tv", "count": "1", "position": "left"},
          "scene": {"setting": "kitchen"}, "relation": [{"a": "woman", "rel": "right of", "b": "tv"}]},
 "hint": "A woman stands in the dining area at the table. ...",
 "source": {"dataset": "coco", "id": "139", "license": "CC BY 4.0", "url": "https://cocodataset.org"},
 "held": false}
```

- `spec`: facts only, as `system -> attribute -> value` plus a list of relations; every value is plain lower-case ASCII of at most 20
  bytes, and a key with its value fits 27 bytes. Keys with a closed vocabulary take only its values. Mood, intent and story are not
  facts of the source and are never in a seed.
- `hint`: optional source text (at most 600 bytes) a writer may draw further facts from; sentences that may hold a real person's name
  are removed.
- `source`: the dataset, the item's id there, its license and its page. Every source allows derived and redistributed use with
  attribution (CC0, CC BY 4.0, ODC-By, Apache-2.0, MIT); see LICENSES.md and CITATIONS.bib in the dataset.
- `held`: a tenth of the vocabulary is sealed for evaluation; a seed that uses a sealed value belongs to the held-out split.

## The attribute systems

The systems, their vocabularies, the sealed tenth, the row validator and the seed gate come from the dataset's own tools file
(`tools/thought_tools.py` in the dataset repo). The package carries a verbatim copy (`thought_seeds/thought_tools.py`, its hash in
`thought_seeds.core.TOOLS_SHA256`) and checks on import that its sealed values are the dataset's, so every build uses the same lists
and the same held-out values. `THOUGHT_TOOLS` may name another copy of the file.

## Layout

```
thought_seeds/
  core.py      the seed contract: value cleaning, the byte budget, closed lists, the held-out routing, hints, the real-name filter, shards
  maps.py      source words to the closed values (colours, settings, poses, media, styles, relations, ...)
  textspec.py  the prompt-text parser the prompt and label sources share (parti, diffusiondb, wikidata)
  build.py     the runner and the attribution files (the `thought-seeds` command)
  io.py        reading seed files
  hub.py       listing and downloading the published seeds
  sources/     one importer per source: fetch() and seeds()
colab/         the two build notebooks and their generator
tests/
```

## License

The code: Apache-2.0. The seeds keep each source's license; see LICENSES.md.
