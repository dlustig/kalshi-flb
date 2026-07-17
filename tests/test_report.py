from kalshi_flb import report


def test_generate_on_fixture_db(panel_con, tmp_path):
    out = report.generate_from_con(panel_con, tmp_path / "out")
    rep = (out / "report.md").read_text()
    verdict = (out / "VERDICT.md").read_text()
    assert "markets_mve" in rep            # exclusion table present
    assert "Calibration" in rep
    assert ("**GO**" in verdict) ^ ("**NO-GO**" in verdict)
    for png in ("calibration_pre_post.png", "net_return_by_bucket.png"):
        f = out / "plots" / png
        assert f.exists() and f.stat().st_size > 1024
