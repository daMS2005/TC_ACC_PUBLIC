from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..providers.render_checkpoints import RENDERER_SOURCE_PATHS
from ..workflow_contracts import Department, ReviewGate

STAGE_CONTRACT_VERSION = "2026-07-28-stage-registry.3"


class StageKind(StrEnum):
    MODEL_AGENT = "model_agent"
    DETERMINISTIC_STAGE = "deterministic_stage"
    TOOL_WORKER = "tool_worker"
    WORKFLOW = "workflow"


class WorkflowStateField(StrEnum):
    LEAD = "lead"
    DOSSIER = "dossier"
    CLAIM_LEDGER = "claim_ledger"
    COURT_RECORD_RESOURCE_LEDGER = (
        "court_record_resource_ledger"
    )
    NEWS_INTERVIEW_RESOURCE_LEDGER = (
        "news_interview_resource_ledger"
    )
    TIMELINE_STORY = "timeline_story"
    SENSITIVITY_REVIEW = "sensitivity_review"
    SCRIPT_PACKAGE = "script_package"
    PACING_REVIEW = "pacing_review"
    SCENE_PLAN = "scene_plan"
    ASSET_PLAN = "asset_plan"
    ASSET_MANIFEST = "asset_manifest"
    ASSET_PEOPLE_IMAGE_RESEARCH_PLAN = (
        "asset_people_image_research_plan"
    )
    ASSET_COURT_RECORD_RESEARCH_PLAN = (
        "asset_court_record_research_plan"
    )
    ASSET_NEWS_INTERVIEW_RESEARCH_PLAN = (
        "asset_news_interview_research_plan"
    )
    ASSET_LOCATION_MAP_RESEARCH_PLAN = (
        "asset_location_map_research_plan"
    )
    ASSET_VALIDATION_REPORT = "asset_validation_report"
    ASSET_EDITORIAL_INDEX = "asset_editorial_index"
    SOURCE_RESEARCH_QUERIES = "source_research_queries"
    ANIMATION_PLAN = "animation_plan"
    ENHANCED_ANIMATION_PLAN = "enhanced_animation_plan"
    SOUND_DESIGN_PLAN = "sound_design_plan"
    SOUND_LIBRARY_FINGERPRINT = "sound_library_fingerprint"
    VOICE_MANIFEST = "voice_manifest"
    VOICE_TIMING_SUMMARY = "voice_timing_summary"
    RENDER_MANIFEST = "render_manifest"
    METADATA_PACKAGE = "metadata_package"
    DELIVERY_MANIFEST = "delivery_manifest"
    ISSUE_LEDGER = "issue_ledger"
    COORDINATION = "coordination"
    STORY_DEVELOPMENT = "v2_story_development"
    CREATIVE_DIRECTION = "v2_creative_direction"
    PREPRODUCTION = "v2_preproduction"
    EDITORIAL_CONTEXT = "v2_editorial_context"
    VIDEO_ENHANCEMENT = "v2_video_enhancement"
    SHOWRUNNER_PREPRODUCTION = "showrunner_preproduction"
    SHOWRUNNER_EDIT = "showrunner_edit"
    RUN_CONTROL = "run_control"


class StageDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    contract_version: str = Field(min_length=1)
    kind: StageKind
    owner: Department
    dependencies: tuple[str, ...] = ()
    state_inputs: tuple[WorkflowStateField, ...] = ()
    state_outputs: tuple[WorkflowStateField, ...] = ()
    permitted_state_mutations: tuple[WorkflowStateField, ...] = ()
    fingerprint_excluded_state_inputs: tuple[
        WorkflowStateField, ...
    ] = ()
    fingerprint_state_after_execution: bool = False
    coordination_inputs: tuple[Department, ...] = ()
    coordination_gates: tuple[ReviewGate, ...] = ()
    artifact_outputs: tuple[str, ...] = ()
    resume_fingerprint_artifact_outputs: tuple[str, ...] = ()
    setting_fields: tuple[str, ...] = ()
    source_fingerprint_paths: tuple[str, ...] = ()
    provider_requirements: tuple[str, ...] = ()
    applicability: Literal["always"] = "always"


def _stage(
    stage_id: str,
    kind: StageKind,
    owner: Department,
    *,
    dependencies: tuple[str, ...] = (),
    state_inputs: tuple[WorkflowStateField | str, ...] = (),
    state_outputs: tuple[WorkflowStateField | str, ...] = (),
    permitted_state_mutations: tuple[
        WorkflowStateField | str,
        ...,
    ] = (),
    fingerprint_excluded_state_inputs: tuple[
        WorkflowStateField | str,
        ...,
    ] = (),
    fingerprint_state_after_execution: bool = False,
    coordination_inputs: tuple[Department, ...] = (),
    coordination_gates: tuple[ReviewGate, ...] = (
        ReviewGate.PREPRODUCTION,
    ),
    artifact_outputs: tuple[str, ...] = (),
    resume_fingerprint_artifact_outputs: tuple[str, ...] = (),
    setting_fields: tuple[str, ...] = (),
    source_fingerprint_paths: tuple[str, ...] = (),
    provider_requirements: tuple[str, ...] = (),
    contract_version: str = STAGE_CONTRACT_VERSION,
) -> StageDefinition:
    return StageDefinition(
        stage_id=stage_id,
        contract_version=contract_version,
        kind=kind,
        owner=owner,
        dependencies=dependencies,
        state_inputs=state_inputs,
        state_outputs=state_outputs,
        permitted_state_mutations=permitted_state_mutations,
        fingerprint_excluded_state_inputs=(
            fingerprint_excluded_state_inputs
        ),
        fingerprint_state_after_execution=(
            fingerprint_state_after_execution
        ),
        coordination_inputs=coordination_inputs,
        coordination_gates=coordination_gates,
        artifact_outputs=artifact_outputs,
        resume_fingerprint_artifact_outputs=(
            resume_fingerprint_artifact_outputs
        ),
        setting_fields=setting_fields,
        source_fingerprint_paths=source_fingerprint_paths,
        provider_requirements=provider_requirements,
    )


