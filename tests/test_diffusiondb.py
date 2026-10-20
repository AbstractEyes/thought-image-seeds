"""The DiffusionDB importer on a tiny prompts.parquet shaped like the fetched columns (no network): the NSFW filter, the corpus-learned
name strip, the deduplication and the spec of a cleaned prompt."""
import os

import pyarrow as pa
import pyarrow.parquet as pq

from thought_seeds import core
from thought_seeds.sources import diffusiondb as ddb

ANIMALS = ["cat", "dog", "fox", "owl", "bear", "deer"]


def _write(raw):
    d = os.path.join(raw, "diffusiondb")
    os.makedirs(d)
    rows = []
    for a in ANIMALS:                                      # the corpus teaches the names: an artist after 'by', a sitter in capitals
        rows.append((f"a {a} in a forest, by greg rutkowski, trending on artstation", 0.01, 0.0))
        rows.append((f"portrait of Emma Watson as a {a}, oil painting", 0.02, 0.0))
    rows += [
        ("a red car parked by the sea at night, greg rutkowski, trending on artstation, 8 k", 0.01, 0.0),
        ("a red car parked by the sea at night, greg rutkowski, trending on artstation, 8 k", 0.03, 0.1),   # the same prompt again
        ("a red car parked by the sea at night, Greg Rutkowski, 8 k", 0.01, 0.0),                            # the same once cleaned
        ("a woman in a blue dress sitting on a bench, sharp focus", 0.5, 0.0),                               # prompt NSFW score
        ("a woman in a blue dress standing in a garden, sharp focus", 0.01, 2.0),                            # image flagged
        ("nude woman lying on a bed, oil painting", 0.1, 0.0),                                               # explicit word
        ("emma watson, greg rutkowski", 0.01, 0.0),                                                           # nothing left
    ]
    t = pa.table({"prompt": [r[0] for r in rows], "prompt_nsfw": pa.array([r[1] for r in rows], pa.float32()),
                  "image_nsfw": pa.array([r[2] for r in rows], pa.float32())})
    pq.write_table(t, os.path.join(d, "prompts.parquet"))


def test_diffusiondb_seeds(tmp_path, monkeypatch):
    monkeypatch.setattr(ddb, "NAME_MIN", 1)                # a tiny corpus: every word is known
    raw = str(tmp_path)
    _write(raw)
    out = list(ddb.seeds(raw))
    hints = [s["hint"] for s in out]
    assert all("greg" not in h and "rutkowski" not in h and "emma" not in h.lower() and "watson" not in h.lower() for h in hints)
    assert all("artstation" not in h and "nude" not in h and "woman in a blue dress" not in h for h in hints)
    car = [s for s in out if s["hint"].startswith("a red car")]
    assert len(car) == 1                                   # deduplicated as written and as cleaned
    s = car[0]
    assert s["hint"] == "a red car parked by the sea at night."              # the artist, platform and '8 k' are gone
    assert s["spec"] == {"thing": {"name": "car", "count": "1", "colour": "red"}, "scene": {"time": "night"}}
    assert s["domain"] == "illustration" and s["genre"] == "object" and s["source"]["license"] == "CC0 1.0"
    assert s["seed_id"] == "diffusiondb:" + s["source"]["id"] and len(s["source"]["id"]) == 16
    forest = [x for x in out if x["hint"].startswith("a cat in a forest")]
    assert forest and forest[0]["spec"]["scene"] == {"setting": "forest"} and forest[0]["spec"]["thing"]["name"] == "cat"
    for x in out:
        assert core.check_spec(x["spec"]) == [] and not core.drop_named(x["hint"]) != x["hint"]


def test_strip_segment_keeps_agents_and_drops_artists():
    names = {"greg", "rutkowski"}
    assert ddb.strip_segment("a woman surrounded by flowers", names) == "a woman surrounded by flowers"
    assert ddb.strip_segment("a portrait by greg rutkowski", names) == "a portrait"
    assert ddb.strip_segment("art by somebody", names) == ""
    assert ddb.strip_segment("in the style of ukiyo-e", names) == "ukiyo-e"
    assert ddb.strip_segment("a cottage by the lake trending on artstation", names) == "a cottage by the lake"
    assert ddb.strip_segment('" a red car parked by the sea on "', names) == "a red car parked by the sea"     # quotes go
