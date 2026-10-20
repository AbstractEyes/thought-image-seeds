"""The seed core and the word maps against the dataset's tools (the final seal)."""
from thought_seeds import core, maps
from thought_seeds.core import tp


def test_find_longest_first_and_bounded():                                  # (the maps' values: tests/test_maps.py)
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


def test_ascii_text_folds_typographic_punctuation():
    dash, apos, lq, rq = chr(0x2013), chr(0x2019), chr(0x201C), chr(0x201D)
    assert core.ascii_text(f"ca. 1888{dash}89") == "ca. 1888-89"                 # not '188889'
    assert core.ascii_text(f"Van Gogh{apos}s room") == "Van Gogh's room"           # not 'Goghs'
    assert core.ascii_text(f"a sign that reads {lq}OPEN{rq}") == 'a sign that reads "OPEN"'
    assert core.ascii_text(f"8{chr(0x00BD)} x 11 in., caf{chr(0x00E9)}") == "8 1/2 x 11 in., cafe"


def test_hyphen_is_not_a_word_boundary():
    assert maps.find("post-impressionism", maps.STYLE) == [] and maps.find("neo-gothic", maps.STYLE) == []
    assert maps.find("impressionism", maps.STYLE) == ["impressionism"]
    assert maps.find("a close-up of a face, low-angle", maps.FRAMING) == ["close-up"]
    assert maps.find("a close-up of a face, low-angle", maps.ANGLE) == ["low angle"]


def test_intaglio_prints_are_not_etching():
    for t in ("engraving", "drypoint", "aquatint", "line engraving"):
        assert maps.find(t, maps.MEDIUM) == [], t
    assert maps.find("wood engraving", maps.MEDIUM) == []          # end grain cut with engraving tools: not a woodcut
    assert maps.find("etching and aquatint", maps.MEDIUM) == ["etching"]
    assert "etching" not in [v for k, v in maps.MEDIUM.items() if k != "etching"]


def test_period_european_eras_only_for_western_art():
    assert maps.period_of(1503) == "renaissance" and maps.period_of(1503, western=False) is None
    assert maps.period_of(1650, 1680) == "baroque" and maps.period_of(1650, 1680, western=False) is None
    assert maps.period_of(1590, 1610) is None                                     # a span across two periods
    assert maps.period_of(1850, 1859, western=False) == "19th century" and maps.period_of(-300, "", False) == "ancient"


def test_role_lookup_of_plurals():
    assert maps.lookup("cyclists", maps.ROLE) == "rider" and maps.lookup("bikers", maps.ROLE) == "rider"
    assert maps.lookup("swimmers", maps.ROLE) == "swimmer" and maps.lookup("Monks", maps.ROLE) == "monk"
    assert maps.lookup("dvd players", maps.ROLE) is None and maps.lookup("astronauts", maps.ROLE) is None


def test_date_marks_pass_drop_named_when_allowed():
    assert core.drop_named("Made about 500 BCE.") == ""                           # an all-capitals word: a possible name
    assert core.drop_named("Made about 500 BCE.", allow=core.DATE_MARKS) == "Made about 500 BCE."


def test_strict_name_filter():
    vocab = core.corpus_vocab(["The potter shaped the bowl. It was perhaps a gift.",
                               "A bowl by the potter. It is perhaps the oldest."])
    assert {"potter", "perhaps"} <= vocab and "rose" not in core.corpus_vocab(["a rose. a rose. a rose."])   # a given name
    text = ("Caillebotte captured a busy street. A man and a woman walk under one umbrella. The street was painted by J. "
            "Here White balanced the light. The signature reads CLAUDE MONET. The cup dates to 500 BCE. Perhaps the potter "
            "made it for feast XII.")
    assert core.drop_named_strict(text, vocab) == ("A man and a woman walk under one umbrella. The cup dates to 500 BCE. "
                                                   "Perhaps the potter made it for feast XII.")


def test_sentences_keep_initials_and_abbreviations_with_their_name():
    t = ("J. M. W. Turner admired the street. A statue of St. Francis stands in the garden. Made ca. 1850 in a shop. A stamnos "
         "(pl. stamnoi) held wine. Two boats.")
    assert core.sentences(t) == ["J. M. W. Turner admired the street.", "A statue of St. Francis stands in the garden.",
                                 "Made ca. 1850 in a shop.", "A stamnos (pl. stamnoi) held wine.", "Two boats."]
    assert core.sentences("Mt. Fuji rises behind the lake. Mr. Brown waves.") == ["Mt. Fuji rises behind the lake.",
                                                                                  "Mr. Brown waves."]


