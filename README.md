# thought-seeds

Licensed image descriptions, scene graphs, museum metadata and prompts, turned into **hidden picture specifications** ("seeds") for
the text-only art thought dataset
[AbstractPhil/thought-symbolic-image-captions](https://huggingface.co/datasets/AbstractPhil/thought-symbolic-image-captions).

A row of that dataset is one act of thinking about a picture nobody sees: the picture's facts as short records, a chain of thoughts at
a stated depth (simple, medium, deep), the wordings an artist would use (caption, prompt, tags, critique) and questions whose answers
sit in the records. A seed is the starting point of such a row: the facts of one real picture, taken from a licensed source, in the
dataset's systems of attributes. No image is downloaded or stored; only annotations, metadata and text.

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
  attribution (CC0, CC BY 4.0, ODC-By, Apache-2.0, MIT); see LICENSES.md and CITATIONS.bib.
- `held`: a tenth of the vocabulary is sealed for evaluation; a seed that uses a sealed value belongs to the held-out split.

## Use

```bash
pip install -r requirements.txt
python -m thought_seeds.build --sources=coco,parti --raw=raw --out=out --fetch=1 --limit=2000
python -m thought_seeds.build --docs=out
python -m pytest -q tests
```

The attribute systems and their vocabularies come from the dataset's tooling module `thought_pack`
([geolip-nano-beatrix-trainer](https://github.com/AbstractEyes/geolip-nano-beatrix-trainer)); set `THOUGHT_TRAINER_REF` to the folder
holding `thought_pack.py` and `caption_pack.py` of a pinned checkout.

## License

The code: Apache-2.0. The seeds keep each source's license; see LICENSES.md.
