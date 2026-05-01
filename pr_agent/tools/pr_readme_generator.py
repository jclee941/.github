import copy
from functools import partial
from typing import Optional

from jinja2 import Environment, StrictUndefined

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider_with_context
from pr_agent.git_providers.git_provider import get_main_pr_language
from pr_agent.log import get_logger


class PRReadmeGenerator:
    def __init__(self, pr_url: str, args: list = None, ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        self.git_provider = get_git_provider_with_context(pr_url)
        self.main_language = get_main_pr_language(self.git_provider.get_languages(), self.git_provider.get_files())
        self.ai_handler = ai_handler()
        self.ai_handler.main_pr_language = self.main_language

        self.patches_diff = None
        self.prediction = None
        self.current_readme: Optional[str] = None
        self.repo_name = self.git_provider.repo
        self.branch = self.git_provider.get_pr_branch()

        self.vars = {
            "title": self.git_provider.pr.title,
            "branch": self.branch,
            "description": self.git_provider.get_pr_description(),
            "language": self.main_language,
            "diff": "",
            "extra_instructions": get_settings().pr_readme_generator.get("extra_instructions", ""),
            "repo_name": self.repo_name,
            "current_readme": "",
            "file_list": "",
        }

        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self.vars,
            get_settings().pr_readme_prompt.system,
            get_settings().pr_readme_prompt.user,
        )

    async def run(self):
        try:
            get_logger().info("Generating README.md for PR...")
            if get_settings().config.publish_output:
                self.git_provider.publish_comment("Generating README.md proposal...", is_temporary=True)

            # Fetch current README if exists
            await self._fetch_current_readme()

            # Fetch repo file list
            await self._fetch_file_list()

            get_logger().info("Preparing README prediction...")
            await retry_with_fallback_models(self._prepare_prediction)

            readme_content = self.prediction.strip()
            if not readme_content:
                get_logger().info("No README content generated.")
                return

            if get_settings().config.publish_output:
                self.git_provider.remove_initial_comment()
                self._publish_readme_proposal(readme_content)
        except Exception as e:
            get_logger().error(f"Failed to generate README, error: {e}")

    async def _fetch_current_readme(self):
        try:
            if hasattr(self.git_provider, "_get_repo"):
                repo = self.git_provider._get_repo()
                readme_file = repo.get_contents("README.md", ref=self.branch)
                self.current_readme = readme_file.decoded_content.decode("utf-8")
                self.vars["current_readme"] = self.current_readme
                get_logger().info("Found existing README.md")
            else:
                get_logger().debug("Git provider does not support direct repo content access.")
        except Exception as e:
            get_logger().info(f"No existing README.md found on branch {self.branch}: {e}")
            self.current_readme = None
            self.vars["current_readme"] = ""

    async def _fetch_file_list(self):
        try:
            files = self.git_provider.get_files()
            # Limit to first 100 files to avoid token overflow
            file_names = [f.filename for f in files[:100]]
            self.vars["file_list"] = "\n".join(file_names)
            get_logger().info(f"Fetched {len(file_names)} files for README context")
        except Exception as e:
            get_logger().warning(f"Could not fetch file list: {e}")
            self.vars["file_list"] = ""

    async def _prepare_prediction(self, model: str):
        get_logger().info("Getting PR diff...")
        self.patches_diff = get_pr_diff(
            self.git_provider, self.token_handler, model, add_line_numbers_to_hunks=True, disable_extra_lines=False
        )

        get_logger().info("Getting AI prediction for README...")
        self.prediction = await self._get_prediction(model)

    async def _get_prediction(self, model: str):
        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().pr_readme_prompt.system).render(variables)
        user_prompt = environment.from_string(get_settings().pr_readme_prompt.user).render(variables)
        if get_settings().config.verbosity_level >= 2:
            get_logger().info(f"\nSystem prompt:\n{system_prompt}")
            get_logger().info(f"\nUser prompt:\n{user_prompt}")
        response, finish_reason = await self.ai_handler.chat_completion(
            model=model, temperature=get_settings().config.temperature, system=system_prompt, user=user_prompt
        )
        return response

    def _publish_readme_proposal(self, readme_content: str):
        if self.current_readme:
            header = "## README.md Update Proposal\n\nThe following README.md content is proposed to reflect the changes in this PR:"
        else:
            header = "## README.md Creation Proposal\n\nThis repository does not currently have a README.md. The following content is proposed:"

        # Extract markdown content if wrapped in code block
        if readme_content.startswith("```markdown"):
            readme_content = readme_content[len("```markdown") :]
            if readme_content.endswith("```"):
                readme_content = readme_content[:-3]
        elif readme_content.startswith("```"):
            readme_content = readme_content[len("```") :]
            if readme_content.endswith("```"):
                readme_content = readme_content[:-3]

        body = f"{header}\n\n<details><summary>Proposed README.md</summary>\n\n```markdown\n{readme_content.strip()}\n```\n\n</details>\n\n"
        if not self.current_readme:
            body += "**Action required:** To apply this README, create a file named `README.md` in the repository root with the above content."
        else:
            body += "**Action required:** Review the proposed changes and update `README.md` accordingly."

        self.git_provider.publish_comment(body)
