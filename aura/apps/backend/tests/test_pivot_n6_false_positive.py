from __future__ import annotations

from aegisure.diff_risk import analyze_diff
from aegisure.finding_dismissals import dismiss_finding, list_dismissed_findings


def test_findings_use_launch_severity_tiers_and_can_be_dismissed(tmp_path):
    report = analyze_diff("""diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1,2 @@
 print("ok")
+password = "hunter22222"
""")
    finding = report.findings[0]
    assert finding.severity in {"info", "warning", "high", "critical"}
    assert report.verdict == "block"

    fp = dismiss_finding(tmp_path, finding)
    assert fp in list_dismissed_findings(tmp_path)
