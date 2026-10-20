"""The runner's source list and the attribution files (no network, no raw data)."""
from thought_seeds import build, core


def test_the_eleven_sources_and_not_the_parser():
    assert build.available() == list(build.ORDER)          # thought_seeds.textspec sits beside sources/, not in it


def test_docs_name_every_source_with_a_permissive_license(tmp_path):
    build.docs(str(tmp_path))
    rows = [r for r in (tmp_path / "LICENSES.md").read_text(encoding="utf-8").splitlines() if r.startswith("| ")][1:]
    assert [r.split(" | ")[0][2:] for r in rows] == list(build.ORDER)
    for m in map(build.module, build.ORDER):
        for part in m.LICENSE.split(";"):                  # aic: the records CC0, the description hints CC BY 4.0
            assert core.tp.permissive(part.split("(")[0].strip()), (m.DATASET, m.LICENSE)
        assert m.CITATION.strip().startswith("@") and m.ATTRIBUTION and m.TAKEN and m.URL.startswith("https://")
    bib = (tmp_path / "CITATIONS.bib").read_text(encoding="utf-8")
    assert all(m.CITATION.strip() in bib for m in map(build.module, build.ORDER))


def test_every_cc_by_row_links_the_license_and_says_what_was_changed(tmp_path):
    build.docs(str(tmp_path))
    rows = {r.split(" | ")[0][2:]: r for r in (tmp_path / "LICENSES.md").read_text(encoding="utf-8").splitlines()
            if r.startswith("| ") and not r.startswith("| source")}
    by = "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)"
    for name, row in rows.items():
        m = build.module(name)
        if "CC BY" in m.LICENSE:
            assert by in row, name                                          # CC BY 4.0 3(a)(1)(C): the license text linked
        cells = row.split(" | ")
        assert len(cells) == 6 and ("modified" in cells[4] or "transformed" in cells[4]), name     # 3(a)(1)(B)
    for name in ("met", "cleveland", "nga"):
        assert "transformed" in build.module(name).MODIFIED                 # the museums' own ask: data changed is marked
    assert "https://www.artic.edu/terms" in rows["aic"]                     # the API's terms, disclosed in the row
    readme = (tmp_path / "seeds" / "README.md").read_text(encoding="utf-8")
    assert by in readme
    assert build.license_cell("CC0 1.0 (records); CC BY 4.0 (description hints)") == (
        "[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (records); "
        "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (description hints)")
