import json

from kalshi_flb import cli


def test_status_json_on_empty_db(tmp_path, capsys):
    dbp = str(tmp_path / "t.duckdb")
    rc = cli.main(["status", "--db", dbp, "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["tables"] == {"series": 0, "events": 0, "markets": 0, "trades": 0}
