"""Reading seed files and the build's attribution files."""
import json

from thought_seeds import read_seeds


def test_read_seeds_paths_folders_globs_and_filters(tmp_path):
    a = tmp_path / "seeds" / "x"
    a.mkdir(parents=True)
    rows = [{"seed_id": "x:1", "domain": "photograph", "held": False}, {"seed_id": "x:2", "domain": "painting", "held": True}]
    (a / "x-00000.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + "\n", encoding="utf-8")
    assert [s["seed_id"] for s in read_seeds(tmp_path)] == ["x:1", "x:2"]
    assert [s["seed_id"] for s in read_seeds(str(tmp_path / "seeds" / "*" / "*.jsonl"))] == ["x:1", "x:2"]
    assert [s["seed_id"] for s in read_seeds(a / "x-00000.jsonl", domain="painting")] == ["x:2"]
    assert [s["seed_id"] for s in read_seeds([a], held=False)] == ["x:1"]


def test_trie_is_loaded_at_the_pinned_commit():
    from thought_seeds import core
    assert core.TOOLS_SHA256 and core.SEAL_SHA256 and len(core.KEYS) == 58 and sum(len(v) for v in core.HELD.values()) == 73


def test_the_vendored_tools_file_is_unchanged():
    import hashlib
    from thought_seeds import core
    assert hashlib.sha256(open(core.TOOLS_FILE, "rb").read()).hexdigest() == core.TOOLS_SHA256