STAGE_DEFINITIONS = (
    _stage(
        "source_intake",
        StageKind.DETERMINISTIC_STAGE,
        Department.PRODUCTION_CONTROL,
        state_inputs=("lead",),
        artifact_outputs=("source_intake",),
    ),
    _stage(
        "research_collection",
        StageKind.WORKFLOW,
        Department.RESEARCH,
        contract_version=(
            "2026-08-15-shared-research-notebook.1"
        ),
        dependencies=("source_intake",),
        state_inputs=("lead",),
        artifact_outputs=(
            "research_pool",
            "research_loop_status",
            "research_gate",
        ),
        # Compare only what this stage is authoritative for, the same trade
        # map_production makes with the shared asset manifest.
        #
        # research_pool.json is the case notebook, not this stage's private
        # output: research_expand writes into it, the transcript queue used to,
        # and case_media now lands its acquired-transcript notes there because
        # its Gemini-discovered sources do not exist until after research has
        # run. With research_pool in the resume fingerprint, that amendment
        # changed the file after this stage recorded its hash, so a resumed run
        # found research_collection "changed" and re-ran the entire paid
        # research loop -- and, because a resume recomputes output_fingerprint
        # from the files on disk, the change propagated into case_media's input
        # fingerprint and re-bought the Gemini inspections too, which amended
        # the pool again. It never converged.
        #
        # research_gate.json is the honest fingerprint of research's own work:
        # it carries pool_note_count and the final coverage measured at the
        # moment this stage finished, so anything research actually did
        # differently moves it. Deletion of the pool is still caught -- resume
        # separately requires every declared output to exist.
        resume_fingerprint_artifact_outputs=(
            "research_loop_status",
            "research_gate",
        ),
        setting_fields=(
            "research_model",
            "subagent_model",
            "search_provider",
            "wikipedia_enabled",
            "wikipedia_language",
            "research_pool_max_web_queries",
            "research_pool_max_youtube_queries",
            "research_pool_results_per_query",
            "youtube_search_delay_seconds",
            "youtube_search_limit",
            "research_loop_max_iterations",
            "research_loop_max_questions_per_pass",
            "research_loop_min_distinct_sources",
            "research_loop_min_notes",
            "research_loop_run_transcripts",
            "research_loop_stop_on_no_new_notes",
            "research_loop_transcript_candidates_per_pass",
            "youtube_transcript_provider",
            "youtube_transcript_delay_seconds",
            "serpapi_youtube_transcript_language_code",
            "serpapi_transcript_max_calls_per_run",
            "serpapi_transcript_monthly_budget",
        ),
        provider_requirements=("text", "web_search"),
        coordination_inputs=(Department.RESEARCH,),
    ),
    _stage(
        "case_media",
        StageKind.TOOL_WORKER,
        Department.RESEARCH,
        contract_version=(
            "2026-08-14-gemini-native-case-visual-media.2"
        ),
        dependencies=("research_collection",),
        state_inputs=("lead",),
        artifact_outputs=(
            "youtube_transcript_queue",
            "youtube_research_transcripts",
            "gemini_youtube_case_media_sources",
            "asset_transcript_leads",
            "youtube_clip_frame_manifest",
        ),
        setting_fields=(
            "script_model",
            "subagent_model",
            "youtube_case_media_fetch_enabled",
            "youtube_transcript_provider",
            "youtube_transcript_delay_seconds",
            "serpapi_youtube_transcript_language_code",
            "serpapi_transcript_max_calls_per_run",
            "serpapi_transcript_monthly_budget",
            "youtube_clip_frame_max_leads",
            "youtube_clip_frame_count_per_lead",
            "youtube_clip_frame_max_window_seconds",
            "youtube_visual_trim_sample_interval_seconds",
            "youtube_visual_trim_boundary_tolerance_seconds",
            "youtube_visual_trim_max_boundary_iterations",
            "youtube_visual_trim_min_clip_seconds",
            "youtube_visual_trim_interior_sample_seconds",
        ),
        provider_requirements=(
            "text",
            "vision",
            "video_download",
            "ffmpeg",
            "web_search",
        ),
    ),

    # ... 26 further stage definitions omitted from this public excerpt.
    #
    # The full registry declares all 29 stages across 6 departments. What is
    # shown above is the shape every one of them takes: its dependencies, the
    # state it may read and the state it is *permitted* to mutate, the
    # artifacts it must produce, the config keys and source paths that
    # invalidate its cached result, and the external services it requires.
    #
    # Declaring this rather than implying it from call order is what lets the
    # control plane answer questions about a run without executing it.
)
