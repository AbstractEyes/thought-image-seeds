"""The seed core and the word maps against the dataset's tools (the final seal)."""
from thought_seeds import core, maps
from thought_seeds.core import tp


def test_every_mapped_value_is_in_its_list():
    for key, mapping in maps.ALL.items():
        lst = core.closed_list(key)
        assert lst is not None, key
        for phrase, value in mapping.items():
            if value is None or (key in ("wear colour", "thing colour") and value in maps.HAIR_COLOUR_ONLY):
                continue
            assert value in lst, (key, phrase, value)
    for phrase, rel in maps.RELATION.items():
        assert rel in tp.RELATIONS, (phrase, rel)


def test_find_longest_first_and_bounded():
    assert maps.find("a man in a navy blue coat", maps.COLOUR) == ["navy"]
    assert maps.find("an old man sitting", maps.AGE) == ["elderly"]
    assert maps.find("a bookseller", maps.ROLE) == []                     # 'seller' inside a word is not a match
    assert maps.majority(["a man", "a man and a dog", "a woman"], maps.GENDER) == "man"
    assert maps.majority(["a man"], maps.GENDER) is None


def test_spec_budget_lists_and_caps():
    s = core.Spec()
    assert s.set("person", "gender", "Woman")
    assert not s.set("wear", "clothing", "shirt")                          # not in the closed list
    assert s.dropped["not in list: wear clothing"] == 1
    assert not s.set("thing", "name", "an extraordinarily long name")      # over 20 bytes
    assert s.set("thing", "name", "fish stall")
    assert not s.set("person", "gender", "man")                            # the first value wins
    assert s.relate("woman", "in front of", "fish stall")
    assert not s.relate("woman", "on", "fish stall")                       # 'on' is not a relation of the list
    try:
        s.set("mood", "feeling", "calm")
        raise AssertionError("a seed took a mood")
    except ValueError:
        pass
    spec = s.spec()
    assert core.check_spec(spec) == []
    assert tp.n_records(spec) == 3


def test_route_keeps_a_tenth_whole_and_strips_the_rest():
    spec = {"person": {"gender": "woman"}, "body": {"pose": "walking"}, "thing": {"name": "dog"}}
    assert core.sealed(spec)                                              # walking is sealed in the 0.1.62 seal
    kept = held = 0
    for i in range(2000):
        s, h = core.route(f"test:{i}", spec)
        if h:
            held += 1
            assert s == spec
        else:
            kept += 1
            assert "body" not in s and not core.sealed(s)
    assert 120 < held < 290, held                                         # about a tenth


def test_make_seed_contract_fields():
    s = core.Spec()
    s.set("person", "gender", "man")
    s.set("scene", "setting", "beach")
    seed = core.make_seed("coco", "123", "photograph", "street", s, "A man on a beach.", "CC BY 4.0", "https://cocodataset.org")
    assert set(seed) == {"seed_id", "domain", "genre", "spec", "hint", "source", "held"}
    assert seed["seed_id"] == "coco:123" and seed["held"] is False
    assert set(seed["source"]) == {"dataset", "id", "license", "url"}


def test_hint_is_ascii_bounded_and_deduplicated():
    h = core.make_hint(["A café by the sea", "a café by the sea", "Two boats."] + ["Long sentence here."] * 100)
    assert h.startswith("A cafe by the sea. Two boats.") and len(h) <= core.HINT_MAX and h.isascii()


def test_period():
    assert maps.period_of(1503) == "renaissance" and maps.period_of(1872) == "19th century" and maps.period_of(-300) == "ancient"


def test_drop_named_sentences():
    t = "A woman sits by a window. The portrait was painted by Rembrandt in Leiden. Two dogs sleep."
    assert core.drop_named(t) == "A woman sits by a window. Two dogs sleep."


def test_blocking_phrases_ties_and_shouting():
    assert maps.find("two wine glasses and a man in glasses", maps.ACCESSORY) == ["glasses"]
    assert maps.find("a dvd player", maps.ROLE) == [] and maps.find("a man in a wet suit", maps.CLOTHING) == []
    assert maps.majority(["a man", "a woman", "a man and a woman"], maps.GENDER) is None          # a tie gives nothing
    assert core.drop_named("A train at a station. THE BNSF TRAIN ARRIVES. A sign for OMNI HOTELS. A TV on a wall.") == \
        "A train at a station. A TV on a wall."


def test_strip_sealed_drops_the_whole_thing_when_its_name_is_sealed():
    spec = {"thing": {"name": "bicycle", "colour": "red", "count": "1"}, "person": {"gender": "man"}}
    assert core.strip_sealed(spec) == {"person": {"gender": "man"}}


def test_route_by_group_agrees_across_sources():
    spec = {"person": {"gender": "woman"}, "body": {"pose": "walking"}}
    for i in range(300):
        a = core.route(f"coco:{i}", spec, group=f"coco-image:{i}")[1]
        b = core.route(f"localized_narratives:{i}", spec, group=f"coco-image:{i}")[1]
        assert a == b
