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


def _spec(text):
    return textspec.spec_from_text(text)[0].spec()


def test_a_number_counts_only_the_noun_it_stands_before():
    for text in ("portrait of a 25 year old man", "portrait of a 2 5 year old man with wavey brown hair",
                 "a beautiful young 20 year old male", "a twelve years old girl"):
        p = _spec(text)["person"]
        assert p["count"] == "1" and "age" not in p, text           # an age is no count, and '25 year old man' is not elderly
    assert _spec("a 48 year old tree")["thing"] == {"name": "tree", "count": "1"}
    assert "count" not in _spec("photograph of a family of 6 eating pizza")["thing"]     # 6 counts the family
    assert "count" not in _spec("six meters tall mech")["thing"]                          # a measure
    assert "count" not in _spec("a 8 winged 4 armed angel")["thing"]                      # a compound modifier
    assert "person" not in _spec("metin 2 warrior hiking in the mountains")               # a title's number
    assert "count" not in _spec("tandy trs 80 computer")["thing"]
    assert _spec("three cats on a sofa")["thing"]["count"] == "3"
    assert _spec("two men and a woman")["person"]["count"] == "3"
    assert _spec("a tall horse next to a red car")["thing"]["count"] == "1"
    assert _spec("a horned owl with a graduation cap")["thing"]["count"] == "1"
    assert _spec("two smiling women")["person"]["count"] == "2"


def test_a_count_covers_every_person_the_text_names():
    assert _spec("a father and a son playing tennis")["person"]["count"] == "2"
    assert "count" not in _spec("a grandmother reading a book to her grandson and granddaughter")["person"]


def test_person_words_that_name_no_person():
    for text in ("a chess queen to the right of a chess knight", "chess king piece holding a shotgun", "the king of all the mice",
                 "a baby daikon radish in a tutu", "orange jello in the shape of a man", "a robot with a human white skull",
                 "two fighters grappling in closed guard", "a castle, substance 3d painter, octane render",
                 "father christmas driving a yellow sports car", "The old man the boat.", "a drawing made by a child",
                 "gate in the courtyard of a colorful kitsune wizard college", "a marble statue of a woman"):
        assert "person" not in _spec(text), text
    assert _spec("an oil painting of the royal raccoon king")["thing"]["name"] == "raccoon"
    assert _spec("a man with puppet that looks like a king")["person"] == {"count": "1", "gender": "man"}
    assert _spec("a baby sleeping in a crib")["person"] == {"count": "1", "age": "baby"}
    assert _spec("a horse rider in a field")["person"]["role"] == "rider"           # a role keeps its person


def test_a_guise_is_no_person():
    for text in ("a corgi as a knight", "a cat dressed as a pirate", "a gorilla astronaut", "a frog knight", "a cat chef cooking",
                 "a chimpanzee, dressed as wonder woman", "roses that resemble a beautiful teen girl",
                 "surreal photography by man ray"):
        assert "person" not in _spec(text), text
    assert _spec("a gorilla astronaut")["thing"]["name"] == "gorilla"
    assert _spec("a corgi as a knight")["thing"]["name"] == "corgi"
    assert _spec("an armored granite wombat warrior statue holding a broad sword")["thing"]["name"] == "statue"
    assert _spec("a woman dressed as a pirate")["person"] == {"count": "1", "gender": "woman"}     # one person, not two
    assert _spec("a horse rider")["person"] == {"role": "rider"}                                     # who rides the horse
    assert "role" not in _spec("portrait of a man, painting by dutch painter vermeer")["person"]     # the maker


def test_a_gender_or_role_holds_for_every_person():
    for text in ("a girl and a boy", "a man and a woman", "A boy holds and a girl paints a piece of wood.", "a father and a son",
                 "a mother holding her baby", "a beautiful young female doctor talking with a nurse", "a mother daughter photo"):
        p = _spec(text).get("person", {})
        assert "gender" not in p and "role" not in p, text
    assert _spec("a beautiful young female doctor talking with a nurse")["person"]["count"] == "2"
    assert _spec("an elderly woman")["person"] == {"count": "1", "gender": "woman", "age": "elderly"}   # one person, two words
    assert _spec("two female soldiers")["person"] == {"count": "2", "gender": "woman", "role": "soldier"}
    assert _spec("a female cowboy")["person"] == {"count": "1", "gender": "woman"}          # the gender word, not the role's
    assert _spec("a young female elven warrior")["person"] == {"gender": "woman"}
    assert _spec("two men")["person"] == {"count": "2", "gender": "man"}
    assert _spec("an asian female tourist with a modern tourist look")["person"]["count"] == "1"   # 'tourist look' is a style


