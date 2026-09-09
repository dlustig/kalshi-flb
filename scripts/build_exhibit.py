#!/usr/bin/env python3
"""Build the portable, frozen Almost Certain research exhibit."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, overload
from urllib.parse import SplitResult, urlsplit, urlunsplit


class BuildError(RuntimeError):
    """Raised when publication inputs are incomplete or inconsistent."""


REQUIRED_MARKERS = frozenset(
    {
        "hero_svg",
        "pre_interval_svg",
        "post_interval_svg",
        "default_lab_svg",
        "default_lab_table",
        "trade_count",
        "trade_count_short",
        "aggregate_count_short",
        "snapshot_label",
        "analysis_generated",
        "publication_date",
        "pre_net",
        "post_net",
        "attenuation",
        "source_url",
        "methodology_url",
    }
)
TRUSTED_MARKUP = frozenset(
    {"hero_svg", "pre_interval_svg", "post_interval_svg", "default_lab_svg", "default_lab_table"}
)
SOURCE_ASSETS = (
    "web/exhibit.css",
    "web/exhibit.mjs",
    "web/exhibit-charts.mjs",
    "web/exhibit-model.mjs",
    "web/data/stats.json",
    "web/snapshot.json",
)
REPORT_ARTIFACTS = (
    "analysis/out/report.md",
    "analysis/out/VERDICT.md",
    "analysis/out/plots/calibration_pre_post.png",
    "analysis/out/plots/net_return_by_bucket.png",
)
HEADLINE_SCALE = (-1.0, 4.0)
BASE_SVG_STYLE = (
    "text{font-family:Arial,Helvetica,sans-serif;font-size:11px;fill:#253b30}"
    "line{vector-effect:non-scaling-stroke}"
)


def display_number(value: int | float | None, *, places: int = 2) -> str:
    return "Unavailable" if value is None else f"{value:+.{places}f}"


def render_template(template: str, values: dict[str, str]) -> str:
    marker_re = re.compile(r"\{\{([a-z_]+)\}\}")
    present = set(marker_re.findall(template))
    unknown = present - values.keys()
    if unknown:
        raise BuildError(f"unknown template marker(s): {', '.join(sorted(unknown))}")
    missing = REQUIRED_MARKERS - present
    if missing:
        raise BuildError(f"missing required template marker(s): {', '.join(sorted(missing))}")
    malformed = re.findall(r"\{\{([^{}]+)\}\}", template)
    malformed = sorted(set(malformed) - present)
    if malformed:
        raise BuildError(f"invalid template marker(s): {', '.join(malformed)}")
    rendered = marker_re.sub(lambda match: values[match[1]], template)
    if "{{" in rendered or "}}" in rendered:
        raise BuildError("unresolved template marker")
    return rendered


def _read(path: Path, *, label: str | None = None) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise BuildError(label or f"missing required input: {path}") from exc


def _decode_json(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"invalid JSON input: {path}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"JSON input must be an object: {path}")
    return value


def _required(mapping: dict[str, Any], key: str, context: str) -> Any:
    if key not in mapping:
        raise BuildError(f"missing {context}.{key}")
    return mapping[key]


@overload
def _number(value: Any, context: str, *, nullable: Literal[False] = False) -> int | float: ...


@overload
def _number(value: Any, context: str, *, nullable: bool) -> int | float | None: ...


def _number(value: Any, context: str, *, nullable: bool = False) -> int | float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BuildError(f"{context} must be numeric{' or null' if nullable else ''}")
    return value


def _format_count(value: int | float) -> str:
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.3f}".rstrip("0").rstrip(".")


def _short_count(value: int | float) -> str:
    magnitude = abs(value)
    for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if magnitude >= divisor:
            scaled = value / divisor
            places = 1 if abs(scaled) < 100 else 0
            return f"{scaled:.{places}f}{suffix}"
    return _format_count(value)


def _validate_url(source_url: str) -> SplitResult:
    try:
        parsed = urlsplit(source_url)
        _ = parsed.port
    except ValueError as exc:
        raise BuildError("source URL is malformed") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise BuildError("source URL must be an absolute HTTPS URL without credentials")
    return parsed


def _source_revision(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and re.fullmatch(r"[0-9a-fA-F]{40,64}", revision) else None


def _methodology_url(parsed: SplitResult, revision: str | None) -> str:
    ref = revision or "main"
    base_path = parsed.path.rstrip("/")
    host = (parsed.hostname or "").lower()
    if host == "github.com" or host.endswith(".github.com"):
        path = f"{base_path}/blob/{ref}/DESIGN.md"
    elif host == "bitbucket.org" or host.endswith(".bitbucket.org"):
        path = f"{base_path}/src/{ref}/DESIGN.md"
    else:
        path = f"{base_path}/DESIGN.md"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _parse_report_metadata(report: str) -> dict[str, str]:
    generated = re.search(r"^Generated (.+?)\. Window: trades ≥ (.+?);", report, re.MULTILINE)
    span = re.search(r"^Trade span: (.+?) → (.+?)\. Aggregated panel:", report, re.MULTILINE)
    if not generated or not span:
        raise BuildError("report is missing generated/window/trade-span metadata")
    analysis_date = re.match(r"\d{4}-\d{2}-\d{2}", generated.group(1))
    if not analysis_date:
        raise BuildError("report generated timestamp does not begin with an ISO date")
    return {
        "analysis_date": analysis_date.group(0),
        "generated_at": generated.group(1),
        "window_start": generated.group(2),
        "trade_timestamp_start": span.group(1),
        "trade_timestamp_end": span.group(2),
    }


def _svg_document(
    identifier: str,
    title: str,
    description: str,
    body: str,
    *,
    view_box: str,
    style: str,
) -> str:
    title_escaped = html.escape(title)
    description_escaped = html.escape(description)
    title_id = f"{identifier}-title"
    description_id = f"{identifier}-description"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" role="img" '
        f'aria-labelledby="{title_id} {description_id}">'
        f'<title id="{title_id}">{title_escaped}</title>'
        f'<desc id="{description_id}">{description_escaped}</desc>'
        f"<style>{BASE_SVG_STYLE}{style}</style>{body}</svg>"
    )


def _render_hero(rows: list[dict[str, Any]]) -> str:
    points: list[tuple[float, float, int | float, int | float, int | float]] = []
    highlighted: tuple[int | float, int | float] | None = None
    for index, row in enumerate(rows):
        bucket = _number(_required(row, "bucket", f"curve[{index}]"), f"curve[{index}].bucket")
        price = _number(_required(row, "price_c", f"curve[{index}]"), f"curve[{index}].price_c", nullable=True)
        win = _number(_required(row, "win_pct", f"curve[{index}]"), f"curve[{index}].win_pct", nullable=True)
        if price is None or win is None:
            continue
        points.append((54 + price * 5.1, 326 - win * 2.82, bucket, price, win))
        if bucket == 90:
            highlighted = (price, win)
    if highlighted is None:
        raise BuildError("post|all|All calibration is missing the 90–94¢ hero bucket")
    price, win = highlighted
    grid = "".join(
        f'<line class="hero-grid" x1="54" y1="{326 - value * 2.82:.1f}" '
        f'x2="564" y2="{326 - value * 2.82:.1f}"/>'
        f'<text class="hero-tick" x="44" y="{330 - value * 2.82:.1f}" '
        f'text-anchor="end">{value}</text>'
        f'<text class="hero-tick" x="{54 + value * 5.1:.1f}" y="350" '
        f'text-anchor="middle">{value}¢</text>'
        for value in range(0, 101, 20)
    )
    axes = (
        '<line class="hero-axis" x1="54" y1="326" x2="564" y2="326"/>'
        '<line class="hero-axis" x1="54" y1="326" x2="54" y2="44"/>'
        '<line class="hero-reference" x1="54" y1="326" x2="564" y2="44"/>'
        '<text x="309" y="382" text-anchor="middle">Mean contract price (¢)</text>'
        '<text x="18" y="185" text-anchor="middle" transform="rotate(-90 18 185)">Observed win rate (%)</text>'
    )
    line = '<polyline class="hero-line" fill="none" points="' + " ".join(
        f"{x:.1f},{y:.1f}" for x, y, _, _, _ in points
    ) + '"/>'
    dots = []
    for x, y, bucket, _, _ in points:
        point_class = "hero-point hero-point--highlight" if bucket == 90 else "hero-point"
        radius = 8 if bucket == 90 else 4
        dots.append(
            f'<circle class="{point_class}" data-bucket="{bucket:g}" '
            f'cx="{x:.1f}" cy="{y:.1f}" r="{radius}"/>'
        )
    description = (
        "Post-publication pooled calibration by full five-cent price bucket. "
        f"The highlighted 90–94 cent bucket has {price:.2f}¢ mean price and "
        f"{win:.2f}% observed win rate."
    )
    highlighted_x, highlighted_y = next(
        (x, y) for x, y, bucket, _, _ in points if bucket == 90
    )
    callout = (
        f'<line class="hero-callout-line" x1="{highlighted_x:.1f}" y1="{highlighted_y:.1f}" '
        'x2="238" y2="105"/>'
        f'<text class="hero-callout hero-callout--price" x="92" y="78">{price:.2f}¢ price</text>'
        f'<text class="hero-callout hero-callout--outcome" x="92" y="103">'
        f'{win:.2f}% observed outcome rate</text>'
    )
    return _svg_document(
        "hero",
        "Post-publication pooled calibration",
        description,
        grid + axes + line + "".join(dots) + callout,
        view_box="0 0 620 400",
        style=(
            ".hero-grid{stroke:#cbd0bf;stroke-width:1}"
            ".hero-axis{stroke:#657064;stroke-width:1}"
            ".hero-reference{stroke:#a8b4a1;stroke-width:1;stroke-dasharray:5 5}"
            ".hero-line{stroke:#2e6652;stroke-width:3}"
            ".hero-point{fill:#2e6652;stroke:#f5f2e9;stroke-width:1.5}"
            ".hero-point--highlight{fill:#ac5035;stroke:#ac5035}"
            ".hero-callout-line{stroke:#ac5035;stroke-width:1}"
            ".hero-callout--price{font-family:Georgia,'Times New Roman',serif;font-size:24px}"
            ".hero-callout--outcome{fill:#ac5035;font-size:12px}"
        ),
    )


def _render_interval(period: str, values: dict[str, Any]) -> str:
    estimate = _number(_required(values, "net_c", f"kpi.{period}"), f"kpi.{period}.net_c", nullable=True)
    low = _number(_required(values, "ci_lo", f"kpi.{period}"), f"kpi.{period}.ci_lo", nullable=True)
    high = _number(_required(values, "ci_hi", f"kpi.{period}"), f"kpi.{period}.ci_hi", nullable=True)
    scale_low, scale_high = HEADLINE_SCALE
    for value in (estimate, low, high):
        if value is not None and not scale_low <= value <= scale_high:
            raise BuildError(
                f"kpi.{period} value {value:g} is outside fixed headline scale "
                f"[{scale_low:g}, {scale_high:g}]"
            )

    def x(value: int | float) -> float:
        return 50 + (value - scale_low) / (scale_high - scale_low) * 500

    axis = (
        f'<line class="interval-axis" x1="50" y1="75" x2="550" y2="75"/>'
        f'<line class="interval-zero" x1="{x(0):.1f}" y1="38" x2="{x(0):.1f}" y2="100"/>'
        f'<text x="50" y="120">{scale_low:+g}¢</text><text x="550" y="120" text-anchor="end">{scale_high:+g}¢</text>'
    )
    if estimate is None or low is None or high is None:
        marks = '<text class="interval-unavailable" x="300" y="68" text-anchor="middle">Unavailable</text>'
        description = f"{period.title()} headline interval is unavailable. Shared scale {scale_low:g} to {scale_high:g} cents."
    else:
        marks = (
            f'<line class="interval-ci" x1="{x(low):.1f}" y1="68" x2="{x(high):.1f}" y2="68"/>'
            f'<circle class="interval-estimate" cx="{x(estimate):.1f}" cy="68" r="7"/>'
            f'<text class="interval-value" x="{x(estimate):.1f}" y="28" text-anchor="middle">'
            f'{html.escape(display_number(estimate))}¢</text>'
        )
        description = (
            f"{period.title()} maker net estimate {estimate:+.2f} cents, 95 percent interval "
            f"{low:+.2f} to {high:+.2f}, on a shared {scale_low:g} to {scale_high:g} cent scale."
        )
    return _svg_document(
        f"{period}-interval",
        f"{period.title()}-publication maker net interval",
        description,
        axis + marks,
        view_box="0 0 600 140",
        style=(
            ".interval-axis{stroke:#657064;stroke-width:1}"
            ".interval-zero{stroke:#98a38e;stroke-width:1;stroke-dasharray:3 3}"
            ".interval-ci{stroke:#2e6652;stroke-width:3}"
            ".interval-estimate{fill:#ac5035}"
            ".interval-value{font-family:Georgia,'Times New Roman',serif;font-size:18px}"
            ".interval-unavailable{fill:#657064;font-style:italic}"
        ),
    )


def _curve_rows(stats: dict[str, Any]) -> list[dict[str, Any]]:
    curves = _required(stats, "curves", "stats")
    if not isinstance(curves, dict):
        raise BuildError("stats.curves must be an object")
    rows = curves.get("post|all|All")
    if not isinstance(rows, list) or not rows:
        raise BuildError("stats.curves must contain non-empty post|all|All data")
    return rows


def _render_default_lab(rows: list[dict[str, Any]]) -> str:
    points: list[tuple[float, float, int | float]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise BuildError(f"stats.curves.post|all|All[{index}] must be an object")
        bucket = _number(_required(row, "bucket", f"curve[{index}]"), f"curve[{index}].bucket")
        price = _number(_required(row, "price_c", f"curve[{index}]"), f"curve[{index}].price_c", nullable=True)
        win = _number(_required(row, "win_pct", f"curve[{index}]"), f"curve[{index}].win_pct", nullable=True)
        if price is not None and win is not None:
            points.append((50 + price * 5, 320 - win * 2.8, bucket))
    diagonal = '<line class="lab-reference" x1="50" y1="320" x2="550" y2="40"/>'
    axes = (
        '<line class="lab-axis" x1="50" y1="320" x2="550" y2="320"/>'
        '<line class="lab-axis" x1="50" y1="320" x2="50" y2="40"/>'
        '<text x="300" y="355" text-anchor="middle">Mean contract price (¢)</text>'
        '<text x="18" y="180" text-anchor="middle" transform="rotate(-90 18 180)">Observed win rate (%)</text>'
    )
    polyline = ""
    if points:
        polyline = '<polyline class="lab-line" fill="none" points="' + " ".join(
            f"{x:.1f},{y:.1f}" for x, y, _ in points
        ) + '"/>'
    dots = "".join(
        f'<circle class="lab-point" data-bucket="{bucket:g}" cx="{x:.1f}" cy="{y:.1f}" r="5"/>'
        for x, y, bucket in points
    )
    return _svg_document(
        "default-lab",
        "Post-publication pooled calibration",
        "Observed win rate against mean contract price by full five-cent bucket; missing observations are omitted.",
        axes + diagonal + polyline + dots,
        view_box="0 0 600 380",
        style=(
            ".lab-axis{stroke:#657064;stroke-width:1}"
            ".lab-reference{stroke:#a8b4a1;stroke-width:1;stroke-dasharray:5 5}"
            ".lab-line{stroke:#2e6652;stroke-width:3}"
            ".lab-point{fill:#2e6652;stroke:#f5f2e9;stroke-width:1.5}"
        ),
    )


def _display_plain(value: Any, *, places: int = 2, suffix: str = "") -> str:
    numeric = _number(value, "curve value", nullable=True)
    if numeric is None:
        return "Unavailable"
    return f"{numeric:.{places}f}{suffix}"


def _render_default_lab_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for index, row in enumerate(rows):
        bucket = _number(_required(row, "bucket", f"curve[{index}]"), f"curve[{index}].bucket")
        upper = min(int(bucket) + 4, 99)
        count = _number(_required(row, "n", f"curve[{index}]"), f"curve[{index}].n", nullable=True)
        count_display = "Unavailable" if count is None else _format_count(count)
        body.append(
            "<tr>"
            f"<th scope=\"row\">{bucket:g}–{upper}¢</th>"
            f"<td>{_display_plain(_required(row, 'price_c', f'curve[{index}]'))}</td>"
            f"<td>{_display_plain(_required(row, 'win_pct', f'curve[{index}]'))}</td>"
            f"<td>{display_number(_number(_required(row, 'net_c', f'curve[{index}]'), 'curve net', nullable=True))}</td>"
            f"<td>{count_display}</td>"
            "</tr>"
        )
    return (
        '<table class="data-table"><caption>Post-publication pooled calibration values</caption>'
        '<thead><tr><th scope="col">Price bucket</th><th scope="col">Mean price (¢)</th>'
        '<th scope="col">Win rate (%)</th><th scope="col">Net (¢)</th><th scope="col">Contracts</th>'
        f"</tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _hash_metadata(raw: bytes) -> dict[str, int | str]:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def _validate_dq_evidence(
    inputs: dict[str, bytes], archived: dict[str, Any], fresh: dict[str, Any]
) -> None:
    expected_sources = {
        "archived": "analysis/out/dq-2026-07-02.log",
        "fresh": "analysis/out/dq-2026-09-08.log",
    }
    for label, record in (("archived", archived), ("fresh", fresh)):
        source = record.get("evidence_source")
        expected = expected_sources[label]
        if source is None:
            if record.get("status") not in {"not_run", "pending"}:
                raise BuildError(
                    f"{label} DQ evidence_source is required for status {record.get('status')}"
                )
            continue
        if source != expected:
            raise BuildError(f"{label} DQ evidence_source must be {expected}")
        if source not in inputs:
            raise BuildError(f"{label} DQ evidence is missing: {source}")


def build_exhibit(repo_root: Path, out_dir: Path, source_url: str) -> dict[str, Any]:
    """Compile source assets and frozen evidence into a portable static bundle."""
    repo_root = Path(repo_root).resolve()
    out_dir = Path(out_dir).resolve()
    parsed_url = _validate_url(source_url)

    template_path = repo_root / "web" / "exhibit.html"
    template_raw = _read(template_path, label=f"missing exhibit template: {template_path}")
    input_paths = [repo_root / relative for relative in (*SOURCE_ASSETS, *REPORT_ARTIFACTS)]
    inputs: dict[str, bytes] = {"web/exhibit.html": template_raw}
    for path in input_paths:
        relative = path.relative_to(repo_root).as_posix()
        inputs[relative] = _read(path)
    builder_path = repo_root / "scripts" / "build_exhibit.py"
    if builder_path.is_file():
        inputs["scripts/build_exhibit.py"] = builder_path.read_bytes()
    for relative in (
        "analysis/out/dq-2026-07-02.log",
        "analysis/out/dq-2026-09-08.log",
    ):
        dq_path = repo_root / relative
        if dq_path.is_file():
            inputs[relative] = dq_path.read_bytes()

    try:
        template = template_raw.decode("utf-8")
        report = inputs["analysis/out/report.md"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError("template and report inputs must be UTF-8") from exc
    stats = _decode_json(inputs["web/data/stats.json"], repo_root / "web/data/stats.json")
    snapshot = _decode_json(inputs["web/snapshot.json"], repo_root / "web/snapshot.json")
    report_metadata = _parse_report_metadata(report)

    stats_meta = _required(stats, "meta", "stats")
    kpi = _required(stats, "kpi", "stats")
    if not isinstance(stats_meta, dict) or not isinstance(kpi, dict):
        raise BuildError("stats.meta and stats.kpi must be objects")
    pre = _required(kpi, "pre", "stats.kpi")
    post = _required(kpi, "post", "stats.kpi")
    if not isinstance(pre, dict) or not isinstance(post, dict):
        raise BuildError("stats.kpi.pre and stats.kpi.post must be objects")

    trade_count = _number(_required(stats_meta, "n_trades", "stats.meta"), "stats.meta.n_trades")
    aggregate_count = _number(_required(snapshot, "aggregate_count", "snapshot"), "snapshot.aggregate_count")
    rows = _curve_rows(stats)
    publication_date = _required(stats_meta, "publication_date", "stats.meta")
    if not isinstance(publication_date, str):
        raise BuildError("stats.meta.publication_date must be text")
    revision = _source_revision(repo_root)
    methodology_url = _methodology_url(parsed_url, revision)
    svg_values = {
        "hero_svg": _render_hero(rows),
        "pre_interval_svg": _render_interval("pre", pre),
        "post_interval_svg": _render_interval("post", post),
        "default_lab_svg": _render_default_lab(rows),
        "default_lab_table": _render_default_lab_table(rows),
    }
    attenuation_value = _number(
        _required(kpi, "attenuation_pct", "stats.kpi"), "stats.kpi.attenuation_pct", nullable=True
    )
    prose_values: dict[str, Any] = {
        "trade_count": _format_count(trade_count),
        "trade_count_short": _short_count(trade_count),
        "aggregate_count_short": _short_count(aggregate_count),
        "snapshot_label": _required(snapshot, "snapshot_label", "snapshot"),
        "analysis_generated": report_metadata["generated_at"],
        "publication_date": publication_date,
        "pre_net": display_number(_number(_required(pre, "net_c", "stats.kpi.pre"), "pre net", nullable=True)),
        "post_net": display_number(_number(_required(post, "net_c", "stats.kpi.post"), "post net", nullable=True)),
        "attenuation": "Unavailable" if attenuation_value is None else f"{attenuation_value:.1f}%",
        "source_url": source_url,
        "methodology_url": methodology_url,
    }
    for key, value in prose_values.items():
        if not isinstance(value, str):
            raise BuildError(f"template value {key} must be text")
    raw_values = {**prose_values, **svg_values}
    template_values = {
        key: value if key in TRUSTED_MARKUP else html.escape(value, quote=True)
        for key, value in raw_values.items()
    }
    if set(template_values) != REQUIRED_MARKERS:
        raise BuildError("internal template mapping does not match required markers")
    index_raw = render_template(template, template_values).encode("utf-8")

    output_bytes: dict[str, bytes] = {
        "index.html": index_raw,
        "exhibit.css": inputs["web/exhibit.css"],
        "exhibit.mjs": inputs["web/exhibit.mjs"],
        "exhibit-charts.mjs": inputs["web/exhibit-charts.mjs"],
        "exhibit-model.mjs": inputs["web/exhibit-model.mjs"],
        "snapshot.json": inputs["web/snapshot.json"],
        "data/stats.json": inputs["web/data/stats.json"],
        "figures/hero.svg": svg_values["hero_svg"].encode("utf-8"),
        "figures/pre-interval.svg": svg_values["pre_interval_svg"].encode("utf-8"),
        "figures/post-interval.svg": svg_values["post_interval_svg"].encode("utf-8"),
        "figures/default-lab.svg": svg_values["default_lab_svg"].encode("utf-8"),
        "evidence/report.md": inputs["analysis/out/report.md"],
        "evidence/VERDICT.md": inputs["analysis/out/VERDICT.md"],
        "evidence/plots/calibration_pre_post.png": inputs[
            "analysis/out/plots/calibration_pre_post.png"
        ],
        "evidence/plots/net_return_by_bucket.png": inputs[
            "analysis/out/plots/net_return_by_bucket.png"
        ],
    }
    if "analysis/out/dq-2026-07-02.log" in inputs:
        output_bytes["evidence/dq-2026-07-02.log"] = inputs[
            "analysis/out/dq-2026-07-02.log"
        ]
    if "analysis/out/dq-2026-09-08.log" in inputs:
        output_bytes["evidence/dq-2026-09-08.log"] = inputs[
            "analysis/out/dq-2026-09-08.log"
        ]

    data_quality = _required(snapshot, "data_quality", "snapshot")
    if not isinstance(data_quality, dict):
        raise BuildError("snapshot.data_quality must be an object")
    archived = _required(data_quality, "archived", "snapshot.data_quality")
    fresh = _required(data_quality, "fresh", "snapshot.data_quality")
    if not isinstance(archived, dict) or not isinstance(fresh, dict):
        raise BuildError("snapshot data-quality records must be objects")
    _validate_dq_evidence(inputs, archived, fresh)
    manifest: dict[str, Any] = {
        "schema_version": _required(snapshot, "schema_version", "snapshot"),
        "source": {"url": source_url, "revision": revision},
        "snapshot": {
            "label": _required(snapshot, "snapshot_label", "snapshot"),
        },
        "analysis": {
            **report_metadata,
            "trade_count": trade_count,
            "aggregate_count": aggregate_count,
            "publication_date": publication_date,
            "curve_bootstrap_replicates": _required(
                snapshot, "curve_bootstrap_replicates", "snapshot"
            ),
            "headline_bootstrap_replicates": _required(
                snapshot, "headline_bootstrap_replicates", "snapshot"
            ),
        },
        "build": {"generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")},
        "data_quality": {"archived": archived, "fresh": fresh},
        "inputs": {relative: _hash_metadata(raw) for relative, raw in sorted(inputs.items())},
        "outputs": {relative: _hash_metadata(raw) for relative, raw in sorted(output_bytes.items())},
    }
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")

    for relative, raw in output_bytes.items():
        _atomic_write(out_dir / relative, raw)
    _atomic_write(out_dir / "data" / "manifest.json", manifest_raw)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("web"), help="output directory (default: web)")
    parser.add_argument(
        "--source-url",
        default="https://github.com/dlustig/kalshi-flb",
        help="public HTTPS repository URL",
    )
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    manifest = build_exhibit(repo_root, args.out, args.source_url)
    print(f"Built {args.out} from {manifest['source']['revision'] or 'unversioned source'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
