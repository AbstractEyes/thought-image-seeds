"""thought_seeds: licensed image descriptions, scene graphs, museum metadata and prompts turned into hidden picture specifications
(seeds) for the text-only art thought dataset (huggingface.co/datasets/AbstractPhil/thought-symbolic-image-captions).

    from thought_seeds import read_seeds                 # read seed files (local paths or a glob)
    from thought_seeds.hub import seed_files, load        # list / download the published seeds
    from thought_seeds import core, build                 # build seeds (core loads the pinned attribute systems on first use)

Command line: `thought-seeds --sources=coco --raw=raw --out=out --fetch=1` (or `python -m thought_seeds ...`)."""
__version__ = "0.2.13"

from .io import read_seeds  # noqa: E402,F401  (light: no network, no trie)
