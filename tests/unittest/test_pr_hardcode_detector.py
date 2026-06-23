"""Unit tests for PRHardcodeDetector regex pre-filter (_regex_scan).

These tests exercise the offline regex scanner only — no GitHub API, no LLM.
We bypass __init__ via object.__new__ because _regex_scan has no instance deps.
"""

from jclee_bot.review_engine.tools.pr_hardcode_detector import PRHardcodeDetector


def scan(diff: str):
    """Run the regex pre-filter against a unified-diff string."""
    detector = object.__new__(PRHardcodeDetector)
    return detector._regex_scan(diff)


def categories(diff: str):
    return {f["category"] for f in scan(diff)}


def magic_findings(diff: str):
    return [f for f in scan(diff) if f["category"] == "magic_number"]


class TestMagicNumberNoise:
    """The magic_number pattern must not flag every 3+ digit number."""

    def test_http_status_codes_not_flagged(self):
        diff = "\n".join(
            [
                "+    if response.status_code == 200:",
                "+    elif response.status_code == 404:",
                "+    elif response.status_code == 500:",
            ]
        )
        assert magic_findings(diff) == []

    def test_ports_not_flagged_as_magic_number(self):
        diff = "\n".join(
            [
                "+server.listen(8080)",
                "+TLS_PORT = 443",
            ]
        )
        assert magic_findings(diff) == []

    def test_year_not_flagged(self):
        diff = "+    copyright_year = 2024"
        assert magic_findings(diff) == []

    def test_context_bound_timeout_is_flagged(self):
        diff = "+    request_timeout = 5000"
        assert len(magic_findings(diff)) == 1

    def test_context_bound_retry_and_threshold_flagged(self):
        diff = "\n".join(
            [
                "+    retry_limit = 1000",
                "+    alert_threshold = 900",
            ]
        )
        assert len(magic_findings(diff)) == 2


