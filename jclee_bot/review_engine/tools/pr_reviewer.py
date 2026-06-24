import copy
import datetime
import hashlib
from functools import partial
from typing import List, Tuple

from jinja2 import Environment, StrictUndefined

from jclee_bot.review_engine.algo.ai_handlers.base_ai_handler import BaseAiHandler
from jclee_bot.review_engine.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from jclee_bot.review_engine.algo.pr_processing import (
    add_ai_metadata_to_diff_files,
    get_pr_diff,
    retry_with_fallback_models,
)
from jclee_bot.review_engine.algo.token_handler import TokenHandler
from jclee_bot.review_engine.algo.utils import (
    ModelType,
    PRReviewHeader,
    convert_to_markdown_v2,
    github_action_output,
    load_yaml,
    show_relevant_configurations,
)
from jclee_bot.review_engine.config_loader import get_settings
from jclee_bot.review_engine.git_providers import get_git_provider_with_context
from jclee_bot.review_engine.git_providers.git_provider import IncrementalPR, get_main_pr_language
from jclee_bot.review_engine.log import get_logger
from jclee_bot.review_engine.servers.help import HelpMessage
from jclee_bot.review_engine.tools.ticket_pr_compliance_check import extract_and_cache_pr_tickets


class PRReviewer:
    """
    The PRReviewer class is responsible for reviewing a pull request and generating feedback using an AI model.
    """

    def __init__(
        self,
        pr_url: str,
        is_answer: bool = False,
        is_auto: bool = False,
        args: list = None,
        ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler,
    ):
        """
        Initialize the PRReviewer object with the necessary attributes and objects to review a pull request.

        Args:
            pr_url (str): The URL of the pull request to be reviewed.
            is_answer (bool, optional): Indicates whether the review is being done in answer mode. Defaults to False.
            is_auto (bool, optional): Indicates whether the review is being done in automatic mode. Defaults to False.
            ai_handler (BaseAiHandler): The AI handler to be used for the review. Defaults to None.
            args (list, optional): List of arguments passed to the PRReviewer class. Defaults to None.
        """
        self.git_provider = get_git_provider_with_context(pr_url)
        self.args = args
        self.incremental = self.parse_incremental(args)  # -i command
        if self.incremental and self.incremental.is_incremental:
            self.git_provider.get_incremental_commits(self.incremental)

        self.main_language = get_main_pr_language(self.git_provider.get_languages(), self.git_provider.get_files())
        self.pr_url = pr_url
        self.is_answer = is_answer
        self.is_auto = is_auto

        if self.is_answer and not self.git_provider.is_supported("get_issue_comments"):
            raise Exception(f"Answer mode is not supported for {get_settings().config.git_provider} for now")
        self.ai_handler = ai_handler()
        self.ai_handler.main_pr_language = self.main_language
        self.patches_diff = None
        self.prediction = None
        answer_str, question_str = self._get_user_answers()
        self.pr_description, self.pr_description_files = self.git_provider.get_pr_description(
            split_changes_walkthrough=True
        )
        if (
            self.pr_description_files
            and get_settings().get("config.is_auto_command", False)
            and get_settings().get("config.enable_ai_metadata", False)
        ):
            add_ai_metadata_to_diff_files(self.git_provider, self.pr_description_files)
            get_logger().debug(f"AI metadata added to the this command")
        else:
            get_settings().set("config.enable_ai_metadata", False)
            get_logger().debug(f"AI metadata is disabled for this command")

        self.vars = {
            "title": self.git_provider.pr.title,
            "branch": self.git_provider.get_pr_branch(),
            "description": self.pr_description,
            "language": self.main_language,
            "diff": "",  # empty diff for initial calculation
            "num_pr_files": self.git_provider.get_num_of_files(),
            "num_max_findings": get_settings().pr_reviewer.num_max_findings,
            "require_score": get_settings().pr_reviewer.require_score_review,
            "require_tests": get_settings().pr_reviewer.require_tests_review,
            "require_estimate_effort_to_review": get_settings().pr_reviewer.require_estimate_effort_to_review,
            "require_estimate_contribution_time_cost": get_settings().pr_reviewer.require_estimate_contribution_time_cost,
            "require_can_be_split_review": get_settings().pr_reviewer.require_can_be_split_review,
            "require_security_review": get_settings().pr_reviewer.require_security_review,
            "require_todo_scan": get_settings().pr_reviewer.get("require_todo_scan", False),
            "question_str": question_str,
            "answer_str": answer_str,
            "extra_instructions": get_settings().pr_reviewer.extra_instructions,
            "commit_messages_str": self.git_provider.get_commit_messages(),
            "custom_labels": "",
            "enable_custom_labels": get_settings().config.enable_custom_labels,
            "is_ai_metadata": get_settings().get("config.enable_ai_metadata", False),
            "related_tickets": get_settings().get("related_tickets", []),
            "duplicate_prompt_examples": get_settings().config.get("duplicate_prompt_examples", False),
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        }

        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self.vars,
            get_settings().pr_review_prompt.system,
            get_settings().pr_review_prompt.user,
        )

    def parse_incremental(self, args: List[str]):
        is_incremental = False
        if args and len(args) >= 1:
            arg = args[0]
            if arg == "-i":
                is_incremental = True
        incremental = IncrementalPR(is_incremental)
        return incremental

    async def run(self) -> None:
        try:
            if not self.git_provider.get_files():
                get_logger().info(f"PR has no files: {self.pr_url}, skipping review")
                return None

            if self.incremental.is_incremental and not self._can_run_incremental_review():
                return None

            # if isinstance(self.args, list) and self.args and self.args[0] == 'auto_approve':
            #     get_logger().info(f'Auto approve flow PR: {self.pr_url} ...')
            #     self.auto_approve_logic()
            #     return None

            get_logger().info(f"Reviewing PR: {self.pr_url} ...")
            relevant_configs = {"pr_reviewer": dict(get_settings().pr_reviewer), "config": dict(get_settings().config)}
            get_logger().debug("Relevant configs", artifacts=relevant_configs)

            # ticket extraction if exists
            await extract_and_cache_pr_tickets(self.git_provider, self.vars)

            if (
                self.incremental.is_incremental
                and hasattr(self.git_provider, "unreviewed_files_set")
                and not self.git_provider.unreviewed_files_set
            ):
                get_logger().info(f"Incremental review is enabled for {self.pr_url} but there are no new files")
                previous_review_url = ""
                if hasattr(self.git_provider, "previous_review"):
                    previous_review_url = self.git_provider.previous_review.html_url
                if get_settings().config.publish_output:
                    self.git_provider.publish_comment(
                        f"Incremental Review Skipped\n"
                        f"No files were changed since the [previous PR Review]({previous_review_url})"
                    )
                return None

            if get_settings().config.publish_output and not get_settings().config.get("is_auto_command", False):
                self.git_provider.publish_comment("Preparing review...", is_temporary=True)

            await retry_with_fallback_models(self._prepare_prediction, model_type=ModelType.REGULAR)
            if not self.prediction:
                self.git_provider.remove_initial_comment()
                return None

            pr_review = self._prepare_pr_review()
            get_logger().debug(f"PR output", artifact=pr_review)

            should_publish = get_settings().config.publish_output and self._should_publish_review_no_suggestions(
                pr_review
            )
            if not should_publish:
                reason = "Review output is not published"
                if get_settings().config.publish_output:
                    reason += ": no major issues detected."
                get_logger().info(reason)
                get_settings().data = {"artifact": pr_review}
                return

            # publish the review
            if get_settings().pr_reviewer.persistent_comment and not self.incremental.is_incremental:
                final_update_message = get_settings().pr_reviewer.final_update_message
                self.git_provider.publish_persistent_comment(
                    pr_review,
                    initial_header=f"{PRReviewHeader.REGULAR.value} 🔍",
                    update_header=True,
                    final_update_message=final_update_message,
                )
            else:
                self.git_provider.publish_comment(pr_review)

            self.git_provider.remove_initial_comment()
            self._create_issues_for_review_findings()
        except Exception as e:
            get_logger().error(f"Failed to review PR: {e}")

    def _should_publish_review_no_suggestions(self, pr_review: str) -> bool:
        return (
            get_settings().pr_reviewer.get("publish_output_no_suggestions", True)
            or "No major issues detected" not in pr_review
        )

    async def _prepare_prediction(self, model: str) -> None:
        self.patches_diff = get_pr_diff(
            self.git_provider,
            self.token_handler,
            model,
            add_line_numbers_to_hunks=True,
            disable_extra_lines=False,
        )

        if self.patches_diff:
            get_logger().debug(f"PR diff", diff=self.patches_diff)
            self.prediction = await self._get_prediction(model)
        else:
            get_logger().warning(f"Empty diff for PR: {self.pr_url}")
            self.prediction = None

    async def _get_prediction(self, model: str) -> str:
        """
        Generate an AI prediction for the pull request review.

        Args:
            model: A string representing the AI model to be used for the prediction.

        Returns:
            A string representing the AI prediction for the pull request review.
        """
        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff  # update diff

        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().pr_review_prompt.system).render(variables)
        user_prompt = environment.from_string(get_settings().pr_review_prompt.user).render(variables)

        response, finish_reason = await self.ai_handler.chat_completion(
            model=model, temperature=get_settings().config.temperature, system=system_prompt, user=user_prompt
        )

        return response

    def _prepare_pr_review(self) -> str:
        """
        Prepare the PR review by processing the AI prediction and generating a markdown-formatted text that summarizes
        the feedback.
        """
        first_key = "review"
        last_key = "security_concerns"
        data = load_yaml(
            self.prediction.strip(),
            keys_fix_yaml=[
                "ticket_compliance_check",
                "estimated_effort_to_review_[1-5]:",
                "security_concerns:",
                "key_issues_to_review:",
                "relevant_file:",
                "relevant_line:",
                "suggestion:",
            ],
            first_key=first_key,
            last_key=last_key,
        )
        self.review_data = data  # Store for auto-issue creation
        github_action_output(data, "review")

        if "review" not in data:
            get_logger().exception("Failed to parse review data", artifact={"data": data})
            return ""

        # move data['review'] 'key_issues_to_review' key to the end of the dictionary
        if "key_issues_to_review" in data["review"]:
            key_issues_to_review = data["review"].pop("key_issues_to_review")
            data["review"]["key_issues_to_review"] = key_issues_to_review

        incremental_review_markdown_text = None
        # Add incremental review section
        if self.incremental.is_incremental:
            last_commit_url = (
                f"{self.git_provider.get_pr_url()}/commits/{self.git_provider.incremental.first_new_commit_sha}"
            )
            incremental_review_markdown_text = f"Starting from commit {last_commit_url}"

        markdown_text = convert_to_markdown_v2(
            data,
            self.git_provider.is_supported("gfm_markdown"),
            incremental_review_markdown_text,
            git_provider=self.git_provider,
            files=self.git_provider.get_diff_files(),
        )

        # Add help text if gfm_markdown is supported
        if self.git_provider.is_supported("gfm_markdown") and get_settings().pr_reviewer.enable_help_text:
            markdown_text += "<hr>\n\n<details> <summary><strong>💡 Tool usage guide:</strong></summary><hr> \n\n"
            markdown_text += HelpMessage.get_review_usage_guide()
            markdown_text += "\n</details>\n"

        # Output the relevant configurations if enabled
        if get_settings().get("config", {}).get("output_relevant_configurations", False):
            markdown_text += show_relevant_configurations(relevant_section="pr_reviewer")

        # Add custom labels from the review prediction (effort, security)
        self.set_review_labels(data)

        if markdown_text is None or len(markdown_text) == 0:
            markdown_text = ""

        return markdown_text

    def _create_issues_for_review_findings(self):
        if not get_settings().pr_reviewer.get("auto_create_issues", False):
            return

        try:
            findings = self._extract_auto_issue_findings()
            if not findings:
                return

            labels = get_settings().pr_reviewer.get("auto_create_issue_labels", ["jclee-bot", "review-finding"])
            self.git_provider.ensure_labels(labels)

            for finding in findings:
                self._create_single_issue(finding, labels)
        except Exception as e:
            get_logger().warning(f"Auto-issue creation failed: {e}")

    def _record_schema_mismatch(self, field: str, value) -> None:
        """Record an LLM schema mismatch (got non-dict where dict expected)."""
        try:
            from jclee_bot.review_engine.servers.monitoring import record_llm_failure
            model = get_settings().get("config.model", "unknown")
            record_llm_failure("schema_mismatch", model)
        except Exception as e:
            get_logger().warning(f"Failed to record schema_mismatch metric: {e}")
        get_logger().warning(
            f"PR reviewer schema mismatch: '{field}' is {type(value).__name__}, expected dict",
            artifact={
                "field": field,
                "type": type(value).__name__,
                "value_preview": str(value)[:200],
            },
        )

    def _extract_auto_issue_findings(self):
        findings = []
        data = getattr(self, "review_data", {})

        # Defensive: load_yaml can return non-dict (e.g. str) when the LLM
        # response is malformed or returns plain prose instead of structured YAML.
        # Observed with some gpt-5.5 responses. Record and skip rather than crash.
        if not isinstance(data, dict):
            self._record_schema_mismatch("review_data", data)
            return findings

        review = data.get("review", {})
        if not isinstance(review, dict):
            self._record_schema_mismatch("review", review)
            return findings

        # Check security_concerns
        security = review.get("security_concerns", "")
        if security and str(security).strip() and str(security).strip().lower() not in ["no", "none", "n/a", ""]:
            findings.append(
                {
                    "category": "security",
                    "severity": "critical",
                    "title": f"[Review][Security] Security concerns detected",
                    "content": str(security),
                    "file": "",
                    "start_line": 0,
                    "end_line": 0,
                }
            )

        # Check key_issues_to_review
        key_issues = review.get("key_issues_to_review", [])
        if isinstance(key_issues, dict):
            key_issues = [key_issues]
        if not isinstance(key_issues, list):
            return findings

        for issue in key_issues:
            if not isinstance(issue, dict):
                continue
            header = str(issue.get("issue_header", "")).lower()
            content = str(issue.get("issue_content", "")).lower()
            combined = header + " " + content

            category = None
            severity = "high"

            # Security patterns
            if any(
                kw in combined
                for kw in [
                    "security",
                    "vulnerability",
                    "injection",
                    "xss",
                    "csrf",
                    "secret",
                    "credential",
                    "auth",
                    "authentication bypass",
                    "rce",
                    "remote code",
                ]
            ):
                category = "security"
                severity = "critical"

            # Bug patterns
            elif any(
                kw in combined
                for kw in [
                    "bug",
                    "incorrect",
                    "broken",
                    "crash",
                    "data loss",
                    "race condition",
                    "deadlock",
                    "exception",
                    "error",
                ]
            ):
                category = "bug"
                severity = "critical" if "data loss" in combined or "crash" in combined else "high"

            # Critical patterns
            elif any(kw in combined for kw in ["critical", "privilege escalation", "secret exposure"]):
                category = "critical"
                severity = "critical"

            if category:
                file_path = issue.get("relevant_file", "")
                start_line = issue.get("start_line", 0) or 0
                end_line = issue.get("end_line", 0) or 0
                findings.append(
                    {
                        "category": category,
                        "severity": severity,
                        "title": f"[Review][{category.capitalize()}] {issue.get('issue_header', 'Issue')}",
                        "content": issue.get("issue_content", ""),
                        "file": file_path,
                        "start_line": start_line,
                        "end_line": end_line,
                    }
                )

        return findings

    def _create_single_issue(self, finding, default_labels):
        pr_url = self.git_provider.get_pr_url()
        repo = self.git_provider.repo

        # Build fingerprint marker from structural position + category + a stable
        # hash of the finding content. The LLM-generated *title* is excluded
        # because it is reworded across re-reviews (which would create duplicate
        # issues), but category and content are included so that two DISTINCT
        # findings sharing the same line span (or repo-level findings with no
        # location) do not collapse into a single marker.
        content_hash = hashlib.sha256(str(finding.get("content", "")).encode()).hexdigest()[:8]
        marker_input = (
            f"{repo}|{finding['file']}|{finding['start_line']}|{finding['end_line']}"
            f"|{finding.get('category', '')}|{content_hash}"
        )
        fingerprint = hashlib.sha256(marker_input.encode()).hexdigest()[:16]
        marker = f"<!-- jclee-bot-review-finding: {fingerprint} -->"

        # Check for duplicates
        search_labels = list(default_labels)
        existing = self.git_provider.find_open_issue_by_marker(marker, labels=search_labels)
        if existing:
            get_logger().info(f"Skipping duplicate issue: {finding['title']}")
            return

        # Build labels
        labels = list(default_labels)
        if finding["category"] == "security":
            labels.extend(get_settings().pr_reviewer.get("auto_create_issue_security_labels", ["security", "critical"]))
        elif finding["category"] == "bug":
            labels.extend(get_settings().pr_reviewer.get("auto_create_issue_bug_labels", ["bug", "critical"]))
        elif finding["category"] == "critical":
            labels.extend(["critical"])
        labels = list(dict.fromkeys(labels))  # dedup while preserving order

        # Build body
        body_lines = [
            marker,
            "",
            "## Automated Review Finding",
            "",
            f"**Category:** {finding['category'].capitalize()}",
            f"**Severity:** {finding['severity'].upper()}",
            f"**Source PR:** {pr_url}",
        ]
        if finding["file"]:
            body_lines.append(f"**File:** `{finding['file']}`")
        if finding["start_line"]:
            body_lines.append(f"**Lines:** {finding['start_line']}-{finding['end_line']}")
        body_lines.extend(
            [
                f"**Model:** `{get_settings().config.model}`",
                "",
                "## Finding",
                "",
                str(finding["content"]),
                "",
                "## Suggested Action",
                "",
                "Review the PR finding, confirm exploitability/impact, and fix before merging.",
            ]
        )
        body = "\n".join(body_lines)

        # Create issue
        result = self.git_provider.create_issue(
            title=finding["title"],
            body=body,
            labels=labels,
        )
        if result:
            get_logger().info(f"Created issue #{result.number}: {finding['title']}")
        else:
            get_logger().warning(f"Failed to create issue: {finding['title']}")

    def _get_user_answers(self) -> Tuple[str, str]:
        """
        Retrieves the question and answer strings from the discussion messages related to a pull request.

        Returns:
            A tuple containing the question and answer strings.
        """
        question_str = ""
        answer_str = ""

        if self.is_answer:
            discussion_messages = self.git_provider.get_issue_comments()

            for message in discussion_messages.reversed:
                if "Questions to better understand the PR:" in message.body:
                    question_str = message.body
                elif "/answer" in message.body:
                    answer_str = message.body

                if answer_str and question_str:
                    break

        return question_str, answer_str

    def _get_previous_review_comment(self):
        """
        Get the previous review comment if it exists.
        """
        try:
            if hasattr(self.git_provider, "get_previous_review"):
                return self.git_provider.get_previous_review(
                    full=not self.incremental.is_incremental,
                    incremental=self.incremental.is_incremental,
                )
        except Exception as e:
            get_logger().exception(f"Failed to get previous review comment, error: {e}")

    def _remove_previous_review_comment(self, comment):
        """
        Remove the previous review comment if it exists.
        """
        try:
            if comment:
                self.git_provider.remove_comment(comment)
        except Exception as e:
            get_logger().exception(f"Failed to remove previous review comment, error: {e}")

    def _can_run_incremental_review(self) -> bool:
        """
        Checks if we can run incremental review according the various configurations and previous review.
        """
        # checking if running is auto mode but there are no new commits
        if self.is_auto and not self.incremental.first_new_commit_sha:
            get_logger().info(f"Incremental review is enabled for {self.pr_url} but there are no new commits")
            return False

        if not hasattr(self.git_provider, "get_incremental_commits"):
            get_logger().info(f"Incremental review is not supported for {get_settings().config.git_provider}")
            return False
        # checking if there are enough commits to start the review
        num_new_commits = len(self.incremental.commits_range)
        num_commits_threshold = get_settings().pr_reviewer.minimal_commits_for_incremental_review
        not_enough_commits = num_new_commits < num_commits_threshold
        # checking if the commits are not too recent to start the review
        recent_commits_threshold = datetime.datetime.now() - datetime.timedelta(
            minutes=get_settings().pr_reviewer.minimal_minutes_for_incremental_review
        )
        last_seen_commit_date = (
            self.incremental.last_seen_commit.commit.author.date if self.incremental.last_seen_commit else None
        )
        all_commits_too_recent = (
            last_seen_commit_date > recent_commits_threshold if self.incremental.last_seen_commit else False
        )
        # check all the thresholds or just one to start the review
        condition = any if get_settings().pr_reviewer.require_all_thresholds_for_incremental_review else all
        if condition((not_enough_commits, all_commits_too_recent)):
            get_logger().info(
                f"Incremental review is enabled for {self.pr_url} but didn't pass the threshold check to run:"
                f"\n* Number of new commits = {num_new_commits} (threshold is {num_commits_threshold})"
                f"\n* Last seen commit date = {last_seen_commit_date} (threshold is {recent_commits_threshold})"
            )
            return False
        return True

    def set_review_labels(self, data):
        if not get_settings().config.publish_output:
            return

        if not get_settings().pr_reviewer.require_estimate_effort_to_review:
            get_settings().pr_reviewer.enable_review_labels_effort = False  # we did not generate this output
        if not get_settings().pr_reviewer.require_security_review:
            get_settings().pr_reviewer.enable_review_labels_security = False  # we did not generate this output

        if (
            get_settings().pr_reviewer.enable_review_labels_security
            or get_settings().pr_reviewer.enable_review_labels_effort
        ):
            try:
                review_labels = []
                if get_settings().pr_reviewer.enable_review_labels_effort:
                    estimated_effort = data["review"]["estimated_effort_to_review_[1-5]"]
                    estimated_effort_number = 0
                    if isinstance(estimated_effort, str):
                        try:
                            estimated_effort_number = int(estimated_effort.split(",")[0])
                        except ValueError:
                            get_logger().warning(f"Invalid estimated_effort value: {estimated_effort}")
                    elif isinstance(estimated_effort, int):
                        estimated_effort_number = estimated_effort
                    else:
                        get_logger().warning(f"Unexpected type for estimated_effort: {type(estimated_effort)}")
                    if 1 <= estimated_effort_number <= 5:  # 1, because ...
                        review_labels.append(f"Review effort {estimated_effort_number}/5")
                if (
                    get_settings().pr_reviewer.enable_review_labels_security
                    and get_settings().pr_reviewer.require_security_review
                ):
                    security_concerns = data["review"]["security_concerns"]  # yes, because ...
                    security_concerns_bool = "yes" in security_concerns.lower() or "true" in security_concerns.lower()
                    if security_concerns_bool:
                        review_labels.append("Possible security concern")

                current_labels = self.git_provider.get_pr_labels(update=True)
                if not current_labels:
                    current_labels = []
                get_logger().debug(f"Current labels:\n{current_labels}")
                if current_labels:
                    current_labels_filtered = [
                        label
                        for label in current_labels
                        if not label.lower().startswith("review effort")
                        and not label.lower().startswith("possible security concern")
                    ]
                else:
                    current_labels_filtered = []
                new_labels = review_labels + current_labels_filtered
                if (current_labels or review_labels) and sorted(new_labels) != sorted(current_labels):
                    get_logger().info(f"Setting review labels:\n{review_labels + current_labels_filtered}")
                    self.git_provider.publish_labels(new_labels)
                else:
                    get_logger().info(f"Review labels are already set:\n{review_labels + current_labels_filtered}")
            except Exception as e:
                get_logger().error(f"Failed to set review labels, error: {e}")

    def auto_approve_logic(self):
        """
        Auto-approve a pull request if it meets the conditions for auto-approval.
        """
        if get_settings().config.enable_auto_approval:
            is_auto_approved = self.git_provider.auto_approve()
            if is_auto_approved:
                get_logger().info("Auto-approved PR")
                self.git_provider.publish_comment("Auto-approved PR")
        else:
            get_logger().info("Auto-approval option is disabled")
            self.git_provider.publish_comment(
                "Auto-approval option for PR-Agent is disabled. "
                "You can enable it via a [configuration file](https://github.com/qodo-ai/pr-agent/blob/main/docs/docs/tools/review.md)"
            )
