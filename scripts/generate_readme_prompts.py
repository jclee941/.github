from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReadmeTemplateContract:
    language_order: str
    first_viewport: tuple[str, ...]
    google_sections: tuple[str, ...]
    markdown_rules: tuple[str, ...]
    cjk_rule: str


README_TEMPLATE_CONTRACT = ReadmeTemplateContract(
    language_order="Korean summary first; English as secondary text",
    first_viewport=(
        "short Korean summary",
        "quick-glance status table",
        "compact flow summary",
    ),
    google_sections=(
        "Purpose / Package Contents",
        "Status",
        "First Files to Read",
        "API or Entry Points",
        "Quickstart / Usage",
        "Maintainers / Points of Contact",
        "Further Documentation",
    ),
    markdown_rules=(
        "repository-relative links for local docs and assets",
        "blank line before each table",
        "simple pipe syntax",
    ),
    cjk_rule=(
        "avoid splitting Korean particles, endings, short subject-predicate phrases, "
        "or mixed Korean/English parentheticals"
    ),
)


def readme_template_contract() -> ReadmeTemplateContract:
    return README_TEMPLATE_CONTRACT


def _korean_first_visual_contract() -> str:
    contract = readme_template_contract()
    return (
        f"Korean-first output: put the {contract.language_order}, not a competing duplicate paragraph. "
        "Design the first viewport for fast scanning: after the title and badges, include a "
        f"{contract.first_viewport[0]} first, then a {contract.first_viewport[1]} and a {contract.first_viewport[2]} "
        "that explain what runs, who owns it, and what command or endpoint an operator uses next. "
        "Use concise headings, Markdown tables, and short bullets instead of long bilingual blocks. "
        f"Keep CJK line breaks natural: {contract.cjk_rule} across awkward lines. "
    )


def _readme_quality_contract() -> str:
    contract = readme_template_contract()
    google_sections = ", ".join(contract.google_sections[:-1]) + f", and {contract.google_sections[-1]}"
    markdown_rules = ", ".join(contract.markdown_rules[:-1]) + f", and {contract.markdown_rules[-1]}"
    return (
        "Use a Google-style README Template adapted for this repository: "
        f"{google_sections}. "
        "Cover README basics explicitly: what the project does, why it is useful, "
        "what users can do with it, how to get started, whether it is deprecated or production-ready, "
        "where to get help, who maintains it, and where to read more detailed docs. "
        f"Use {markdown_rules}; avoid absolute GitHub blob URLs for local docs. "
    )


def automation_source_system_prompt() -> str:
    return "".join(
        (
            "You are a technical writer bot specialized in GitHub automation documentation. ",
            "Generate a comprehensive, professional README.md in Korean and English (bilingual). ",
            _korean_first_visual_contract(),
            _readme_quality_contract(),
            "Use Markdown. Structure: title, badges, overview, features, architecture, ",
            "jclee-bot automation surfaces, Go tools, quick start, local development, ",
            "commands reference, and contribution guide. ",
            "Be specific about App-owned automation surfaces and Go tool names. ",
            "Use operator-scannable status tables for automation capabilities, health checks, ",
            "required permissions, and ownership boundaries. ",
            "Include an Observability section that explains structured logs, ELK/Filebeat log ",
            "shipping, health workflows, and the metrics or job summaries operators inspect. ",
            "Do NOT render a GitHub workflow inventory table and do NOT list linked workflow files as rows; ",
            "workflow files are implementation triggers, not the automation source of truth. ",
            "Describe mutating automation as owned by jclee-bot, and include the exact marker ",
            "'jclee-bot에의해자동화됨' for issue automation behavior. ",
            "For the README architecture section, use compact Markdown tables and numbered ",
            "request-flow steps instead of Mermaid or ASCII/box-drawing diagrams. ",
            "Detailed architecture docs may use GitHub-native Mermaid, but README.md must ",
            "remain readable even when diagram rendering is unavailable. ",
            "For the repository structure tree, reflect the ACTUAL top-level layout provided ",
            "below; never invent directories such as _bot-scripts/ (that name only ever appears ",
            "as a transient CI checkout path, not a real directory). ",
            "NEVER include hardcoded private/internal IP addresses (RFC1918: 192.168.x.x, ",
            "10.x.x.x, 172.16-31.x.x) or LXC container numbers; use placeholders like ",
            "<homelab-host> / <homelab-elk> and the public endpoint https://cliproxy.jclee.me/v1 instead. ",
            "Do NOT use bold/emphasis text as a substitute for a heading (markdownlint MD036); ",
            "use real '#' headings. ",
            "Current README-gen primary model: minimax-m3 (fallback: gpt-5.5 via CLIProxyAPI). ",
            "Do NOT invent GitHub repository URLs: never link to non-existent repos such as ",
            "github.com/jclee941/CLIProxyAPI or retired/guessed repository slugs. For external ",
            "links use only qodo-ai/pr-agent, cliproxy.jclee.me, and bot.jclee.me. ",
        )
    )


def product_readme_system_prompt() -> str:
    return "".join(
        (
            "You are a technical writer for application, CLI, library, and tool repositories. ",
            "Generate a comprehensive, professional README.md in Korean and English (bilingual). ",
            _korean_first_visual_contract(),
            _readme_quality_contract(),
            "Document the repository's actual product: what the app/tool/library does, who uses it, ",
            "its entry points, architecture, configuration, commands, testing, and local development. ",
            "Use Markdown. Prefer this structure when applicable: title, overview, features, ",
            "architecture, quick start, configuration, commands reference, local development, testing, ",
            "contribution guide, and license. ",
            "Prefer scannable Markdown tables for runtime status, permissions, and operator-facing ",
            "observability when the product exposes them. ",
            "Do NOT add jclee-bot automation surfaces, issue automation, PR automation, release ",
            "automation, downstream health checks, workflow/event-adapter policy, README generation ",
            "metadata, model names, bot control-plane URLs, or the marker 'jclee-bot에의해자동화됨'. ",
            "Do NOT add sections named 'jclee-bot Automation', 'Automation Surfaces', ",
            "'README Generation', 'Go Automation Tools', or similar repository-maintenance boilerplate ",
            "unless this repository's own source code implements that as the product. ",
            "If the existing README contains jclee-bot, qodo-ai/pr-agent, cliproxy, bot.jclee.me, ",
            "workflow adapter, README generation, or automation policy text, treat that content as ",
            "stale boilerplate from a previous generator run and remove it unless the product source ",
            "files independently prove it belongs. ",
            "Workflow files, AGENTS.md instructions, badges, and bot-owned PR metadata are context for ",
            "safe generation only; do not present them as user-facing product features. ",
            "For the README architecture section, prefer compact Markdown tables and numbered ",
            "request-flow steps. Do NOT hand-draw ASCII/box-drawing diagrams. ",
            "Use Mermaid only in detailed documentation files, not in generated README landing pages. ",
            "For the repository structure tree, reflect the ACTUAL top-level layout provided below; ",
            "never invent directories. ",
            "NEVER include hardcoded private/internal IP addresses (RFC1918: 192.168.x.x, 10.x.x.x, ",
            "172.16-31.x.x) or LXC container numbers; use placeholders only when the actual product ",
            "needs them. ",
            "Do NOT use bold/emphasis text as a substitute for a heading (markdownlint MD036); use ",
            "real '#' headings. ",
            "Do NOT invent GitHub repository URLs. ",
        )
    )
