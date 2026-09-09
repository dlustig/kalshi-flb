# Almost Certain: a prediction-market research observatory

Concept and visual direction · 2026-09-08

Status: brainstorming document for review. This describes a proposed portfolio
exhibit; it does not authorize implementation, new research runs, or publication.

## 1. The idea

**Almost Certain** is an interactive essay about a small question that turned
into a large data experiment:

> When a prediction market is almost certain, how often is it right?

A visitor arrives at a carefully composed page, encounters a question they can
understand without knowing Kalshi, and follows the experiment from intuition to
evidence. A few deliberate interactions let them investigate the answer. Near
the end, the page opens up the machinery: hundreds of millions of trades,
collection failures, memory constraints, and statistical choices.

The project is a finished personal experiment published on Bitbucket. Its purpose
is to show curiosity, taste, technical depth, and the ability to finish a coherent
piece of work. There is no audience-growth objective, ongoing service obligation,
or need to persuade visitors to return. A dated research snapshot is the intended
form. “Observatory” describes the act of examining evidence, not a promise of live
monitoring.

The desired reaction is: “That was interesting. The person who built this thought
carefully about both the problem and how to explain it.”

### What a successful visit looks like

| Time available | What the visitor takes away |
|---|---|
| 20 seconds | The question, the scale, the visual character, and who made it |
| 2 minutes | What market calibration means, what changed across the research split, and why the answer needs qualification |
| 5–8 minutes | A few personally explored comparisons and an understanding of the main engineering decisions |
| A technical interview | A reproducible artifact and concrete tradeoffs to discuss |

These are editorial design targets, not analytics goals. The page should remain
worth reading if nobody ever measures a visit.

## 2. The design recommendation

Three visual concepts fit the subject:

| Direction | Appearance and character | Strength | Cost |
|---|---|---|---|
| **Illustrated field notebook — recommended** | Warm paper, dark ink, large editorial type, precise diagrams, restrained annotations | Makes a technical experiment approachable while retaining authorship and rigor | Requires strong composition and concise writing |
| Observatory after dark | Charcoal canvas, illuminated plots, instrument-like controls, fine coordinate lines | Dramatic screenshots and a strong sense of measurement | Can imply a live trading terminal and become visually dense |
| Financial broadsheet | Narrow columns, rules, compact tables, assertive headlines | Excellent information density and print output | Less playful; can feel like a publication or institutional report |

Use the field notebook as the overall design, with the broadsheet's clarity for
tables and the instrument concept's precision for charts. Keep one consistent
light theme in the first version. A second theme would add chart and contrast
work without improving the core story enough to justify it.

### Name and voice

Recommended public title: **Almost Certain**.

Subtitle: **A prediction-market experiment in 672 million trades.**

The scale in the subtitle must be derived from the selected publication snapshot;
672 million is the rounded value in the saved report, not a new count.

Other names considered: “The Price of Confidence” is evocative but less direct;
“Prediction Market Observatory” is descriptive but suggests an enduring service.
Use the latter as a project description in repository metadata if useful.

Write in a curious, candid first person where the author can confirm the wording.
Explain what was asked, what the data showed, and what made the work difficult.
Dry humor belongs in the engineering anecdotes, especially the documented machine
freeze. Avoid invented development timelines, conversations, or personal motives.

Sample opening copy, to refine during implementation:

> A contract priced at 90¢ looks like a 90% chance. I wanted to see how closely
> those prices matched what actually happened—and whether a published pattern
> still appeared afterward.

## 3. What it looks like

### The page as a visual object

Think of a well-designed science essay spread across a generous sheet of paper.
The main heading is large enough to be memorable. Charts receive the space normally
given to photography. Fine rules, figure numbers, and short notes establish a
research character. Sections alternate between reading and examining.

There is one major visual idea per section. Avoid repeating a grid of rounded
cards. Use a full-width figure, a narrow explanation beside a chart, a paired
comparison, then a quiet text passage. The changing composition gives the page
rhythm without requiring elaborate motion.

### Proposed visual vocabulary

