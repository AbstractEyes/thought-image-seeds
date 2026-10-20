"""The published seeds on the Hugging Face Hub (the dataset repo's seeds/ folder): list and download them."""
from __future__ import annotations

from .io import read_seeds

DATASET_REPO = "AbstractPhil/thought-symbolic-image-captions"


def seed_files(source: str | None = None, repo: str = DATASET_REPO, revision: str | None = None) -> list:
    """The seed shards on the Hub (paths inside the repo), all sources or one."""
    from huggingface_hub import HfApi
    files = HfApi().list_repo_files(repo, repo_type="dataset", revision=revision)
    prefix = f"seeds/{source}/" if source else "seeds/"
    return sorted(f for f in files if f.startswith(prefix) and f.endswith(".jsonl"))


def load(source: str | None = None, repo: str = DATASET_REPO, revision: str | None = None, **filters):
    """Download the shards of one source (or all) and iterate their seeds; filters as read_seeds (domain=, held=)."""
    from huggingface_hub import hf_hub_download
    paths = [hf_hub_download(repo, f, repo_type="dataset", revision=revision) for f in seed_files(source, repo, revision)]
    return read_seeds(paths, **filters)
