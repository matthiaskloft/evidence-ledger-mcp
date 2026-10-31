"""Real open-access PDFs for the link-resolution tests, fetched from their publishers and cached
locally (tests/.pdf-cache, git-ignored), never committed, so the repository does not republish
them. Tests using them are marked `network`; once cached, they run offline.

- Ioannidis JPA (2005). Why most published research findings are false. PLoS Medicine 2(8): e124.
  https://doi.org/10.1371/journal.pmed.0020124 (CC BY)
- Jiang AQ, Sablayrolles A, Mensch A, et al. (2023). Mistral 7B. arXiv:2310.06825v1. (CC BY 4.0)
- Sulpis O, Humphreys MP, Wilhelmus MM, et al. (2022). RADIv1: a non-steady-state early
  diagenetic model for ocean sediments in Julia and MATLAB/GNU Octave. Geoscientific Model
  Development 15: 2105-2131. https://doi.org/10.5194/gmd-15-2105-2022 (CC BY 4.0)
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

CACHE = Path(__file__).parent / ".pdf-cache"
SOURCES = {
    "ioannidis2005.pdf": (
        "https://journals.plos.org/plosmedicine/article/file"
        "?id=10.1371/journal.pmed.0020124&type=printable",
        "ffc1005680cb620eec4c913437dfabbf311b535cfe16cbaeb2faec1f92afc362",
    ),
    "mistral7b-2023.pdf": (
        "https://arxiv.org/pdf/2310.06825v1",
        "dfbac4e7035344b305c947481f2e7e8a02f7a24a563917eb6e47f6591d14c5ae",
    ),
    "sulpis2022-radi.pdf": (
        "https://gmd.copernicus.org/articles/15/2105/2022/gmd-15-2105-2022.pdf",
        "6a84b05f5308ae364e2fb9cbf37a5ab5992d25e1f7419144057a7068a5d7bde4",
    ),
}


def real_pdf(name: str) -> Path:
    """The cached PDF, downloaded first if needed; fails if the publisher's file has changed,
    since the tests expect its pages as they were."""
    url, digest = SOURCES[name]
    path = CACHE / name
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "evidence-ledger-mcp tests"})
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
        if hashlib.sha256(body).hexdigest() != digest:
            raise AssertionError(f"{name}: the download from {url} has changed")
        CACHE.mkdir(exist_ok=True)
        path.write_bytes(body)
    return path