| Element | Direction |
|---|---|
| Canvas | Warm ivory, starting point `#F5F2EA` |
| Main text | Near-black brown, `#202720` |
| Secondary text | Muted olive-gray, `#596155` |
| Main accent | Deep green, `#245B4A` |
| Comparison accent | Burnt orange, `#A94429` |
| Rules and grid | Pale neutral, `#D8D7CB` |
| Titles | An expressive editorial serif; Georgia is a viable starting point |
| Body and controls | A readable sans serif with a system-font fallback |
| Figure numbers and technical notes | Monospace used sparingly |
| Illustration | Purpose-built SVG: probability marks, brackets, axes, and data-flow drawings |
| Surfaces | Mostly flat; modest borders around actual controls and inset notes |

These colors are proposed tokens, not validated contrast results. Check final
combinations at actual text sizes. Direct labels, shapes, and line styles must
carry meaning independently of color.

Use color consistently within a figure. Green identifies the primary series;
orange identifies the comparison, not automatically loss or danger. Positive and
negative values are communicated by position relative to zero and explicit signs.

Desktop starting dimensions: a 1,200px outer page, a 650–700px reading column,
roughly 80–110px chapter spacing, and a 72–96px title. On phones: 20px page margins,
roughly 44–52px title, body text around 17px, and vertically stacked figures. All
dimensions should respond to content rather than force fixed-height panels.

### Desktop composition sketch

```text
 ALMOST CERTAIN                         The experiment  Explore  How it worked
 ────────────────────────────────────────────────────────────────────────────

 FIELD NOTES / PREDICTION MARKETS                 BY DAN LUSTIG

 When the market is                    ┌───────────────────────────────────┐
 almost certain,                       │          outcome rate             │
 is it right?                          │          · · ·   /                │
                                       │       · ·      /  reference       │
 A small question,                     │     ·        /                    │
 672 million trades.                   │   ·       /                       │
                                       │          market price →           │
 Read the experiment ↓                 └───────────────────────────────────┘
                                       FIG. 01  How closely price matched
 Snapshot: July 2026                             outcomes in the saved data

 ── 01 / THE QUESTION ───────────────────────────────────────────────────────
 Short explanation                     An annotated probability illustration

 ── 02 / THE EXPERIMENT ─────────────────────────────────────────────────────
 Publication marker                    BEFORE             AFTER
 What the comparison can tell us        estimate + interval on shared axis

 ── 03 / LOOK CLOSER ────────────────────────────────────────────────────────
 [What changed?] [Compare roles] [Compare categories]
 One large active figure + compact controls + evidence caption

 ── 04 / THE MACHINERY ──────────────────────────────────────────────────────
 Large numbers with named units         API → batches → aggregates → page
 Three short engineering stories, each attached to a concrete decision

 ── 05 / WHAT I WOULD INVESTIGATE NEXT ───────────────────────────────────────
 Limits of this experiment, original research rule, methods, reproducibility

 Dan Lustig                       Source on Bitbucket · Report · Chart data
```

This is a layout sketch, not a plot of the results. The actual hero should use
the saved pooled calibration curve with a clearly named period. It must remain a
readable figure at rest. Decorative points must never masquerade as observations.

On a phone, the opening becomes a single sequence: small masthead, large question,
two lines of context, then the figure and its caption. Keep the author and snapshot
date visible near the premise. Chapter navigation can wrap as ordinary links.
In the lab, put the question selector above the chart and the evidence caption
immediately below it. A reader should not have to scroll past unrelated controls
to see the result of a tap. The engineering drawings stack vertically and retain
their labels; they are recomposed rather than scaled-down desktop diagrams.

### Motion and delight

The main moment of delight is a chart changing in response to a good question.
Animate a switch between comparable series over roughly 180–250ms, preserving
axes so the change is interpretable. If a scale must change, make that explicit.

A fine annotation can appear when a datum receives focus. A selected price bucket
can connect the curve to a short sentence below it. A restrained figure-number
motif can recur in navigation and captions. These details provide character.

