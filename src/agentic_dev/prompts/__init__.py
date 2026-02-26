"""Agent prompt templates.

Each constant is a format string. Use .format() to interpolate variables
before passing to run_copilot().

Prompts are organized by agent — one module per agent. This __init__
re-exports every constant so existing ``from agentic_dev.prompts import X``
imports continue to work unchanged.
"""

from agentic_dev.prompts.bootstrap import BOOTSTRAP_PROMPT
from agentic_dev.prompts.builder import (
    BUILDER_FIX_ONLY_PROMPT,
    BUILDER_ISSUE_FIXING_SECTION,
    BUILDER_PROMPT,
)
from agentic_dev.prompts.copilot_instructions import (
    COPILOT_INSTRUCTIONS_PROMPT,
    COPILOT_INSTRUCTIONS_TEMPLATE,
)
from agentic_dev.prompts.planner import (
    BACKLOG_ORDERING_PROMPT,
    BACKLOG_QUALITY_PROMPT,
    PLANNER_COMPLETENESS_PROMPT,
    PLANNER_INITIAL_PROMPT,
    PLANNER_JOURNEYS_PROMPT,
    PLANNER_PROMPT,
    PLANNER_SPLIT_PROMPT,
)
from agentic_dev.prompts.reviewer import (
    REVIEWER_BRANCH_BATCH_PROMPT,
    REVIEWER_BRANCH_COMMIT_PROMPT,
    REVIEWER_MILESTONE_PROMPT,
)
from agentic_dev.prompts.tester import TESTER_MILESTONE_PROMPT
from agentic_dev.prompts.validator import (
    VALIDATOR_JOURNEY_RESULTS_TAGS,
    VALIDATOR_JOURNEY_SECTION,
    VALIDATOR_LEGACY_RESULTS_TAGS,
    VALIDATOR_LEGACY_SCOPE,
    VALIDATOR_MILESTONE_PROMPT,
    VALIDATOR_PLAYWRIGHT_SECTION,
    VALIDATOR_PLAYWRIGHT_TRACE_SECTION,
)

__all__ = [
    "BACKLOG_ORDERING_PROMPT",
    "BACKLOG_QUALITY_PROMPT",
    "BOOTSTRAP_PROMPT",
    "BUILDER_FIX_ONLY_PROMPT",
    "BUILDER_ISSUE_FIXING_SECTION",
    "BUILDER_PROMPT",
    "COPILOT_INSTRUCTIONS_PROMPT",
    "COPILOT_INSTRUCTIONS_TEMPLATE",
    "PLANNER_COMPLETENESS_PROMPT",
    "PLANNER_INITIAL_PROMPT",
    "PLANNER_JOURNEYS_PROMPT",
    "PLANNER_PROMPT",
    "PLANNER_SPLIT_PROMPT",
    "REVIEWER_BRANCH_BATCH_PROMPT",
    "REVIEWER_BRANCH_COMMIT_PROMPT",
    "REVIEWER_MILESTONE_PROMPT",
    "TESTER_MILESTONE_PROMPT",
    "VALIDATOR_JOURNEY_RESULTS_TAGS",
    "VALIDATOR_JOURNEY_SECTION",
    "VALIDATOR_LEGACY_RESULTS_TAGS",
    "VALIDATOR_LEGACY_SCOPE",
    "VALIDATOR_MILESTONE_PROMPT",
    "VALIDATOR_PLAYWRIGHT_SECTION",
    "VALIDATOR_PLAYWRIGHT_TRACE_SECTION",
]
