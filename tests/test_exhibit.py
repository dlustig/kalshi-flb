import hashlib
import json
import re
import stat
from pathlib import Path

import pytest

from scripts.build_exhibit import BuildError, build_exhibit


REQUIRED_MARKERS = (
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
)


def _write_fixture(repo: Path) -> None:
    (repo / "web" / "data").mkdir(parents=True)
    (repo / "analysis" / "out" / "plots").mkdir(parents=True)

    markers = "\n".join(f'<section data-name="{name}">{{{{{name}}}}}</section>' for name in REQUIRED_MARKERS)
    (repo / "web" / "exhibit.html").write_text(f"<!doctype html>\n{markers}\n", encoding="utf-8")
    (repo / "web" / "exhibit.css").write_text("body { color: #173f35; }\n", encoding="utf-8")
    for name in ("exhibit.mjs", "exhibit-charts.mjs", "exhibit-model.mjs"):
        (repo / "web" / name).write_text(f"// {name}\n", encoding="utf-8")

    stats = {
        "meta": {"n_trades": 1234.5, "publication_date": "2025-09-18"},
        "kpi": {
            "pre": {"net_c": None, "ci_lo": None, "ci_hi": None, "n": 10.5, "n_events": 2},
            "post": {"net_c": 1.25, "ci_lo": -0.5, "ci_hi": 2.75, "n": 20.25, "n_events": 3},
            "attenuation_pct": None,
        },
        "curves": {
            "post|all|All": [
                {"bucket": 90, "price_c": 92.5, "win_pct": 93.75, "net_c": 1.25, "n": 5.5},
                {"bucket": 95, "price_c": 97.25, "win_pct": None, "net_c": None, "n": 7.25},
            ]
        },
    }
    (repo / "web" / "data" / "stats.json").write_text(
        json.dumps(stats, separators=(",", ":")), encoding="utf-8"
    )
    snapshot = {
        "schema_version": 1,
        "snapshot_label": "Fixture snapshot",
        "aggregate_count": 45.25,
        "curve_bootstrap_replicates": 400,
        "headline_bootstrap_replicates": 1000,
        "data_quality": {
            "archived": {
                "status": "pass",
                "checked_at": "2026-07-02",
                "evidence_source": "analysis/out/dq-2026-07-02.log",
                "note": "Archived check; not rerun by this build.",
            },
            "fresh": {
                "status": "fail",
                "checked_at": "2026-09-08",
                "evidence_source": "analysis/out/dq-2026-09-08.log",
                "note": "Snapshot freshness failed: missing 2026-08 and 2026-09.",
            },
        },
    }
    (repo / "web" / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")

    (repo / "analysis" / "out" / "report.md").write_text(
        "# Report\n\n"
        "Generated 2026-07-03 03:31Z. Window: trades ≥ 2024-01-01; decay split at 2025-09-18.\n\n"
        "| trades | 1,234.5 |\n\n"
        "Trade span: 2024-01-01 00:00:00+00:00 → 2026-07-02 03:00:00+00:00. "
        "Aggregated panel: 45.25 event×bucket×segment cells.\n",
        encoding="utf-8",
    )
    (repo / "analysis" / "out" / "VERDICT.md").write_text("# VERDICT\n\n**GO**\n", encoding="utf-8")
    (repo / "analysis" / "out" / "dq-2026-07-02.log").write_text(
        "DATA QUALITY: PASS\nArchived 2026-07-02\n", encoding="utf-8"
    )
    (repo / "analysis" / "out" / "dq-2026-09-08.log").write_text(
        "FAIL  monthly_coverage: missing ['2026-08', '2026-09']\n"
        "DQ GATE: FAIL ['monthly_coverage']\n",
        encoding="utf-8",
    )
    (repo / "analysis" / "out" / "plots" / "calibration_pre_post.png").write_bytes(b"calibration-png")
    (repo / "analysis" / "out" / "plots" / "net_return_by_bucket.png").write_bytes(b"return-png")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_builds_portable_nested_bundle_without_database(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    out = repo / "publish" / "almost-certain"

    manifest = build_exhibit(repo, out, "https://example.test/research?a=1&b=2")

    html = (out / "index.html").read_text(encoding="utf-8")
    assert "1,234.5" in html
    assert "1.2K" in html
    assert "45.25" in html
    assert "Fixture snapshot" in html
    assert "2026-07-03 03:31Z" in html
    assert "2025-09-18" in html
    assert "+1.25" in html
    assert "https://example.test/research?a=1&amp;b=2" in html
    assert "Unavailable" in html
    assert "{{" not in html
    assert manifest["analysis"]["trade_timestamp_start"] == "2024-01-01 00:00:00+00:00"
    assert manifest["analysis"]["trade_timestamp_end"] == "2026-07-02 03:00:00+00:00"
    assert manifest["analysis"]["analysis_date"] == "2026-07-03"
    assert manifest["analysis"]["publication_date"] == "2025-09-18"
    assert manifest["analysis"]["curve_bootstrap_replicates"] == 400
    assert manifest["analysis"]["headline_bootstrap_replicates"] == 1000
    assert manifest["data_quality"]["archived"]["status"] == "pass"
    assert manifest["data_quality"]["fresh"]["status"] == "fail"
    assert not (repo / "data" / "kalshi.duckdb").exists()


def test_snapshot_changes_update_page_and_manifest_together(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    out = repo / "site"
    build_exhibit(repo, out, "https://example.test/research")

    snapshot_path = repo / "web" / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot.update(snapshot_label="Revised freeze", aggregate_count=12345.5)
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    manifest = build_exhibit(repo, out, "https://example.test/research")

    html = (out / "index.html").read_text(encoding="utf-8")
    assert "Revised freeze" in html
    assert "12.3K" in html
    assert manifest["snapshot"]["label"] == "Revised freeze"
    assert manifest["analysis"]["aggregate_count"] == 12345.5


def test_missing_values_render_unavailable_and_are_not_plotted_at_zero(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    out = repo / "site"

    build_exhibit(repo, out, "https://example.test/research")

    html = (out / "index.html").read_text(encoding="utf-8")
    lab_svg = (out / "figures" / "default-lab.svg").read_text(encoding="utf-8")
    table = html.split('data-name="default_lab_table">', 1)[1].split("</section>", 1)[0]
    assert html.count("Unavailable") >= 3
    assert "95–99¢" in table
    assert "Unavailable" in table
    assert 'data-bucket="95"' not in lab_svg
    assert ">0.00<" not in table


def test_inline_svg_accessible_ids_are_unique(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    out = repo / "site"

    build_exhibit(repo, out, "https://example.test/research")

    html = (out / "index.html").read_text(encoding="utf-8")
    ids = re.findall(r'<(?:title|desc) id="([^"]+)"', html)
    labelled_by = re.findall(r'aria-labelledby="([^"]+)"', html)
    assert len(ids) == 8
    assert len(ids) == len(set(ids))
    assert set(" ".join(labelled_by).split()) == set(ids)


def test_hero_uses_saved_post_calibration_and_highlights_90_cent_bucket(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    out = repo / "site"

    build_exhibit(repo, out, "https://example.test/research")

    hero = (out / "figures" / "hero.svg").read_text(encoding="utf-8")
    assert 'data-bucket="90"' in hero
    assert 'class="hero-point hero-point--highlight"' in hero
    assert "92.50¢ mean price" in hero
    assert "93.75% observed win rate" in hero
    assert "Synthetic" not in hero
    assert re.search(
        r'<text[^>]*class="hero-callout hero-callout--price"[^>]*>92\.50¢ price</text>', hero
    )
    assert re.search(
        r'<text[^>]*class="hero-callout hero-callout--outcome"[^>]*>93\.75% observed outcome rate</text>',
        hero,
    )


def test_standalone_svgs_include_their_own_presentation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    out = repo / "site"

    build_exhibit(repo, out, "https://example.test/research")

    expected_rules = {
        "hero.svg": ".hero-axis{",
        "pre-interval.svg": ".interval-ci{",
        "post-interval.svg": ".interval-ci{",
        "default-lab.svg": ".lab-point{",
    }
    for filename, rule in expected_rules.items():
        svg = (out / "figures" / filename).read_text(encoding="utf-8")
        assert "<style>" in svg
        assert rule in svg

    hero = (out / "figures" / "hero.svg").read_text(encoding="utf-8")
    assert hero.count('class="hero-grid"') == 6
    for value in range(0, 101, 20):
        assert f'>{value}</text>' in hero
        assert f'>{value}¢</text>' in hero


def test_written_publication_files_are_world_readable(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    out = repo / "site"

    manifest = build_exhibit(repo, out, "https://example.test/research")

    published = [out / relative for relative in manifest["outputs"]]
    published.append(out / "data" / "manifest.json")
    assert {stat.S_IMODE(path.stat().st_mode) for path in published} == {0o644}


def test_headline_value_outside_fixed_scale_fails_instead_of_clamping(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    stats_path = repo / "web" / "data" / "stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    stats["kpi"]["post"]["ci_hi"] = 4.01
    stats_path.write_text(json.dumps(stats), encoding="utf-8")
    out = repo / "site"

    with pytest.raises(BuildError, match="outside fixed headline scale"):
        build_exhibit(repo, out, "https://example.test/research")

    assert not (out / "index.html").exists()


def test_declared_dq_evidence_must_exist(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    (repo / "analysis" / "out" / "dq-2026-09-08.log").unlink()
    out = repo / "site"

    with pytest.raises(BuildError, match="fresh DQ evidence is missing"):
        build_exhibit(repo, out, "https://example.test/research")

    assert not (out / "index.html").exists()


def test_declared_dq_evidence_must_match_allowlisted_record(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    snapshot_path = repo / "web" / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["data_quality"]["fresh"]["evidence_source"] = "analysis/out/dq-2026-07-02.log"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    out = repo / "site"

    with pytest.raises(BuildError, match="fresh DQ evidence_source must be"):
        build_exhibit(repo, out, "https://example.test/research")

    assert not (out / "index.html").exists()


def test_copies_only_referenced_report_images_and_hashes_emitted_bytes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    unrelated = repo / "analysis" / "out" / "plots" / "net_edge_by_category.png"
    unrelated.write_bytes(b"unrelated")
    out = repo / "site"

    manifest = build_exhibit(repo, out, "https://example.test/research")

    assert (out / "evidence" / "plots" / "calibration_pre_post.png").read_bytes() == b"calibration-png"
    assert (out / "evidence" / "plots" / "net_return_by_bucket.png").read_bytes() == b"return-png"
    assert (out / "evidence" / "dq-2026-07-02.log").read_text(encoding="utf-8") == (
        "DATA QUALITY: PASS\nArchived 2026-07-02\n"
    )
    assert (out / "evidence" / "dq-2026-09-08.log").read_text(encoding="utf-8") == (
        "FAIL  monthly_coverage: missing ['2026-08', '2026-09']\n"
        "DQ GATE: FAIL ['monthly_coverage']\n"
    )
    assert not (out / "evidence" / "plots" / unrelated.name).exists()
    assert "analysis/out/dq-2026-07-02.log" in manifest["inputs"]
    assert "analysis/out/dq-2026-09-08.log" in manifest["inputs"]
    disk_manifest = json.loads((out / "data" / "manifest.json").read_text(encoding="utf-8"))
    assert disk_manifest == manifest
    for relative, metadata in manifest["outputs"].items():
        assert metadata["sha256"] == _sha256(out / relative)
        assert metadata["bytes"] == (out / relative).stat().st_size


def test_unknown_template_marker_fails_before_publishing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    template = repo / "web" / "exhibit.html"
    template.write_text(template.read_text(encoding="utf-8") + "{{surprise}}\n", encoding="utf-8")
    out = repo / "site"

    with pytest.raises(BuildError, match="unknown template marker.*surprise"):
        build_exhibit(repo, out, "https://example.test/research")

    assert not (out / "index.html").exists()


@pytest.mark.parametrize("source_url", ["javascript:alert(1)", "http://example.test/research", "https:///missing-host"])
def test_rejects_unsafe_or_malformed_source_url(tmp_path: Path, source_url: str) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)

    with pytest.raises(BuildError, match="source URL"):
        build_exhibit(repo, repo / "site", source_url)


def test_missing_template_is_a_clear_build_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_fixture(repo)
    (repo / "web" / "exhibit.html").unlink()

    with pytest.raises(BuildError, match="missing exhibit template"):
        build_exhibit(repo, repo / "site", "https://example.test/research")