class TestSecretPatternCoverage:
    """High-risk secret formats must be detected by the regex pre-filter."""

    def test_aws_access_key_detected(self):
        diff = "+AWS_ACCESS_KEY_ID = 'AKIA1234567890ABCDEF'"
        assert "aws_access_key" in categories(diff)

    def test_github_classic_token_detected(self):
        diff = "+GITHUB_TOKEN = 'ghp_abcdefghijklmnopqrstuvwxyz0123456789'"
        assert "github_token" in categories(diff)

    def test_github_fine_grained_pat_detected(self):
        token = "github_pat_" + "1" * 22 + "_" + "a" * 59
        diff = f"+PAT = '{token}'"
        assert "github_token" in categories(diff)

    def test_private_key_header_detected(self):
        diff = "+key = '-----BEGIN RSA PRIVATE KEY-----'"
        assert "private_key" in categories(diff)

    def test_openssh_private_key_header_detected(self):
        diff = "+key = '-----BEGIN OPENSSH PRIVATE KEY-----'"
        assert "private_key" in categories(diff)

    def test_jwt_detected(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlVmFsdWU"
        diff = f"+token = '{jwt}'"
        assert "jwt" in categories(diff)

    def test_credentialed_connection_string_detected(self):
        diff = "+MONGO_URI = 'mongodb://admin:s3cret@db.internal:27017/app'"
        assert "connection_string" in categories(diff)

    def test_postgres_connection_string_detected(self):
        diff = "+DSN = 'postgresql://user:pw@10.0.0.5:5432/db'"
        assert "connection_string" in categories(diff)

    def test_github_fine_grained_pat_with_underscores_detected(self):
        # Real fine-grained PATs contain underscores in the token body.
        token = "github_pat_" + "1" * 22 + "_" + "a_b1c2" + "d" * 53
        diff = f"+PAT = '{token}'"
        assert "github_token" in categories(diff)

    def test_sqlalchemy_driver_connection_string_detected(self):
        diff = "+DSN = 'postgresql+psycopg2://user:pw@host:5432/db'"
        assert "connection_string" in categories(diff)

    def test_mysql_driver_connection_string_detected(self):
        diff = "+DSN = 'mysql+pymysql://user:pw@host:3306/db'"
        assert "connection_string" in categories(diff)

    def test_rediss_tls_connection_string_detected(self):
        diff = "+CACHE = 'rediss://user:pw@cache.internal:6380/0'"
        assert "connection_string" in categories(diff)


class TestExistingPatternsPreserved:
    """Ensure the original categories still fire."""

    def test_api_key_still_detected(self):
        diff = "+api_key = \"abcdef1234567890\""
        assert "api_key" in categories(diff)

    def test_secret_still_detected(self):
        diff = "+password = \"hunter2pass\""
        assert "secret" in categories(diff)

    def test_only_added_lines_scanned(self):
        # removed/context lines must be ignored
        diff = "\n".join(
            [
                "-password = \"oldsecret123\"",
                " unchanged = 12345",
            ]
        )
        assert scan(diff) == []


class TestMergeRegexFindings:
    """Regex pre-filter findings must reach the published output, not just logs.

    Regression guard (Oracle): _regex_scan results were only logged; the
    secret/magic patterns had zero effect on what /hardcode reports.
    """

    def _detector(self):
        return object.__new__(PRHardcodeDetector)

    def test_regex_findings_merged_into_llm_findings(self):
        det = self._detector()
        llm = [
            {"severity": "high", "category": "secret", "file": "a.py",
             "line": 5, "description": "hardcoded password"},
        ]
        regex = [
            {"line": 12, "category": "aws_access_key", "content": "key = AKIA..."},
        ]
        merged = det._merge_regex_findings(llm, regex)
        cats = {f["category"] for f in merged}
        assert "secret" in cats
        assert "aws_access_key" in cats
        # regex finding must carry a severity so _publish_findings renders it
        aws = next(f for f in merged if f["category"] == "aws_access_key")
        assert aws.get("severity")
        assert aws.get("line") == 12

    def test_regex_findings_dedup_against_llm_same_line_category(self):
        det = self._detector()
        llm = [
            {"severity": "critical", "category": "aws_access_key", "file": "a.py",
             "line": 12, "description": "AWS key"},
        ]
        regex = [
            {"file": "a.py", "line": 12, "category": "aws_access_key", "content": "key = AKIA..."},
        ]
        merged = det._merge_regex_findings(llm, regex)
        aws = [f for f in merged if f["category"] == "aws_access_key"]
        assert len(aws) == 1, f"expected dedup, got {aws}"

    def test_merge_handles_empty_inputs(self):
        det = self._detector()
        assert det._merge_regex_findings([], []) == []
        only_regex = det._merge_regex_findings(
            [], [{"line": 1, "category": "jwt", "content": "eyJ..."}]
        )
        assert len(only_regex) == 1
        assert only_regex[0]["category"] == "jwt"


class TestRegexScanHunkFormat:
    """_regex_scan must parse the real PR diff format (## File + numbered hunks)
    so findings carry the actual file path and source line number, not diff
    buffer ordinals. (Oracle deeper D2 finding.)
    """

    def _detector(self):
        return object.__new__(PRHardcodeDetector)

    def test_parses_file_and_source_line_from_hunk(self):
        diff = "\n".join([
            "## File: 'src/config.py'",
            "",
            "__new hunk__",
            "880        unchanged = 1",
            "881 +      aws_key = 'AKIA1234567890ABCDEF'",
            "882        other = 2",
        ])
        findings = self._detector()._regex_scan(diff)
        aws = [f for f in findings if f["category"] == "aws_access_key"]
        assert len(aws) == 1, f"expected one aws finding, got {findings}"
        assert aws[0]["file"] == "src/config.py"
        assert aws[0]["line"] == 881

    def test_context_lines_in_hunk_not_scanned(self):
        # only added (+) lines should be scanned; context line with a secret-like
        # token must be ignored.
        diff = "\n".join([
            "## File: 'src/config.py'",
            "__new hunk__",
            "880        aws_key = 'AKIA1234567890ABCDEF'",  # context, no +",
        ])
        findings = self._detector()._regex_scan(diff)
        assert findings == [], f"context line should not be scanned: {findings}"

    def test_multiple_files_attributed_correctly(self):
        diff = "\n".join([
            "## File: 'a.py'",
            "__new hunk__",
            "10 +      token = 'ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'",
            "## File: 'b.py'",
            "__new hunk__",
            "20 +      key = 'AKIA1234567890ABCDEF'",
        ])
        findings = self._detector()._regex_scan(diff)
        by_cat = {f["category"]: f for f in findings}
        assert by_cat["github_token"]["file"] == "a.py"
        assert by_cat["github_token"]["line"] == 10
        assert by_cat["aws_access_key"]["file"] == "b.py"
        assert by_cat["aws_access_key"]["line"] == 20

    def test_simple_plus_format_still_supported(self):
        # Backward-compat: a bare '+line' (no hunk header) still scans.
        findings = self._detector()._regex_scan("+api_key = 'abcdef1234567890'")
        assert any(f["category"] == "api_key" for f in findings)


class TestMergeDedupByFileLineCategory:
    """Dedup must key on (file, line, category), not (line, category) alone."""

    def _detector(self):
        return object.__new__(PRHardcodeDetector)

    def test_same_line_different_file_not_deduped(self):
        det = self._detector()
        llm = [{"severity": "high", "category": "secret", "file": "a.py",
                "line": 12, "description": "x"}]
        regex = [{"file": "b.py", "line": 12, "category": "secret", "content": "y"}]
        merged = det._merge_regex_findings(llm, regex)
        secrets = [f for f in merged if f["category"] == "secret"]
        assert len(secrets) == 2, f"different files must not dedup: {secrets}"

    def test_same_file_line_category_deduped(self):
        det = self._detector()
        llm = [{"severity": "critical", "category": "aws_access_key", "file": "a.py",
                "line": 12, "description": "AWS"}]
        regex = [{"file": "a.py", "line": 12, "category": "aws_access_key", "content": "k"}]
        merged = det._merge_regex_findings(llm, regex)
        aws = [f for f in merged if f["category"] == "aws_access_key"]
        assert len(aws) == 1, f"same file+line+category must dedup: {aws}"


class TestRegexFallbackLineNumbers:
    """Bare unified-diff fallback must assign distinct line numbers so
    different lines do not collapse to (file, '', category) on dedup
    (#263 / #269)."""

    def _detector(self):
        return object.__new__(PRHardcodeDetector)

    def test_fallback_lines_get_distinct_numbers(self):
        # Build AWS-key-shaped fixtures at runtime so no literal key string
        # sits in the file for secret scanners (gitleaks) to flag.
        k1 = "AKIA" + "1234567890ABCDEF"
        k2 = "AKIA" + "Z" * 16
        diff = "\n".join([
            f"+aws_key = '{k1}'",
            "+other = 1",
            f"+aws_key2 = '{k2}'",
        ])
        findings = self._detector()._regex_scan(diff)
        aws = [f for f in findings if f["category"] == "aws_access_key"]
        assert len(aws) == 2, f"expected two aws lines, got {findings}"
        lines = {f["line"] for f in aws}
        assert "" not in lines, f"fallback line must not be empty: {aws}"
        assert len(lines) == 2, f"fallback lines must be distinct: {aws}"

    def test_fallback_findings_survive_merge_dedup(self):
        det = self._detector()
        k1 = "AKIA" + "1234567890ABCDEF"
        k2 = "AKIA" + "Z" * 16
        diff = "\n".join([
            f"+aws_key = '{k1}'",
            f"+aws_key2 = '{k2}'",
        ])
        regex = det._regex_scan(diff)
        merged = det._merge_regex_findings([], regex)
        aws = [f for f in merged if f["category"] == "aws_access_key"]
        assert len(aws) == 2, f"distinct fallback lines must not dedup: {aws}"


class TestNoSecretValueLeak:
    """Merged regex findings must NOT carry the raw matched secret value in
    the published description (#267)."""

    def _detector(self):
        return object.__new__(PRHardcodeDetector)

    def test_description_does_not_contain_raw_secret(self):
        det = self._detector()
        secret = "AKIA" + "1234567890ABCDEF"
        regex = [{
            "file": "a.py", "line": 5, "category": "aws_access_key",
            "content": f"aws_key = '{secret}'",
        }]
        merged = det._merge_regex_findings([], regex)
        desc = merged[0]["description"]
        assert secret not in desc, desc
        assert "aws access key" in desc.lower(), desc
