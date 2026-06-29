# arXiv + PRL Reading App

Mobile-first paper reading queue for daily high-energy astrophysics and high-energy phenomenology updates.

## What it does

- Fetches arXiv papers from `astro-ph.HE` and `hep-ph`.
- Uses the official arXiv API for the same two recent lists:
  - `https://arxiv.org/list/hep-ph/recent`
  - `https://arxiv.org/list/astro-ph.HE/recent`
- Fetches PRL only from the APS recent section:
  - `https://journals.aps.org/prl/recent?toc_section%5B%5D=cosmology-astrophysics-and-gravitation`
- Serves a static web app that works on GitHub Pages.
- Stores like, dislike, and hidden states in the browser with `localStorage`.
- Exports liked papers as CSV.

## Local preview

From this folder:

```bash
python3 -m http.server 8000
```

Then open:

```text
http://localhost:8000
```

## Fetch latest papers locally

```bash
python3 scripts/fetch_papers.py
```

This writes:

- `data/latest.json`
- `data/YYYY-MM-DD.json`

The script uses only Python standard-library modules.

## GitHub Pages deployment

1. Create a GitHub repository.
2. Push this folder to the repository.
3. In GitHub repository settings, enable GitHub Pages from the main branch.
4. Enable GitHub Actions.
5. The included workflow runs every day and updates `data/latest.json`.

## Notes

- arXiv categories map directly to the desired fields:
  - `astro-ph.HE`
  - `hep-ph`
- The arXiv recent pages are recorded as source URLs, while the script uses arXiv's official API because it returns structured title, author, abstract, and PDF metadata.
- PRL is parsed only from the APS `cosmology-astrophysics-and-gravitation` recent page. If APS returns a Cloudflare challenge to non-browser requests, the script prints a warning and skips PRL rather than substituting guessed Crossref results. A Crossref fallback exists behind `--allow-prl-fallback`, but it is off by default because Crossref does not identify the APS section exactly.
- Browser state is local to the current browser. Use CSV export to keep a permanent copy of liked papers.
# arxiv-journal-reading-web
