import json
import pytest
from neurometric.reports.evidence import REPORT_TYPES, build_report, demo_study


@pytest.fixture(scope="module")
def sd():
    return demo_study(n=6, seed=1)


@pytest.mark.parametrize("rtype", list(REPORT_TYPES))
def test_each_report_builds_with_disclaimers(sd, rtype, tmp_path):
    js = build_report(sd, rtype, tmp_path)
    md = (tmp_path / f"{rtype}.md").read_text()
    assert (tmp_path / f"{rtype}.pdf").stat().st_size > 1500
    assert "not a regulatory submission" in md
    assert "SYNTHETIC" in md
    assert js["provenance"]["synthetic"] is True
    assert len(js["provenance"]["data_sha256"]) == 64
    json.dumps(js)


def test_report_is_reproducible(sd, tmp_path):
    a = build_report(sd, "sponsor_study_summary", tmp_path / "a")
    b = build_report(sd, "sponsor_study_summary", tmp_path / "b")
    assert a["provenance"]["data_sha256"] == b["provenance"]["data_sha256"]
    assert a["results"] == b["results"]
