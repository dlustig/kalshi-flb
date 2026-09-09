# Publishing Almost Certain

Almost Certain is a static exhibit of the saved July 2026 research snapshot.
Building or previewing the page does not collect trades, open DuckDB, or rerun
the statistics. The Python collector and analysis remain separate workflows.

## Build and preview

From the repository root, with Python 3.12 available:

```bash
python scripts/build_exhibit.py --out dist/site
python -m http.server --bind 127.0.0.1 8000 --directory dist/site
```

Open `http://localhost:8000`. The publication builder uses the Python standard
library. Installing the analysis environment is only necessary for the research
pipeline and Python test suite. Browser JavaScript is shipped as native modules;
there is no npm install or browser-side analytics runtime.

To exercise project-subdirectory hosting:

```bash
python scripts/build_exhibit.py --out dist/preview/almost-certain
python -m http.server --bind 127.0.0.1 8000 --directory dist/preview
```

Then open `http://localhost:8000/almost-certain/`. Asset links are relative;
selected lab views live in the URL fragment and need no server routing.

The default source link points at the current public research repository. If the
source repository moves, set its actual public URL when building:

```bash
python scripts/build_exhibit.py --out dist/site --source-url https://github.com/dlustig/kalshi-flb
```

The source repository URL and the static hosting URL are different concepts.
Moving the static page to Bitbucket does not require silently changing the
research repository's remote or making a private source repository public.

## Generated files and source ownership

| File | Owner |
|---|---|
| `web/exhibit.html` | Editorial HTML template |
| `web/exhibit.css` | Visual design, responsive and print rules |
| `web/exhibit-model.mjs` | Supported selections and saved-data view preparation |
| `web/exhibit-charts.mjs` | SVG rendering and data annotations |
| `web/exhibit.mjs` | Controls, URL state, fetch/retry, and accessible announcements |
| `web/data/stats.json` | Existing analytical export; regenerate with `scripts/build_site_data.py` only when intentionally publishing new statistics |
| `web/snapshot.json` | Descriptive provenance of the selected research snapshot |
| `web/index.html`, `web/data/manifest.json`, `web/evidence/`, generated SVGs | Outputs of `scripts/build_exhibit.py`; never hand-edit |
| `dist/site/` | Portable publication output; ignored by Git |

Build into `web/` to refresh the committed preview artifacts, or into `dist/site/`
to obtain only the portable release files. The manifest records input/output
hashes and distinguishes the historical analysis date from the website build
date. Preserve the evidence alongside the page.

## What reproduction means here

The public bundle reproduces the presentation of saved results: charts, numeric
tables, captions, and report downloads. It does not contain the approximately
72GB raw database. Reproducing the statistical estimates from trades requires
the matching inputs and analytical environment. A new backfill queries a changing
public API and is not guaranteed to reconstruct an identical historical snapshot.

The repository's DQ gate remains mandatory before trusting a new analysis. It
also checks collection coverage through the current month, so running it against
an intentionally frozen July database later in the year can fail freshness even
when its structural checks pass. Preserve and report the actual gate result;
never present an archived PASS as a fresh full PASS. The snapshot is visibly dated
and does not promise live or complete current-market coverage.

The memory and disk safety rules in [AGENTS.md](../AGENTS.md) apply to any heavy
collection, DQ, dedupe, or report command. The existing statistical exporter also
reads raw-trade metadata; it is not needed for a typography or layout change.

## Bitbucket Cloud destination

The owner confirmed the existing GitHub destination on September 9, 2026:
[`dlustig/kalshi-flb`](https://github.com/dlustig/kalshi-flb), with the Pages
workflow publishing `main` to <https://dlustig.github.io/kalshi-flb/>. The
Bitbucket instructions below remain an optional hosting alternative; no
repository migration is required for this release.

Atlassian documents static hosting through a repository named
`<workspaceid>.bitbucket.io`, with an `index.html` in its root. One workspace hosts
one site; subdirectories can contain their own `index.html`. The selected main
branch supplies the files, JavaScript is supported, and server-side execution is
not. Pages may be cached for 15 minutes. The site is public even if its backing
repository is private. See
[Atlassian's static website documentation](https://support.atlassian.com/bitbucket-cloud/docs/publishing-a-website-on-bitbucket-cloud/).

For an existing portfolio, prefer an `almost-certain/` subdirectory. Once the
exact hosting repository is known, use a separate checkout of that repository,
inspect its current files, and copy the reviewed `dist/site/` contents into the
chosen project folder. Preserve unrelated portfolio files. Commit and push to
the hosting branch only with the required user authority; this research repo
has an explicit no-auto-commit rule.

For a new standalone site, the same bundle can occupy the repository root.
Only the generated public bundle belongs in the hosting repository. No database,
credentials, session state, or development environment is required there.

The existing GitHub Pages workflow remains supported during the transition.
It builds the same portable release before upload. Changing hosts is a deployment
choice, not a reason to remove the existing workflow or rewrite Git history.

## Verification before publication

```bash
uv run pytest
node --test tests/web/*.test.mjs
node --check web/exhibit-model.mjs
node --check web/exhibit-charts.mjs
node --check web/exhibit.mjs
python scripts/build_exhibit.py --out dist/site
git diff --check
```

There is no configured project typecheck command. Node syntax checks and tests
do not substitute for one; this fact is recorded rather than inventing a command.

Check the final built page at desktop and phone widths, under the actual site
subdirectory, with keyboard navigation and JavaScript disabled. Exercise all
three lab views, shared URL reload/back, empty selections, retry after a failed
fetch, and print. Check every source/download link and compare displayed values
to the dated bundle. After deployment, open the actual HTTPS URL and verify both
the page and its assets; allow for Bitbucket's cache before concluding a deploy
did not take effect.