Use ordinary document scrolling. No scroll capture, mandatory animation sequence,
moving backgrounds, autoplay, or decorative particle systems. Respect reduced
motion and preserve the final information state when animations are disabled.

## 4. The story, scene by scene

### Opening: a question and a visual promise

The first screen contains the title, a two-sentence premise, an actual annotated
calibration figure, author attribution, and the snapshot date. “Read the
experiment” moves to the next section; “Explore the results” is a secondary text
link to the lab. A source link remains easy to find.

Avoid leading with a green GO badge. The original verdict is a specific research
rule; it needs context before it becomes meaningful. Also avoid four headline
metrics competing with the question. Scale gets one short, prominent sentence.

### Scene 1: what does 90¢ mean?

Explain a binary contract: it pays $1 if the specified outcome occurs and $0 if
it does not. Price can be read as an implied probability for this comparison;
fees and execution affect realized returns.

Use a static 100-mark illustration to explain a hypothetical 90% rate. Label it
“Illustration: 90 out of 100,” with no implication that it samples 100 real trades.
Then show how real price buckets compare with their eventual outcome rates.

Keep the first encounter small: one price bucket highlighted, one expected rate,
one observed rate, and one sentence explaining the gap. The full calibration
curve belongs beside or immediately below that explanation.

Do not equate contract-weighted outcomes with the fraction of distinct markets
that resolved yes. The underlying analysis weights by traded contract quantity.
The caption should say so in plain language.

### Scene 2: an experiment with a before and after

Introduce the research publication date, September 18, 2025, as the prespecified
split recorded in this repository. Use a simple timeline to orient the reader.

Introduce maker and taker here in one sentence: a maker posts an offer that waits
for a match; a taker accepts an available offer. A tiny two-party schematic can
help explain the roles, with the exact fee treatment left to the lab and methods.

Show the favorite-band maker result before and after on the same horizontal
interval plot. There are two dots and their uncertainty intervals, with a visible
zero reference. Avoid an animated dollar counter or a return-on-investment gauge.

Candidate copy grounded in the saved artifacts:

> The average estimated maker return was smaller in the later period. Its
> pooled uncertainty interval also included zero. Looking across categories
> made the picture more interesting.

The saved verdict reports +2.126¢ before and +0.809¢ after, with intervals of
[+0.403, +3.587] and [−0.028, +1.595] cents per contract, respectively.
Source: [VERDICT.md:7](../../../VERDICT.md).

The approximately 62% reduction compares point estimates. It does not establish
that publication caused the change, and it is not itself a statistically tested
change estimate. Put that distinction in the scene's caption, not only in the
methods appendix.

### Scene 3: the interesting part is in the differences

Move from the pooled estimate to a category interval plot. Begin with a curated,
named comparison: all categories pooled, Sports, and Crypto. Keep the full set
available in the lab, and explain that the curated examples illustrate different
sample sizes and uncertainty.

The saved report gives Sports +0.424¢ with an interval crossing zero; Crypto is
+1.311¢ with an interval above zero. Sports accounts for most of the pooled
post-period maker contract quantity. These are better teaching examples than a
ranking led by a category with only two events.
Source: [analysis/out/report.md:209](../../../analysis/out/report.md).

Say “uncertain positive estimate” where appropriate. A confidence interval
crossing zero does not prove there is no effect. A positive interval based on a
tiny number of events does not deserve an unqualified victory label either.

### Scene 4: take the controls

This is the interactive lab specified below. It is an optional deepening of the
story; the essay should already have delivered a coherent answer to a reader who
does not touch a control.

### Scene 5: how a small question became a systems problem

Open with a diagram and three distinct quantities: collected trade records,
potential two-sided observations before filtering, and materialized aggregate
rows. Explain how they differ. The report records 671,921,586 trades and
48,759,259 aggregate cells. Approximately 1.34 billion is the two-sided expansion
of the collected trade count, not a separately collected dataset or a verified
post-exclusion row count.
Source: [analysis/out/report.md:5](../../../analysis/out/report.md).

Tell three engineering stories in short paragraphs, each beside a diagram:

