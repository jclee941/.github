import copy
import re
from functools import partial
from typing import Dict, List

from jinja2 import Environment, StrictUndefined

from jclee_bot.review_engine.algo.ai_handlers.base_ai_handler import BaseAiHandler
from jclee_bot.review_engine.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from jclee_bot.review_engine.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from jclee_bot.review_engine.algo.token_handler import TokenHandler
from jclee_bot.review_engine.config_loader import get_settings
from jclee_bot.review_engine.git_providers import get_git_provider_with_context
from jclee_bot.review_engine.git_providers.git_provider import get_main_pr_language
from jclee_bot.review_engine.log import get_logger

# Regex patterns for common hardcoding issues
HARDCODE_PATTERNS = {
    # High-signal secret formats (specific, low false-positive)
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(
        r"\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9]{22}_[A-Za-z0-9_]{50,})\b"
    ),
    "private_key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    "connection_string": re.compile(
        r"(?i)\b(?:mongodb|postgres(?:ql)?|mysql|mariadb|redis|rediss|amqp)"
        r"(?:\+[a-z0-9]+)?(?:\+srv)?://"
        r"[^:\s/'\"]+:[^@\s/'\"]+@[^\s'\"]+"
    ),
    # Generic credential assignments
    "api_key": re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\'][a-zA-Z0-9\-_]{8,}["\']'),
    "secret": re.compile(r'(?i)(secret|password|passwd|pwd|token)\s*[:=]\s*["\'][^"\']{4,}["\']'),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"),
    "url": re.compile(r'https?://[^\s"\']+(?<!\{)'),
    # Context-bound magic numbers only (timeouts/retries/thresholds), not every
    # 3+ digit literal. The bare `\d{3,}` pattern flagged ports, years and HTTP
    # status codes, drowning real findings in noise.
    "magic_number": re.compile(
        r"(?i)[a-z0-9_]*"
        r"(?:timeout|retry|retries|max_attempts|threshold|interval|delay|backoff|"
        r"ttl|expiry|expires_in|rate_limit|buffer_size|batch_size|page_size|"
        r"pool_size|max_size|chunk_size)"
        r"[a-z0-9_]*\s*[:=]\s*\d{3,}\b"
    ),
}


