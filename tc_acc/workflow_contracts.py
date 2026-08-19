from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import utc_now_iso

WORKFLOW_CONTRACT_VERSION = "2026-07-28-studio-coordination.1"


class Department(StrEnum):
    PRODUCTION_CONTROL = "production_control"
    SHOWRUNNER = "showrunner"
    RESEARCH = "research"
    STORY = "story"
    SCRIPT_AND_PERFORMANCE = "script_and_performance"
    CREATIVE_DIRECTION = "creative_direction"
    ASSETS = "assets"
    SOUND = "sound"
    ANIMATION = "animation"
    REPAIR = "repair"
    RENDER = "render"
    PUBLISHING = "publishing"


class IssueCategory(StrEnum):
    TECHNICAL_INVALID = "technical_invalid"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    QUALITY_BELOW_FLOOR = "quality_below_floor"
    MISSING_EVIDENCE = "missing_evidence"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    MISSING_VISUAL_COVERAGE = "missing_visual_coverage"
    PERFORMANCE_FAILURE = "performance_failure"
    CREATIVE_DEAD_END = "creative_dead_end"
    NO_PROGRESS = "no_progress"
    POLICY_BLOCK = "policy_block"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class IssueStatus(StrEnum):
    OPEN = "open"
    ROUTED = "routed"
    ADDRESSED = "addressed"
    RESOLVED = "resolved"


# ... the remainder of this module -- the issue records themselves, routing,
# and the per-stage contracts that consume them -- is omitted from this
# public excerpt. The vocabulary above is the part worth reading: failure in
# this system is a typed, queryable record with a lifecycle, not an exception.
