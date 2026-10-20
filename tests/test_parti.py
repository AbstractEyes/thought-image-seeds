"""The Parti importer and the shared prompt parser on a tiny PartiPrompts.tsv-shaped fixture (no network)."""
import os

from thought_seeds import core
from thought_seeds.sources import parti

TSV = ("Prompt\tCategory\tChallenge\tNote\n"
       "a red car to the left of two dogs\tVehicles\tProperties & Positioning\t\n"
       "A photo of an old man wearing a blue coat, sitting on a bench at night.\tPeople\tFine-grained Detail\t\n"
       "a painting of a cat in the style of Picasso\tArts\tStyle & Format\t\n"
       "a marina without any boats in it\tOutdoor Scenes\tLinguistic Structures\t\n"
       "bond\tAbstract\tBasic\tBiology-inspired concepts with multiple meanings\n"
       "four wine bottles\tArtifacts\tQuantity\t\n")


def _seeds(tmp_path):
    d = os.path.join(str(tmp_path), "parti")
    os.makedirs(d)
    with open(os.path.join(d, "PartiPrompts.tsv"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(TSV)
    return {s["seed_id"]: s for s in parti.seeds(str(tmp_path))}


def test_parti_specs(tmp_path):
    out = _seeds(tmp_path)
    assert set(out) == {"parti:1", "parti:2", "parti:3", "parti:4", "parti:6"}     # 'bond' states no fact
    a = out["parti:1"]
    assert a["spec"] == {"thing": {"name": "car", "count": "1", "colour": "red"},
                         "relation": [{"a": "car", "rel": "left of", "b": "dog"}]}
    assert a["domain"] == "illustration" and a["genre"] == "vehicles" and a["hint"] == "a red car to the left of two dogs."
    b = out["parti:2"]
    assert b["spec"] == {"person": {"count": "1", "gender": "man", "age": "elderly"}, "wear": {"clothing": "coat", "colour": "blue"},
                         "body": {"pose": "sitting"}, "thing": {"name": "bench", "count": "1"}, "scene": {"time": "night"},
                         "form": {"medium": "photograph"}}
    assert b["domain"] == "photograph" and b["genre"] == "people"
    c = out["parti:3"]
    assert c["domain"] == "painting" and c["genre"] == "art" and "Picasso" not in c["hint"] and c["spec"]["thing"]["name"] == "cat"
    assert out["parti:4"]["spec"] == {"scene": {"setting": "harbour"}}               # the boats are negated
    assert out["parti:6"]["spec"] == {"thing": {"name": "bottle", "count": "4"}} and out["parti:6"]["genre"] == "objects quantity"
    for s in out.values():
        assert core.check_spec(s["spec"]) == [] and s["source"]["license"] == "Apache-2.0"


def test_strip_names():
    assert parti.strip_names("A cat. Oil painting in the style of Vincent Van Gogh.") == "A cat. Oil painting."
    assert parti.strip_names("A cat on a sofa. The mona lisa as a cat.") == "A cat on a sofa."      # a lower-case name
    assert parti.strip_names("A DSLR photo of a VW van. A dog.") == "A dog."                       # a brand in capitals goes
    assert parti.strip_names("A DSLR photo of a red van.") == "A DSLR photo of a red van."


def test_module_contract():
    for name in ("DATASET", "LICENSE", "URL", "ATTRIBUTION", "CITATION", "TAKEN"):
        assert isinstance(getattr(parti, name), str) and getattr(parti, name)
    assert parti.LICENSE == "Apache-2.0" and "@article{yu2022scaling" in parti.CITATION
