"""The shared prompt-text parser (thought_seeds.textspec) on inline texts."""
from thought_seeds import core, textspec


def test_parser_guards():
    s, _ = textspec.spec_from_text("a baby elephant in studio lighting next to wine glasses, pastel colors")
    spec = s.spec()
    assert "person" not in spec and spec["thing"]["name"] == "elephant"
    assert "scene" not in spec and spec["shot"]["light"] == "studio flash" and "form" not in spec
    assert textspec.domain_of("a logo of a fox") == "design" and textspec.domain_of("dslr photo of a fox") == "photograph"
    assert textspec.domain_of("an oil painting of a fox") == "painting" and textspec.domain_of("a fox, digital art") == "illustration"
    assert textspec.is_explicit("a nude figure") and not textspec.is_explicit("a nudibranch")
    assert textspec.strip_phrases("A cat in the style of Vincent Van Gogh, Egyptian art by Egyptian masters") == \
        "A cat, Egyptian art by Egyptian masters"


def test_a_blocking_phrase_is_passed_over():
    spec = textspec.spec_from_text("a man in a wetsuit and a red jacket")[0].spec()
    assert spec["wear"] == {"clothing": "jacket", "colour": "red"}                 # 'wetsuit' gives nothing and stops nothing
    assert "person" not in textspec.spec_from_text("a dvd player on a shelf")[0].spec()


def test_a_hyphenated_word_is_one_word():
    spec = textspec.spec_from_text("snow-capped mountains under a clear sky, a neo-noir city")[0].spec()
    assert spec["scene"]["weather"] == "clear" and "style" not in spec.get("form", {})


def test_finish_drops_a_wear_colour_whose_sealed_garment_was_stripped():
    s = core.Spec()
    s.set("person", "gender", "man")
    s.set("wear", "clothing", "jeans")                                           # a sealed clothing value
    s.set("wear", "colour", "blue")
    s.set("body", "pose", "standing")
    kept = next(str(i) for i in range(200) if not core.held_pick(f"test:{i}"))
    held = next(str(i) for i in range(200) if core.held_pick(f"test:{i}"))
    assert core.route(f"test:{kept}", s.spec())[0]["wear"] == {"colour": "blue"}  # the core strips the garment only
    assert textspec.finish("test", kept, s) == {"person": {"gender": "man"}, "body": {"pose": "standing"}}
    assert textspec.finish("test", held, s) == s.spec()