1. **One cursor was the bottleneck.** Show sequential page requests next to
   disjoint time-window shards sharing one rate limiter. Explain the difference
   between per-cursor latency and aggregate request pacing.
2. **The database outgrew the obvious design.** Explain vectorized insertion and
   the memory cost of indexing hundreds of millions of UUIDs. Include the
   resulting deduplication obligation as part of the tradeoff.
3. **The machine froze.** Describe the documented failure, then show the layers
   of resource protection and time-partitioned aggregation. The interesting
   outcome is the revised operating model and its limits.

These stories are documented in [DESIGN.md:117](../../../DESIGN.md), with
implementation in [collector.py:228](../../../src/kalshi_flb/collector.py),
[db.py:52](../../../src/kalshi_flb/db.py), and
[panel.py:112](../../../src/kalshi_flb/panel.py).

Use recorded history as history. Any published throughput, peak-memory, runtime,
or speedup benchmark needs retained measurement evidence and its environment.
Memory limits are configuration values, not measured memory consumption. A
pipeline animation is explicitly a schematic, not a playback of real telemetry.

### Ending: what the experiment taught me

Finish with a short conclusion and three concrete questions for a hypothetical
follow-up: historical fee reconstruction, category-composition changes across
time, and the gap between observed fills and achievable execution. These are
research questions, not a promised roadmap.

The original rule and its GO outcome remain available under “Original research
decision.” Explain that the rule required a qualifying liquid-category result,
which differs from requiring the pooled interval to exclude zero. Preserve the
original artifact rather than silently redefining the study to match new copy.

Close with the author's name, a concise contribution statement, and links to the
source, methods, report, and downloadable chart data. The work itself supplies
the portfolio argument; the public page does not need a “skills demonstrated” grid.

## 5. The interactive lab

### Recommended scope

Use one large figure area with three question presets. Each preset selects a
small, explicit view; there is no universal filter bar suggesting that every
dimension can be combined.

| Preset | Main figure | Supported controls | What it teaches |
|---|---|---|---|
| What changed? | Paired calibration curves | Category; show before, after, or both | Price-to-outcome calibration and differences between periods |
| Does the trading role matter? | Maker and taker net-return curves | Category; period | How observed role-specific returns differ under the fee model |
| Does the category matter? | Favorite-band maker interval plot | Period; highlighted category | Heterogeneity, sample size, and uncertainty |

Default to “What changed?”, all categories pooled, with both periods visible.
The role preset defaults to all categories pooled in the after period with both
roles shown. The category preset defaults to the after period, includes the
pooled reference, and orders categories alphabetically so changing estimates do
not move every row. It begins with no individual category highlighted. Reset
restores these defaults; curated story links can open a named selection explicitly.

The role comparison uses different observed trade sides and samples. Do not
animate one into the other as if changing fees alone explained the entire gap.

The calibration figure can retain the original full price range as descriptive
context. Net-return exploration defaults to favorites, consistent with the
project's scope. The headline band is [80¢, 97¢); the existing curves use 5¢ bins,
so the 95–99¢ point must not be relabeled as an exact 95–96¢ calculation. Label
curve bins literally and show the exact headline interval as a separate result.
No longshot-side strategy or optimization controls are proposed.

### Every view has an evidence caption

Keep a readable sentence immediately beneath the figure:

> Crypto · After publication · Maker · 80–97¢ favorite band
> Estimated net return: +1.31¢ per contract
> 95% event-bootstrap interval: +0.96¢ to +1.63¢ · 130,197 events

Numbers above are illustrative display formatting of the saved report, not a
second hand-maintained source of truth. Production captions must be generated
from the same snapshot as the chart.

Below the caption, “How this was calculated” expands a short note. “View values”
opens a table. A compact “Copy this view” action stores valid selection state in
the URL fragment and provides a selectable link if clipboard access fails.

Do not sum event counts across categories, price bins, or time-to-close groups
without establishing disjointness. One event can contribute to multiple groups.

### Interaction behavior

