# Scripts

## `fetch_papers.py`

Fetches paper metadata for the static app.

Sources:

- arXiv API for `astro-ph.HE`
- arXiv API for `hep-ph`
- APS PRL recent page for `cosmology-astrophysics-and-gravitation`

The arXiv API is used instead of scraping the HTML recent pages because it provides structured abstracts and PDF links for the same categories:

- `https://arxiv.org/list/hep-ph/recent`
- `https://arxiv.org/list/astro-ph.HE/recent`

The PRL source is exactly:

- `https://journals.aps.org/prl/recent?toc_section%5B%5D=cosmology-astrophysics-and-gravitation`

Run from the project root:

```bash
python3 scripts/fetch_papers.py
```

The script writes JSON files into `data/`.
