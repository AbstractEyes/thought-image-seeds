"""Every value a word map gives is a value of its closed list, or None (a blocking phrase): the shared maps and the importers' own
tables, so a list change in the dataset's tools fails here and never in a seed."""
from thought_seeds import core, maps
from thought_seeds.core import tp
from thought_seeds.sources import aic, cleveland, docci, gqa, met, nga


def _ok(key: str, value) -> bool:
    lst = core.closed_list(key)
    assert lst is not None, f"{key} has no closed list"
    return value is None or value in lst


def test_every_shared_map_value_is_in_its_closed_list_or_none():
    for key, mapping in maps.ALL.items():
        for phrase, value in mapping.items():
            assert _ok(key, value), (key, phrase, value)
    for phrase, rel in maps.RELATION.items():
        assert rel in tp.RELATIONS, (phrase, rel)


def test_every_period_is_in_the_period_list():
    for begin in range(-3000, 2031, 7):
        for western in (True, False):
            assert _ok("form period", maps.period_of(begin, western=western)), begin
            assert _ok("form period", maps.period_of(begin, begin + 40, western)), begin


def test_the_museum_tables_give_list_values():
    for word, (attr, value) in met.PERSON.items():
        assert _ok(f"person {attr}", value), word
    for word, value in met.ROLE_GENDER.items():
        assert _ok("person gender", value), word
    for word, (system, attr, value) in met.SCENE.items():
        assert _ok(f"{system} {attr}", value), word
    for word, value in met.SETTING.items():
        assert _ok("scene setting", value), word
    for table, key in ((met.CLASS_MEDIUM, "form medium"), (met.CLASS_TEXTURE, "form texture"),
                       (met.COLOUR_METAL, "thing colour"), (aic.STYLE_GUARD, "form style"), (nga.STYLE_ALIAS, "form style")):
        for word, value in table.items():
            assert _ok(key, value), (key, word, value)
    for word, (attr, value) in cleveland.TYPE_FORM.items():
        assert _ok(f"form {attr}", value), word
    assert met.PAINT_MEDIA <= set(core.closed_list("form medium"))


def test_the_photograph_tables_give_list_values():
    for table, key in ((gqa.POSE_PRED, "body pose"), (gqa.EXPRESSION, "look expression"),
                       (gqa.EXPRESSION_PART, "look expression"), (gqa.HAIR, "look hair"), (gqa.HAIR_PART, "look hair"),
                       (gqa.SETTING, "scene setting"), (gqa.SETTING_ATTR, "scene setting"), (gqa.WEATHER_FIELD, "scene weather"),
                       (gqa.SKY_WEATHER, "scene weather"), (gqa.ACCESSORY, "wear accessory")):
        for word, value in table.items():
            assert _ok(key, value), (key, word, value)
    for word, (value, _share) in gqa.SETTING_LARGE.items():
        assert _ok("scene setting", value), word
    for table in (gqa.PERSON, docci.PERSON_NOUNS):
        for word, (gender, age, role, *_plural) in table.items():
            assert _ok("person gender", gender) and _ok("person age", age) and _ok("person role", role), word
    for table in (gqa.REL_EXTRA, docci.REL_WORDS):
        assert set(table.values()) <= set(tp.RELATIONS)