Selections update the figure, caption, units, and relevant counts together.
Global dataset facts remain separately labeled. Reset restores the preset's
documented default. Changing presets preserves category and period only where
both remain valid; any reset is reflected immediately in the controls.

Use native selects and buttons, visible focus, and comfortable touch targets.
Every hover annotation must have an equivalent focus or tap behavior. Never
require precise pointer positioning to read a value; the table is the universal
fallback. Announce a concise result summary after a control change rather than
every graphical update.

Category curves currently have point estimates but no per-bucket uncertainty
bands. Show “Interval not computed for this curve” where needed; do not borrow
the pooled interval. The maker category headline intervals are a separate,
available statistic. Sources:
[build_site_data.py:39](../../../scripts/build_site_data.py) and
[calibration.py:113](../../../src/kalshi_flb/calibration.py).

Missing data means “No estimate for this selection,” never zero. With fewer than
two events, show the point estimate if available and “Interval unavailable.”
Keep event counts visible for small groups and avoid a significance badge whose
authority exceeds the evidence.

### What stays outside the first lab

Arbitrary date ranges, a draggable publication split, custom favorite bands,
fee multipliers, monthly trends, and an “exclude Sports” pooled result all need
additional correctly generated statistics. They cannot be derived by averaging
the existing displayed category means or confidence endpoints.

The existing JSON does not provide arbitrary category × role × liquidity ×
time-to-close combinations. Use time-to-close as a fixed supporting figure if it
improves the essay. Omit the liquidity toggle from the main experience: the saved
post-period overall and top-tercile figures are identical, and final-volume
terciles are retrospective. Show that limitation in methods without presenting
the toggle as an interesting distinction.

## 6. Credibility is part of the design

The core editorial discipline is to keep the attractive claim next to the
information needed to interpret it.

| Tempting presentation | Recommended treatment |
|---|---|
| “The edge survives” as a universal result | Name the category, period, role, uncertainty, and original decision rule |
| “Publication erased 62% of the edge” | State the decline between point estimates; the comparison is observational |
| “Sports has no edge” | State that its saved interval crosses zero |
| “Billions of independent observations” | Distinguish trades, contract quantities, and event clusters |
| “What you would have earned” | Describe returns on observed fills under the model; execution was not established |
| A ranked winners table | Show effect sizes, intervals, and event counts without a winner badge |
| “Reproduce the exact result from today's API” | Distinguish the archived snapshot from a new collection using a changing API |

The methods section should explain event clustering, overlapping exclusions,
current rather than historical fee parameters, the approximate rounding boundary,
and final-volume liquidity grouping. The recorded fee-drift exposure is 35.23%
of panel contract quantity; this is useful context for the snapshot, not a newly
verified statistic. Source:
[analysis/out/report.md:272](../../../analysis/out/report.md).

The original category-based rule also deserves a clear multiple-comparisons
qualification. Prespecifying a rule does not automatically adjust uncertainty
for inspecting many categories. No new correction or reanalysis is specified
here; the public explanation should accurately describe what was done.

The reading path stays enjoyable by explaining each limitation where it matters,
with detailed derivations available below. Avoid a wall of generic disclaimers.

## 7. Build around a finished snapshot

### Existing foundation

The code graph located the aggregate/statistics/export path; direct source reads
confirmed the relevant behavior. The browser already consumes compact exported
JSON rather than the local DuckDB database. The existing exporter provides
period/category/role curves and maker headline slices:
[build_site_data.py:62](../../../scripts/build_site_data.py),
[build_site_data.py:135](../../../scripts/build_site_data.py), and
[calibration.py:24](../../../src/kalshi_flb/calibration.py).

Use that separation. Keep the Python analytical system and its statistical tests;
build the exhibit around versioned results. Rendering belongs in the page;
analytical calculations and bootstrap estimates belong in the offline pipeline.

```text
 Public API collection → local DuckDB → data-quality gate
                                           ↓
                              aggregate + statistical report
                                           ↓
                            small, versioned publication bundle
                                           ↓
                          static essay + interactive figures
                                           ↓
                                  Bitbucket static hosting
```

