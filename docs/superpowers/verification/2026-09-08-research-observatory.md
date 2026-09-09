# Almost Certain verification record

Initial verification: 2026-09-08. Local release verified; whole-change review approved.
GitHub destination and commit/push authority confirmed on September 9; see below.

## Scope and workspace

The approved field-notebook exhibit was implemented on
`feat/research-observatory`, based on `b420537`, in the isolated worktree
`.superpowers/worktrees/research-observatory`. The initial handoff was uncommitted.
Existing untracked files in the original checkout are preserved.

The deliverable is a portable static publication of the July 2026 research
snapshot. No new collection, trading functionality, authenticated API usage,
or statistical inference in the browser is part of the change.

## Baseline

`PYTHONPATH=src .venv/bin/python -m pytest -q` in the original checkout passed:
49 tests, 17.56 seconds. Python is 3.12.13; Node is 22.13.1.

No project typecheck command is configured in `pyproject.toml`. JavaScript
syntax and model tests are recorded separately and are not called typechecks.

## Implementation verification

After the publication-builder review fixes, the controller ran the complete
Python suite in the worktree:

```text
PYTHONPATH=src .venv/bin/python -m pytest -q
65 passed in 16.27s
```

This includes the 49 existing research tests and 16 publication tests. The
independent builder review is approved: self-contained SVG styling, visible
data-derived hero labels/ticks, public-readable file permissions, required
declared DQ evidence, and explicit rejection of clipped headline intervals were
verified after regression tests.

Whole-change review then independently reproduced a console-entry-point import
failure that `python -m pytest` had masked: the new tests could not import the
standalone `scripts` namespace. The controller reproduced it before fixing it.
Pytest now explicitly adds `src` and the repository root to its import path;
runtime dependencies and analytical source are unchanged. The bare console
publication tests passed (16 tests), followed by the controller's final full run:

```text
uv --no-cache run --no-sync --frozen pytest -q
65 passed in 16.27s
```

This uses the canonical pytest console entry point in the existing installed
environment. `--no-sync` avoids reinstalling the shared local environment and
`--no-cache` avoids unnecessary cache writes; neither changes pytest's import
behavior. Hosted CI installation/execution remains unclaimed.

The controller also ran `node --test tests/web/*.test.mjs` successfully. This
environment summarizes that invocation by test file; running
`node tests/web/exhibit-model.test.mjs` confirmed all nine named behaviors pass.
All three `node --check web/exhibit-*.mjs` checks passed. Final changes to browser
event handling were syntax-checked and exercised directly in fresh browsers.

## Browser and publication checks

The controller independently checked the actual built page under
`http://localhost:36121/almost-certain/`, not only the source template:

- All 126 supported mode/category/period combinations matched expected saved
  table-row counts and category headline values, kept missing estimates missing,
  exposed no invented category-curve intervals, and produced finite SVG geometry.
- Default/reset, escaped shared state, reload, Back and Forward, normal chapter
  anchors, and invalid shared state were exercised. A same-document invalid hash
  initially lost its notice because both `popstate` and `hashchange` restored it;
  one fragment-event handler fixed this. The final notice stays visible.
- Clipboard rejection exposes the full selected URL in a readonly input.
- JavaScript-disabled 390px rendering retains five SVG figures, a working native
  20-row values table, disabled interactive controls, and an explicit post-only
  static caption. It has no horizontal page overflow.
- A simulated JSON HTTP 503 retains the static figure and disabled controls;
  retry restores forty default chart targets and hides the error. This deliberate
  error was isolated from the clean-session console check.
- A fresh interactive session produced no page/console errors and no external
  runtime requests. The project uses local assets and no project analytics.
- Keyboard datum focus updates the annotation. After a reproduced resize bug,
  redraw now preserves the selected marker and equivalent focus; focusing a
  different control before resize does not have its focus stolen.
- Reduced motion yields automatic scrolling and no active animations. Actual A4
  PDFs were produced for all three modes. The original screen-width SVG made
  print labels too small; fixed print rendering uses a 640-unit width and restores
  responsive width afterward. Printed labels, active captions and values remain
  readable; controls are absent. The controller visually inspected the category
  print page, not just its CSS.
- Opening, default lab and engineering screenshots were inspected against the
  approved mockup. Final mobile document width is 390px and chart width is 348px;
  category labels remain horizontal and readable. Final desktop is 1440px.

The release is generated at `dist/site/`; the committed-preview outputs are in
`web/`. A portable ZIP is `dist/almost-certain.zip`; `unzip -t` reports no errors.
The controller verified all 14 input hashes and 17 output hashes, all
local HTML/module/report-image references, unique static IDs, and public-readable
file permissions. Initial HTML/CSS/modules/data total 249,885 bytes; the complete
bundle totals 456,014 bytes. Optional evidence downloads are outside the initial
payload. These are uncompressed local file sizes, not network benchmarks.

