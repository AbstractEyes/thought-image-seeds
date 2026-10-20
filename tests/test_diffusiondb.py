"""The DiffusionDB importer on a tiny prompts.parquet shaped like the fetched columns (no network): the NSFW filter, the corpus-learned
name strip, the deduplication, the spec of a cleaned prompt, records only (no hint) from the known vocabularies."""
import json
import os

import pyarrow as pa
import pyarrow.parquet as pq

from thought_seeds import core
from thought_seeds.sources import diffusiondb as ddb

ANIMALS = ["cat", "dog", "fox", "owl", "bear", "deer"]


def _write(raw, extra=()):
    d = os.path.join(raw, "diffusiondb")
    os.makedirs(d, exist_ok=True)
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
    rows += list(extra)
    t = pa.table({"prompt": [r[0] for r in rows], "prompt_nsfw": pa.array([r[1] for r in rows], pa.float32()),
                  "image_nsfw": pa.array([r[2] for r in rows], pa.float32())})
    pq.write_table(t, os.path.join(d, "prompts.parquet"))


def test_diffusiondb_seeds(tmp_path, monkeypatch):
    monkeypatch.setattr(ddb, "NAME_MIN", 1)                # a tiny corpus: every word is known
    raw = str(tmp_path)
    _write(raw)
    out = list(ddb.seeds(raw))
    assert out and all("hint" not in s for s in out)       # records only: no prompt text is shipped
    car = [s for s in out if s["spec"].get("thing", {}).get("name") == "car"]
    assert len(car) == 1                                   # deduplicated as written and as cleaned
    s = car[0]
    assert s["spec"] == {"thing": {"name": "car", "count": "1", "colour": "red"}, "scene": {"time": "night"}}
    assert s["domain"] == "illustration" and s["genre"] == "object" and s["source"]["license"] == "CC0 1.0"
    assert s["seed_id"] == "diffusiondb:" + s["source"]["id"] and len(s["source"]["id"]) == 16
    forest = [x for x in out if x["spec"].get("scene") == {"setting": "forest"}]
    assert {x["spec"]["thing"]["name"] for x in forest} == set(ANIMALS)   # six prompts, six seeds: none collapsed without a hint
    assert not any(x["spec"].get("person", {}).get("gender") == "woman" for x in out)   # the NSFW-flagged and explicit ones left
    for x in out:
        assert core.check_spec(x["spec"]) == []
        assert sum(len(v) for v in x["spec"].values()) >= 2               # no hint: one record alone is too little


def test_hintless_seeds_are_deduplicated_by_their_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(ddb, "NAME_MIN", 1)
    raw = str(tmp_path)
    _write(raw, [("a long cavalcade of horses at dusk, endless, " + "very " * 150 + "detailed", 0.01, 0.0),
                 ("a quiet harbour with two boats at dawn, soft light", 0.01, 0.0),
                 ("a quiet harbour with two boats at dawn, soft light, greg rutkowski", 0.01, 0.0)])
    out = list(ddb.seeds(raw))
    boats = [s for s in out if s["spec"].get("thing", {}).get("name") == "boat"]
    assert len(boats) == 1 and boats[0]["spec"]["thing"]["count"] == "2"                # one text once cleaned: one seed
    assert any(s["spec"].get("thing", {}).get("name") == "horse" for s in out)          # a long text keeps its seed


def test_spaced_hyphens_are_joined_before_the_prompt_is_cut():
    assert ddb.segments("photo of a black and yellow spider - man, award - winning photo, trs - 8 0") == \
        ["photo of a black and yellow spider-man", "award-winning photo", "trs-8 0"]
    assert ddb.segments("a castle - digital art") == ["a castle-digital art"]
    names, totals, safe = set(), {}, ddb._safe_words()
    text = ddb.clean_prompt("photo of a cyber black and yellow spider - man, award - winning photo", names, totals, safe)
    spec = ddb.textspec.spec_from_text(text)[0].spec()
    assert "person" not in spec and spec.get("thing", {}).get("name") != "spider"      # Spider-Man is no man and no spider
    realistic = ddb.clean_prompt("an old man by the sea, unreal engine 5 render, photo - realistic", names, totals, safe)
    assert ddb.textspec.domain_of(realistic) != "photograph"


def test_open_records_come_from_the_known_vocabularies():
    things, ends = ddb.known_things(), ddb.known_ends()
    assert {"cat", "car", "tyrannosaurus", "hair dryer", "frisbee"} <= things and "dedede" not in things
    spec = {"thing": {"name": "dedede", "count": "1"}, "person": {"gender": "man"},
            "relation": [{"a": "man", "rel": "holding", "b": "cat"}, {"a": "man", "rel": "beside", "b": "peach"}]}
    assert ddb.vocab_only(spec, things, ends) == {"person": {"gender": "man"},
                                                  "relation": [{"a": "man", "rel": "holding", "b": "cat"}]}


def test_an_all_capitals_word_is_a_name():
    names, safe = set(), ddb._safe_words()
    totals = {w: 10 for w in "japanese street fashion kerouac magazine red bicycle cat sofa dslr photo".split()}
    assert ddb.clean_prompt("japanese street fashion, KEROUAC magazine, a red bicycle", names, totals, safe) == \
        "japanese street fashion, a red bicycle"
    assert "dslr" in ddb.clean_prompt("a cat on a sofa, DSLR photo", names, totals, safe)


def test_the_name_list_is_learned_again_when_its_settings_change(tmp_path, monkeypatch):
    monkeypatch.setattr(ddb, "NAME_MIN", 1)
    raw = str(tmp_path)
    _write(raw)
    path = os.path.join(raw, "diffusiondb", "name_words.json")
    with open(path, "w", encoding="utf-8") as fh:          # a list kept under other settings, naming nobody
        json.dump({"cap_ratio": 0.99, "by_ratio": 0.99, "list_ratio": 0.99, "pair_ratio": 0.99, "name_min": 1, "names": [],
                   "pairs": [], "totals": {}}, fh)
    list(ddb.seeds(raw))
    with open(path, encoding="utf-8") as fh:
        j = json.load(fh)
    assert {k: j[k] for k in ddb.name_settings(ddb._safe_words())} == ddb.name_settings(ddb._safe_words())
    assert {"greg", "rutkowski"} <= set(j["names"])


def test_strip_segment_keeps_agents_and_drops_artists():
    names = {"greg", "rutkowski"}
    assert ddb.strip_segment("a woman surrounded by flowers", names) == "a woman surrounded by flowers"
    assert ddb.strip_segment("a portrait by greg rutkowski", names) == "a portrait"
    assert ddb.strip_segment("art by somebody", names) == ""
    assert ddb.strip_segment("in the style of ukiyo-e", names) == "ukiyo-e"
    assert ddb.strip_segment("a cottage by the lake trending on artstation", names) == "a cottage by the lake"
    assert ddb.strip_segment('" a red car parked by the sea on "', names) == "a red car parked by the sea"     # quotes go


def test_module_contract():
    assert "no hint" in ddb.TAKEN and "hint" not in ddb.TAKEN.replace("no hint", "")