The quality-gate arrow is a requirement for new analytical publication, not a
claim that this document has rerun it. The saved artifacts were inspected as
design inputs only.

### What the publication bundle contains

Recommend one coherent release containing chart JSON, static figure fallbacks,
the report and its images, minimal chart-data downloads, and a small manifest.
The manifest records schema version, analysis generation time, data-window
boundaries with timezone, source revision, bootstrap settings, and artifact
checksums. It distinguishes the analysis date from a later website build date.

Document the existing difference between 400 bootstrap replicates for exported
pooled curve bands and 1,000 for headline/report estimates. If these are unified
later, regenerate through the statistical code and record the new configuration.

Never hand-edit generated JSON or reports. Missing-value handling and rounding
belong in their generators; the reviewed publication should not substitute zero
for unavailable estimates. Preserve fractional quantities in downloadable data,
even when a compact display rounds large totals.

A UI-only iteration should be able to reuse the frozen publication bundle. It
must not start a collection or rebuild aggregates just to change typography.
Any new heavy analysis follows the repository's cgroup, memory, disk, detached
execution, and DQ requirements. The site exporter also queries raw-trade metadata
in [build_site_data.py:116](../../../scripts/build_site_data.py); do not assume
that running it is a purely browser-sized operation.

### Reproduction at an appropriate scale

The first exhibit needs an easy local preview of the static page and access to
the existing analytical tests. A small synthetic end-to-end demonstration is a
valuable second increment if it can reuse the pipeline cleanly. Label it as a
mechanics demonstration; it cannot reproduce the empirical headline.

Publishing a compact snapshot reproduces the displayed results. Rebuilding
those results from raw observations requires the appropriate archived inputs
and environment. State the available level of reproduction precisely. Shipping
the approximately 72GB database is outside this exhibit's scope.

## 8. Bitbucket publication