def test_strict_filter_drops_the_sentence_and_not_a_fragment():
    vocab = core.corpus_vocab(["The cup is on a table. The cup holds tea. A lion fights a demigod. The lion is large."])
    # the whole sentence of a saint or an initial goes, never a one-word fragment of it ('Francis.', 'Turner admired ...')
    assert core.drop_named_strict("A statue of St. Francis stands here. The cup is blue. J. M. W. Turner admired it.", vocab) == \
        "The cup is blue."
    # a surname the text introduces in full ('Gabriel Salmon ... Salmon emphasized'), a lower-case fragment, an inscription
    t = ("Gabriel Salmon cut the block. Salmon emphasized the violent action. on right). The lion fights a demigod. There are "
         "mock inscriptions in the field. The cup bears an ad monogram.")
    assert core.drop_named_strict(t, vocab) == "The lion fights a demigod."


def test_name_tokens_and_plain_words():
    assert core.name_tokens(["King George III", "Workshop of Jean-Baptiste Oudry", "French 18th-century"]) == \
        {"george", "jean-baptiste", "jean", "baptiste", "oudry", "french"}            # no title, role, ordinal or numeral
    assert core.name_tokens(["Jean-Baptiste Oudry (French)"], skip={"french"}) == {"jean-baptiste", "jean", "baptiste", "oudry"}
    assert core.plain_words(["It may rain.", "We may go, rose by rose.", "Rose Bonheur painted it."]) == {"may", "rose"}
    assert core.plain_words(["It may rain.", "Rose Bonheur"], min_count=2) == set()


def test_name_lists_count_a_rare_word_in_any_case_and_an_ordinary_word_as_an_opener():
    own = core.NameList({"schulze", "church", "may"}, plain={"church", "may"})
    assert own.rare == {"schulze"} and own.common == {"church", "may"}
    assert own.hits("A label of h. schulze is on the back.") and own.hits("Church painted the falls.")
    assert not own.hits("The church stands on a hill.") and not own.hits("It may rain.")
    assert not own.hits("Church painted the falls.", opening=False)
    titled = core.NameList(set(), plain=set(), openers={"guardhouse"})     # a title's words count only as a capitalized opener
    assert not titled.hits("Soldiers play cards in a guardhouse.") and titled.hits("Guardhouse scenes were popular.")
    # the source's whole list counts its rare words only; the record's own list counts its ordinary words as an opener too
    assert not core.holds_name("Church painted the falls.", names=own) and core.holds_name("Church painted the falls.", own=own)
    assert core.holds_name("a note by schulze", names=own) and not core.NameList(set())


def test_strict_filter_with_the_name_lists():
    vocab = core.corpus_vocab(["The church stands on a hill. The church is white. A label is on the back. The label is small."])
    plain = core.plain_words(["the church on a hill", "a church", "the label", "a label"])
    own = core.NameList(core.name_tokens(["Frederic Edwin Church (American, 1826-1900)"]), plain)
    names = core.NameList(core.name_tokens(["H. Schulze", "Frederic Edwin Church"]), plain)
    t = ("Church's considerable skills made him famous. The church stands on a hill. A label of h. schulze is on the back. "
         "A white church stands on a hill.")
    assert core.drop_named_strict(t, vocab, names=names, own=own) == "The church stands on a hill. A white church stands on a hill."
    assert "Church's" in core.drop_named_strict(t, vocab, names=names)      # an ordinary word opens a sentence of another record


def test_image_talk_goes_and_the_rest_stays():
    t = ("The image shows a jug with a lid. In this image, a man rides a horse. An image of a kitten on a rug. This image is one of "
         "a set. The sheet was scanned at high resolution. The pixels of the sky are blue. Two boats float.")
    assert core.without_image_talk(t) == "A jug with a lid. A man rides a horse. A kitten on a rug. Two boats float."
    assert core.without_image_talk("The image file is large. A cup.") == "A cup."


def test_cohere_keeps_an_age_only_for_one_fitting_person():
    assert core.cohere({"person": {"age": "child"}}) == {}
    assert core.cohere({"person": {"count": "2", "age": "child", "gender": "man"}}) == {"person": {"count": "2", "gender": "man"}}
    assert core.cohere({"person": {"count": "1", "age": "child", "gender": "man"}}) == {"person": {"count": "1", "gender": "man"}}
    ok = {"person": {"count": "1", "age": "child", "gender": "girl"}}
    assert core.cohere(ok) == ok


def test_a_shared_picture_is_recorded_for_the_build():
    core.PICTURES.clear()
    s = core.Spec()
    s.set("thing", "name", "cup")
    s.set("scene", "setting", "kitchen")
    assert core.make_seed("wikidata", "Q5", "painting", "still life", s, "", "CC0 1.0", "https://www.wikidata.org/wiki/Q5",
                          group="met:1")
    assert core.make_seed("coco", "9", "photograph", "food", s, "", "CC BY 4.0", "https://cocodataset.org", group="coco-image:9")
    assert core.PICTURES == {"wikidata:Q5": "met:1"}                    # COCO's own family needs no record
    core.PICTURES.clear()
