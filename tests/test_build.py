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