class PRHardcodeDetector:
    def __init__(self, pr_url: str, args: list = None, ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        self.git_provider = get_git_provider_with_context(pr_url)
        self.main_language = get_main_pr_language(self.git_provider.get_languages(), self.git_provider.get_files())
        self.ai_handler = ai_handler()
        self.ai_handler.main_pr_language = self.main_language

        self.patches_diff = None
        self.prediction = None
        self.repo_name = self.git_provider.repo

        self.vars = {
            "title": self.git_provider.pr.title,
            "branch": self.git_provider.get_pr_branch(),
            "description": self.git_provider.get_pr_description(),
            "language": self.main_language,
            "diff": "",
            "extra_instructions": get_settings().pr_hardcode_detector.get("extra_instructions", ""),
            "repo_name": self.repo_name,
        }

        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self.vars,
            get_settings().pr_hardcode_prompt.system,
            get_settings().pr_hardcode_prompt.user,
        )

    async def run(self):
        try:
            get_logger().info("Scanning PR for hardcoded values...")
            if get_settings().config.publish_output:
                self.git_provider.publish_comment("Scanning for hardcoded values...", is_temporary=True)

            get_logger().info("Preparing hardcode prediction...")
            await retry_with_fallback_models(self._prepare_prediction)

            findings = self._merge_regex_findings(self._parse_findings(), getattr(self, "regex_findings", []))
            if not findings:
                get_logger().info("No hardcoded values detected.")
                if get_settings().config.publish_output:
                    self.git_provider.remove_initial_comment()
                    self.git_provider.publish_comment("✅ No hardcoded values or sensitive data detected in this PR.")
                return

            if get_settings().config.publish_output:
                self.git_provider.remove_initial_comment()
                self._publish_findings(findings)

            # Optionally create GitHub issues for critical findings
            if get_settings().pr_hardcode_detector.get("create_issues", False):
                await self._create_issues_for_findings(findings)
            # Optionally create a fix PR
            if get_settings().pr_hardcode_detector.get("create_fix_pr", False):
                await self._create_fix_pr(findings)

        except Exception as e:
            get_logger().error(f"Failed to detect hardcoded values, error: {e}")

    async def _prepare_prediction(self, model: str):
        get_logger().info("Getting PR diff...")
        self.patches_diff = get_pr_diff(
            self.git_provider, self.token_handler, model, add_line_numbers_to_hunks=True, disable_extra_lines=False
        )

        # Quick regex pre-filter
        self.regex_findings = self._regex_scan(self.patches_diff)
        if self.regex_findings:
            get_logger().info(f"Regex pre-filter found {len(self.regex_findings)} potential hardcoded values")

        get_logger().info("Getting AI prediction for hardcode detection...")
        self.prediction = await self._get_prediction(model)

    # Matches a numbered hunk line: "881 +      content" or "880        content".
    # group 1 = source line number, group 2 = '+' for added lines (else absent).
    _HUNK_LINE_RE = re.compile(r"^(\d+)\s+(\+)?\s*(.*)$")
    _FILE_HEADER_RE = re.compile(r"^## File:?\s*'?([^'\n]+?)'?\s*$")

    def _regex_scan(self, diff: str) -> List[Dict]:
        """Scan added lines of a PR diff for hardcoded secrets/values.

        Handles two formats:
        1. The real pr-agent diff (add_line_numbers_to_hunks=True): blocks led by
           "## File: '<path>'" and "__new hunk__", where added lines look like
           "881 +      content" (group1=source line, '+' marks an addition).
        2. A bare unified-diff fragment where added lines start with '+' (used by
           lightweight tests and as a fallback).
        """
        findings: List[Dict] = []
        current_file = ""
        # Running ordinal for bare unified-diff added lines (no real line number
        # available) so distinct lines don't collapse to (file, '', category)
        # during dedup (#263/#269).
        fallback_ordinal = 0
        for raw in diff.splitlines():
            file_match = self._FILE_HEADER_RE.match(raw.strip())
            if file_match:
                current_file = file_match.group(1).strip()
                continue
            if raw.startswith("__") or raw.startswith("@@"):
                continue

            source_line: int | str = ""
            content = None
            hunk_match = self._HUNK_LINE_RE.match(raw)
            if hunk_match:
                # Numbered hunk format: only scan added ('+') lines.
                if hunk_match.group(2) != "+":
                    continue
                source_line = int(hunk_match.group(1))
                content = hunk_match.group(3)
            elif raw.startswith("+") and not raw.startswith("+++"):
                # Bare unified-diff fallback: no source line number, so use a
                # monotonic ordinal to keep each added line distinct.
                fallback_ordinal += 1
                source_line = f"+{fallback_ordinal}"
                content = raw[1:]
            else:
                continue

            content = content.strip()
            for category, pattern in HARDCODE_PATTERNS.items():
                if pattern.search(content):
                    findings.append(
                        {
                            "file": current_file,
                            "line": source_line,
                            "category": category,
                            "content": content,
                        }
                    )
        return findings

    # Severity assigned to regex pre-filter findings when merged into output.
    _REGEX_SEVERITY = {
        "aws_access_key": "critical",
        "github_token": "critical",
        "private_key": "critical",
        "jwt": "high",
        "connection_string": "high",
        "secret": "high",
        "api_key": "high",
        "ip_address": "low",
        "url": "low",
        "magic_number": "low",
    }

    def _merge_regex_findings(self, llm_findings: List[Dict], regex_findings: List[Dict]) -> List[Dict]:
        """Merge deterministic regex pre-filter findings into the LLM findings.

        The regex scan was previously only logged, so its secret/magic patterns
        never affected published output. We normalize each regex hit to the
        published finding shape and append it, deduping against LLM findings
        that already cover the same (file, line, category).
        """
        merged = list(llm_findings or [])
        seen = {
            (str(f.get("file", "")), f.get("line"), str(f.get("category", "")).lower())
            for f in merged
        }
        for rf in regex_findings or []:
            key = (str(rf.get("file", "")), rf.get("line"), str(rf.get("category", "")).lower())
            if key in seen:
                continue
            seen.add(key)
            category = rf.get("category", "unknown")
            # Do NOT echo the raw matched value: it may be a real secret and
            # this finding can surface in public PR comments / issues (#267).
            category_label = str(category).replace("_", " ")
            merged.append(
                {
                    "severity": self._REGEX_SEVERITY.get(category, "medium"),
                    "category": category,
                    "file": rf.get("file", ""),
                    "line": rf.get("line", ""),
                    "description": f"Potential hardcoded {category_label} detected by regex pre-filter (value redacted)",
                    "source": "regex",
                }
            )
        return merged

    async def _get_prediction(self, model: str):
        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().pr_hardcode_prompt.system).render(variables)
        user_prompt = environment.from_string(get_settings().pr_hardcode_prompt.user).render(variables)
        if get_settings().config.verbosity_level >= 2:
            get_logger().info(f"\nSystem prompt:\n{system_prompt}")
            get_logger().info(f"\nUser prompt:\n{user_prompt}")
        response, finish_reason = await self.ai_handler.chat_completion(
            model=model, temperature=get_settings().config.temperature, system=system_prompt, user=user_prompt
        )
        return response

    def _parse_findings(self) -> List[Dict]:
        import yaml

        try:
            data = yaml.safe_load(self.prediction.strip())
            if isinstance(data, dict) and "findings" in data:
                return data["findings"]
            if isinstance(data, list):
                return data
        except Exception as e:
            get_logger().warning(f"Could not parse findings as YAML: {e}")
        return []

    def _publish_findings(self, findings: List[Dict]):
        severity_icons = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }

        body = "## ⚠️ Hardcoded Values Detected\n\n"
        body += "The following hardcoded values or sensitive data were detected in this PR:\n\n"
        body += "| Severity | Category | File | Line | Description |\n"
        body += "|----------|----------|------|------|-------------|\n"

        for f in findings:
            severity = f.get("severity", "medium").lower()
            icon = severity_icons.get(severity, "🟡")
            category = f.get("category", "unknown")
            file_path = f.get("file", "N/A")
            line = f.get("line", "N/A")
            description = f.get("description", "").replace("|", "\\|")
            body += f"| {icon} {severity.upper()} | {category} | `{file_path}` | {line} | {description} |\n"

        body += (
            "\n**Recommendation:** Consider extracting these values into environment "
            "variables, configuration files, or secrets management systems."
        )

        self.git_provider.publish_comment(body)

    async def _create_issues_for_findings(self, findings: List[Dict]):
        try:
            if hasattr(self.git_provider, "_get_repo"):
                repo = self.git_provider._get_repo()
                for f in findings:
                    if f.get("severity", "").lower() in ("critical", "high"):
                        title = f"[Hardcode] {f.get('category', 'Unknown')} in {f.get('file', 'repo')}"
                        body = f"**Severity:** {f.get('severity', 'unknown')}\n\n"
                        body += f"**File:** `{f.get('file', 'N/A')}`\n\n"
                        body += f"**Line:** {f.get('line', 'N/A')}\n\n"
                        body += f"**Description:** {f.get('description', '')}\n\n"
                        body += (
                            "**Suggested Fix:** Extract this hardcoded value into "
                            "environment variables or a configuration file."
                        )
                        try:
                            repo.create_issue(title=title, body=body, labels=["hardcode", "security"])
                            get_logger().info(f"Created issue: {title}")
                        except Exception as e:
                            get_logger().warning(f"Failed to create issue: {e}")
        except Exception as e:
            get_logger().warning(f"Issue creation not available: {e}")

    async def _create_fix_pr(self, findings: List[Dict]):
        try:
            if not hasattr(self.git_provider, "create_branch") or not hasattr(self.git_provider, "create_pull"):
                get_logger().warning("Git provider does not support branch/PR creation")
                return

            import time

            branch_name = f"bot/auto-fix-hardcode-{int(time.time())}"
            base_branch = self.git_provider.get_pr_branch()

            # Create branch
            self.git_provider.create_branch(branch_name, base_branch)
            get_logger().info(f"Created branch: {branch_name}")

            # Generate .env.example content
            env_content = self._generate_env_example(findings)

            # Commit file
            self.git_provider.create_or_update_pr_file(
                file_path=".env.example",
                branch=branch_name,
                contents=env_content,
                message="[bot] Add environment variable examples for hardcoded values",
            )
            get_logger().info("Committed .env.example")

            # Create PR
            pr_title = "[bot] Fix hardcoded values detected in PR"
            pr_body = "## 🔧 Hardcoded Values Fix Proposal\n\n"
            pr_body += "The following hardcoded values were detected and should be externalized:\n\n"
            for f in findings:
                pr_body += (
                    f"- **{f.get('category', 'unknown')}** in "
                    f"`{f.get('file', 'N/A')}:{f.get('line', 'N/A')}`: "
                    f"{f.get('description', '')}\n"
                )
            pr_body += "\n### Suggested Changes\n"
            pr_body += "1. Review the generated `.env.example` file\n"
            pr_body += "2. Replace hardcoded values with environment variable references\n"
            pr_body += "3. Update your application code to read from environment variables\n"
            pr_body += "\n_This PR was auto-generated by jclee-bot._"

            self.git_provider.create_pull(pr_title, pr_body, branch_name, base_branch)
            get_logger().info(f"Created fix PR: {pr_title}")
        except Exception as e:
            get_logger().error(f"Failed to create fix PR: {e}")

    def _generate_env_example(self, findings: List[Dict]) -> str:
        lines = ["# Environment Variables", "# Auto-generated by jclee-bot", ""]
        seen = set()
        for f in findings:
            category = f.get("category", "unknown").upper()
            if category in seen:
                continue
            seen.add(category)
            if "API" in category or "KEY" in category:
                lines.append("# API Key - replace with your actual key")
                lines.append("API_KEY=your_api_key_here")
            elif "SECRET" in category or "PASSWORD" in category or "TOKEN" in category:
                lines.append("# Secret - replace with your actual secret")
                lines.append("SECRET=your_secret_here")
            elif "IP" in category or "HOST" in category:
                lines.append("# Server host/IP")
                lines.append("HOST=your_host_here")
            elif "URL" in category or "ENDPOINT" in category:
                lines.append("# API/base URL")
                lines.append("API_URL=https://your-api-url.com")
            elif "MAGIC" in category or "NUMBER" in category:
                lines.append("# Named constants are preferred over magic numbers")
            else:
                lines.append(f"# {category}")
                lines.append(f"{category}=your_value_here")
            lines.append("")
        lines.append("# Add these to your application startup code:")
        lines.append("# import os")
        lines.append("# api_key = os.environ.get('API_KEY')")
        return "\n".join(lines)
