import csv

from app.services import report


def test_save_appends_rows(tmp_path, monkeypatch):
    path = tmp_path / "reports.csv"
    monkeypatch.setattr(report, "_CSV_PATH", str(path))

    report.save("U1", {"category": "ไฟฟ้าสาธารณะ", "notes": "ถนนมืด", "location": "ซอย 5", "severity": "อันตราย"})
    report.save("U2", {"category": "ขยะ", "notes": "กองขยะข้างทาง"})  # no location/severity

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert len(rows) == 2
    assert rows[0]["category"] == "ไฟฟ้าสาธารณะ"
    assert rows[0]["location_text"] == "ซอย 5"
    assert rows[1]["location_text"] == ""  # optional fields blank, not missing
    assert rows[1]["severity"] == ""