Assumption: “a public page on Bitbucket” means Bitbucket Cloud static hosting.
Atlassian documents JavaScript support and a repository named
`<workspaceid>.bitbucket.io`, with a lowercase `index.html` at its root. A workspace
gets one site; project subdirectories can each contain an `index.html`. Content
comes from the selected main branch. Server-side execution is unsupported, and
pages may be cached for 15 minutes. The resulting site is public even when its
hosting repository is private. Atlassian also documents an injected analytics
script. Source, checked September 8, 2026:
[Publishing a Website on Bitbucket Cloud](https://support.atlassian.com/bitbucket-cloud/docs/publishing-a-website-on-bitbucket-cloud/).

Design decision: produce a portable folder that can sit at the site root or at
`/almost-certain/`. Use relative asset paths and document anchors/URL fragments;
do not require server route rewrites. Serve all project assets locally, including
fonts if custom fonts are chosen. Add no project analytics or external embeds.

The exact workspace and target folder are deployment inputs, not blockers to
this design. If a portfolio already occupies the site root, publish the exhibit
in a subdirectory and preserve its contents. The research repository and hosting
repository may be separate. Publish only the reviewed static bundle.

The existing GitHub Pages workflow is historical project infrastructure. A later
Bitbucket delivery change should be explicit and bounded; this document does not
remove it, move remotes, change repository visibility, or publish anything.

## 9. Technical shape and graceful behavior

Prefer semantic HTML, CSS, and small JavaScript modules using SVG figures. The
existing static approach is a suitable starting point. Choose a plotting helper
only if it demonstrably reduces the work of accessible charts; the visual design
does not require a framework migration. Generate repeated snapshot facts and
static fallbacks from data so prose and figures cannot silently drift.

The initial HTML should contain the essay and the headline figures or equivalent
static images and tables. JavaScript enhances the lab. A failed data fetch leaves
the essay readable, with a local error message, a retry action, and a report link.
Never leave the whole page on “Loading data.” An invalid shared selection resets
to a valid documented view and explains the reset briefly.

At narrow widths, stack explanation before figure, use horizontal category
labels, and allow the full chart to grow vertically. Do not shrink desktop axis
labels into illegibility. Detailed tables can scroll within their own region;
the entire page should not require horizontal scrolling.

Target roughly 1MB or less for the initial exhibit payload, with optional report
downloads outside that budget. This is a design budget to measure, not a current
performance claim. Prioritize stable layout, legible figures, and prompt local
control changes. There is no benefit to simulated network latency or loading
animations for calculations already computed offline.

Provide a print stylesheet that keeps captions, source notes, and the active
figure understandable. A resume link preview should use a real plot and the
project title in a composed static image, generated after the visual design is
settled. Neither bitmap illustration nor a logo commission is needed to make the
first version distinctive.

## 10. Scope, priorities, and tempting extensions

### The complete first exhibit

Build the illustrated essay, the three-preset lab using supported statistics,
the engineering section, methods/source links, and the Bitbucket-ready static
bundle. Include mobile, keyboard, reduced-motion, error, and print behavior.
This is already a complete portfolio project.

The strongest investment order is: clarify the story and claims, establish the
visual composition, finish the figures and interactions, then package the evidence
and publication. This is a prioritization recommendation, not an implementation
task plan.

### Worth considering after the core works

| Idea | Why it could be memorable | Recommendation |
|---|---|---|
| A synthetic event-clustering illustration | Shows why many contracts do not equal many independent outcomes | Best optional teaching addition; label every synthetic element |
| A small reproducible pipeline demo | Makes the engineering accessible without a huge download | Add if it reuses existing behavior cleanly |
| A measured ingestion/aggregation case study | Adds concrete evidence to the resource-constraint story | Add only with retained measurements and a bounded run |
| Reader guesses an outcome rate before revealing the estimate | Adds a playful moment of participation | Optional polish; never delay access to the actual figure |
| Before/after category composition | Could explain how the pooled result changes | Separate analytical extension requiring suitable data and careful weighting |
| Historical fee reconstruction | Resolves a real methodological limitation | Separate research project, not a prerequisite for honestly presenting this snapshot |

The first three are ranked by teaching and portfolio value, not a promise to
implement all of them. Resist turning a finished experiment into a permanent
platform simply because the data could support more questions.

Exclude accounts, subscriptions, alerts, leaderboards, live prices, trade
recommendations, order placement, authenticated market endpoints, strategy
optimization, comments, and an AI chat interface. There is no product demand
for these in the stated goal, and trading/authenticated collection would cross
the repository's binding scope.

## 11. What “finished” means

The exhibit is ready when someone can open its public URL and understand the
question without using any controls; change a lab selection and understand
exactly what changed; inspect uncertainty and sample size; and follow a figure
back to a dated artifact and its method.

Visual review should cover a wide desktop and a narrow phone, keyboard-only
navigation, reduced motion, printing, and failed interactive-data loading. The
opening, one lab state, and the engineering section should each make an attractive
standalone screenshot. Charts must remain useful without hover or animation.

Publication checks should compare displayed values against the selected bundle,
verify all supported selection states and URL restoration, and confirm asset
paths work under the chosen Bitbucket subdirectory. New statistical behavior
requires affected analytical tests and the DQ process; a visual restyle does not
justify rerunning the full raw dataset. Follow the repository's no-auto-commit
rule and run required checks before any proposed commit.

The lasting artifact should communicate a clear question, an honest result, a
small enjoyable interaction, and engineering decisions the author can explain
in detail. Its completeness and coherence are the showcase.

## 12. Review notes and evidence boundaries

This concept incorporates the user's direction: a fun example project, a public
Bitbucket page, and no objective to acquire users. It replaces the earlier notion
of an ongoing public research product with a deliberately finite exhibit.

Repository evidence was reviewed directly: the current dashboard and exporter,
statistical aggregation functions, committed report and verdict, design decision
log, and recent Git history. The session-local code graph helped locate source
relationships; direct reads established the cited behavior. No fresh database
count, DQ run, benchmark, API probe, or statistical replication was performed.

The brainstorming skill informed the comparison of visual approaches, explicit
recommendation, detailed visitor experience, and separation of the exhibit from
optional research extensions. The document is the requested design artifact;
implementation planning can follow its review in a separate task.
