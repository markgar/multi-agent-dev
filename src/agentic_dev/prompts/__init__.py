"""Agent prompt templates.

Each constant is a format string. Use .format() to interpolate variables
before passing to run_copilot().

Prompts are organized by agent — one module per agent. This __init__
re-exports every constant so existing ``from agentic_dev.prompts import X``
imports continue to work unchanged.
"""

from agentic_dev.prompts.bootstrap import BOOTSTRAP_PROMPT, LOCAL_BOOTSTRAP_PROMPT
from agentic_dev.prompts.builder import BUILDER_PROMPT
from agentic_dev.prompts.copilot_instructions import (
    COPILOT_INSTRUCTIONS_PROMPT,
    COPILOT_INSTRUCTIONS_TEMPLATE,
)
from agentic_dev.prompts.planner import (
    BACKLOG_QUALITY_PROMPT,
    PLANNER_COMPLETENESS_PROMPT,
    PLANNER_INITIAL_PROMPT,
    PLANNER_PROMPT,
    PLANNER_SPLIT_PROMPT,
)
from agentic_dev.prompts.reviewer import (
    REVIEWER_BATCH_PROMPT,
    REVIEWER_COMMIT_PROMPT,
    REVIEWER_MILESTONE_PROMPT,
    REVIEWER_PROMPT,
)
from agentic_dev.prompts.tester import TESTER_MILESTONE_PROMPT, TESTER_PROMPT
from agentic_dev.prompts.validator import VALIDATOR_MILESTONE_PROMPT, VALIDATOR_PLAYWRIGHT_SECTION

__all__ = [
    "BACKLOG_QUALITY_PROMPT",
    "BOOTSTRAP_PROMPT",
    "LOCAL_BOOTSTRAP_PROMPT",
    "BUILDER_PROMPT",
    "COPILOT_INSTRUCTIONS_PROMPT",
    "COPILOT_INSTRUCTIONS_TEMPLATE",
    "PLANNER_COMPLETENESS_PROMPT",
    "PLANNER_INITIAL_PROMPT",
    "PLANNER_PROMPT",
    "PLANNER_SPLIT_PROMPT",
    "REVIEWER_BATCH_PROMPT",
    "REVIEWER_COMMIT_PROMPT",
    "REVIEWER_MILESTONE_PROMPT",
    "REVIEWER_PROMPT",
    "TESTER_MILESTONE_PROMPT",
    "TESTER_PROMPT",
    "VALIDATOR_MILESTONE_PROMPT",
    "VALIDATOR_PLAYWRIGHT_SECTION",
]