def test_a_relation_binds_its_own_subject_and_object():
    for text in ("beautiful woman from the back facing away from the camera", "A boy holds and a girl paints a piece of wood.",
                 "driftwood and sea agate beside a sandcastle", "a pickup truck under street lights at night",
                 "a crowd of people watching fireworks by a city", "There is a river in front of them with water lilies.",
                 "wolf technician wearing headphones and glasses standing in front of a coastal skyline",
                 "a woman not holding an umbrella", "a woman looking at the camera"):
        assert "relation" not in _spec(text), text
    assert "camera" not in str(_spec("beautiful woman from the back facing away from the camera"))   # the viewer, no thing
    assert "wear" not in _spec("a woman not holding an umbrella")
    for text, rel in (("a dog sitting next to a cat", ("dog", "beside", "cat")), ("a red car to the left of two dogs",
                      ("car", "left of", "dog")), ("a man holding a cat", ("man", "holding", "cat")),
                      ("a woman with long hair next to a luminescent bird", ("woman", "beside", "bird")),
                      ("a glass of orange juice to the right of a plate", ("orange juice", "right of", "plate")),
                      ("a full moon rising above a mountain at night", ("moon", "above", "mountain"))):
        assert _spec(text)["relation"] == [{"a": rel[0], "rel": rel[1], "b": rel[2]}], text


def test_things_inside_the_scene_are_not_the_pictures_form():
    assert "form" not in _spec("a yellow wall with a large framed oil painting of a car")
    assert "form" not in _spec("a blue wall with a large framed watercolor painting of a mountain")
    assert "form" not in _spec("a cat reading a comic book")
    assert "scene" not in _spec("A television made of water that displays an image of a cityscape at night.")
    assert "shot" not in _spec("a yellow diamond-shaped sign with a deer silhouette")
    assert _spec("An oil painting of two rabbits in the style of American Gothic")["form"] == {"medium": "oil painting"}
    assert "scene" not in _spec("a cat in the style of the starry night")
    assert "form" not in _spec("Wood engraving of the Greek letter Omega")          # an engraving is no woodcut
    assert _spec("an oil painting of a cat")["form"] == {"medium": "oil painting"}
    assert _spec("a portrait of a woman, oil painting")["form"] == {"medium": "oil painting"}
    assert _spec("a cat, in the style of an oil painting")["form"] == {"medium": "oil painting"}
    assert _spec("a comic book illustration of a cat") == {"thing": {"name": "cat", "count": "1"}, "form": {"style": "comic"}}
    assert _spec("a silhouette of a man at sunset")["shot"] == {"light": "silhouette"}
    assert "scene" not in _spec("no rain over a quiet street")


def test_a_setting_needs_a_place_and_three_quarters_is_not_frontal():
    for text in ("a jungle gym with three kids on it", "a windmill farm next to a country road", "Hokusai's version of Animal Farm",
                 "farm animals made out of cheese and ham, on a wooden board", "graffiti spelling BE KIND on white subway tile",
                 "a decorative plaque from a reliquary shrine"):
        assert "scene" not in _spec(text), text
    assert _spec("a farm at dawn")["scene"] == {"setting": "farm", "time": "dawn"}
    assert _spec("a monkey in the jungle")["scene"] == {"setting": "forest"}
    assert _spec("Three-quarters front view of a blue 1977 Corvette")["shot"] == {"angle": "three quarter"}
    assert _spec("front view of a red car")["shot"] == {"angle": "frontal"}


def test_finish_routes_by_the_group():
    s = core.Spec()
    s.set("wear", "clothing", "jeans")                                           # a sealed clothing value
    s.set("body", "pose", "standing")
    held = next(f"g:{i}" for i in range(500) if core.held_pick(f"g:{i}"))
    kept = next(str(i) for i in range(500) if not core.held_pick(f"test:{i}"))
    assert textspec.finish("test", kept, s, group=held) == s.spec()             # the group's draw, not the seed id's


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