The public source repository was opened successfully, and a direct HTTP request
to the revision-pinned methodology URL returned 200. No hosted CI execution or
Bitbucket public-page verification has occurred.

Task-scoped independent reviews are approved after fixes. The controller verified
material findings directly rather than treating review reports as test results.
Final whole-change review is also approved with no unresolved findings, including
focused confirmation that the canonical console entry point now collects all
publication tests. Its original failure and resolution remain in the review log.
The review/screenshot/PDF ledger is retained under the original checkout's
`.superpowers/sdd/2026-09-08-research-observatory/` while work remains uncommitted.

## Data evidence

The original `data/dq2.log` was copied unchanged to
`analysis/out/dq-2026-07-02.log`. It reports 671,921,586 collected records,
zero duplicates, all gate checks passing, and agrees with the saved report's
trade count. Its historical PASS is not a newly executed PASS.

A fresh run of the existing `scripts/dq_check.py` was launched on September 8
against the historical database using `systemd-run --user --scope`,
`MemoryMax=24G`, `MemorySwapMax=0`, and detached `setsid nohup`, with unbuffered
logging. The repository's DuckDB memory and spill settings remain in effect.
The run finished with `DQ GATE: FAIL ['monthly_coverage']`: missing August and
September 2026. All seven other checks passed, including zero duplicate IDs,
99.997% category coverage, valid result domains, present event keys, and completed
streams. The full unchanged output is `analysis/out/dq-2026-09-08.log`. This is
a structural recheck of an archived snapshot, not a full fresh-data gate PASS.
No collection was started to fill those intentionally absent later months.

No report or statistical export was regenerated to make the website. The
publication compiler consumes the saved JSON and report artifacts.

An independent saved-artifact audit found consistent headline values and
intervals. The controller verified the material JSON fields and exporter code:
the existing export truncates fractional contract weights, while report tables
round them, causing a one-contract difference for post-period Crypto and Sports.
Display quantities are described as approximate rather than recovered decimals.
Education has a one-event pre-period headline with null CI and no post-period
headline; sparse curve bins must not be presented as a continuous set of measured
values. Category curves have no uncertainty bands; pooled curve bands use 400
replicates versus 1,000 for report/headline intervals.

## External documentation used

[Atlassian's static-hosting documentation](https://support.atlassian.com/bitbucket-cloud/docs/publishing-a-website-on-bitbucket-cloud/)
established the workspace-named hosting repository, main-branch publication,
JavaScript support, project subdirectories, and caching behavior. This informed
the portable directory layout and deployment instructions.

The official [setup-uv documentation](https://github.com/astral-sh/setup-uv)
established its pinned action revision and Python-version input; official
[setup-node documentation](https://github.com/actions/setup-node) established
the supported action version and explicit cache-disable input. These informed
the verification workflow. Hosted workflow execution itself requires a later
push and is not claimed here.

## Initial publication handoff — September 8

The existing research remote is GitHub. The Bitbucket workspace/repository and
site-root versus project-subdirectory choice were requested during implementation.
No Bitbucket deployment has occurred. The repository's explicit no-auto-commit
rule remains binding for local and hosting commits.

The branch-finishing phase preserved `feat/research-observatory` and its worktree,
including uncommitted sources, generated artifacts and the review ledger. There
was no staging, commit, merge, push, cleanup or database collection. The verified
ZIP can be copied to an identified hosting repository once the destination and
required commit authority are supplied. Suggested research commit message:
`feat: publish Almost Certain research exhibit`.

## GitHub release authorization — September 9

The owner explicitly authorized committing and pushing to
<https://github.com/dlustig/kalshi-flb>. GitHub's Pages API confirmed workflow
publication from `main` to <https://dlustig.github.io/kalshi-flb/>. The remote
`main` revision was still `b42053702e93817db357037abed5f0b0f9c84be5`, the reviewed
base; no remote work needed to be overwritten or rebased.

Fresh pre-commit verification passed: the canonical pytest console entry point
ran all 65 tests in 15.93 seconds; all nine Node behaviors, three JavaScript
syntax checks, the portable release build, and whitespace checks passed. No
project typecheck is configured. The original checkout's uncommitted files
remain preserved; publication is performed from the reviewed worktree.

The configured GitHub Actions runs provide the hosted verification and deployment
record: <https://github.com/dlustig/kalshi-flb/actions>. Local test success alone
does not assert that a hosted deployment completed.
