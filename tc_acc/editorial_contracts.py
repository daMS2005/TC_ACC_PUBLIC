from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from .studio.contracts import (
    ArtifactIdentity,
    GlobalAssetLedger,
)


class EpisodeCharter(ArtifactIdentity):
    audience_promise: str = ""
    central_question: str = ""
    documentary_thesis: str = ""
    format: str = ""
    quality_floor: list[str] = Field(default_factory=list)
    factual_constraints: list[str] = Field(default_factory=list)
    sensitivity_constraints: list[str] = Field(default_factory=list)


class NarrativeBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    beat_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    narrative_function: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    depends_on_beat_ids: list[str] = Field(default_factory=list)
    opens_questions: list[str] = Field(default_factory=list)
    resolves_questions: list[str] = Field(default_factory=list)
    factual_guardrails: list[str] = Field(default_factory=list)


class NarrativeEdge(BaseModel):
    """An edge between two beats.

    Models reach for the obvious short names when describing a graph, and one
    returning ``to`` instead of ``to_beat_id`` failed the stage after two
    attempts. The endpoints are unambiguous, so the shorter spellings are
    accepted rather than treated as a different field: rejecting a graph that
    is correct in substance over a synonym makes the pipeline fragile to a
    change of model.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_beat_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices(
            "from_beat_id", "from", "source", "source_beat_id"
        ),
    )
    to_beat_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices(
            "to_beat_id", "to", "target", "target_beat_id"
        ),
    )
    relation: str = Field(
        min_length=1,
        validation_alias=AliasChoices("relation", "type", "kind", "label"),
    )


class NarrativeGraph(ArtifactIdentity):
    beats: list[NarrativeBeat] = Field(min_length=1)
    edges: list[NarrativeEdge] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> NarrativeGraph:
        beat_ids = [beat.beat_id for beat in self.beats]
        if len(beat_ids) != len(set(beat_ids)):
            raise ValueError("narrative beat IDs must be unique")
        known = set(beat_ids)
        for beat in self.beats:
            unknown = set(beat.depends_on_beat_ids) - known
            if unknown:
                raise ValueError(
                    f"{beat.beat_id} depends on unknown beats "
                    f"{sorted(unknown)}"
                )
        for edge in self.edges:
            if (
                edge.from_beat_id not in known
                or edge.to_beat_id not in known
            ):
                raise ValueError(
                    "narrative edge references an unknown beat"
                )
        return self


class StoryArc(ArtifactIdentity):
    thesis: str = ""
    central_question: str = ""
    structure_rationale: str = ""
    ordered_beat_ids: list[str] = Field(default_factory=list)
    hook_strategy: str = ""
    act_progression: list[str] = Field(default_factory=list)
    midpoint_turn: str = ""
    climax_strategy: str = ""
    ending_strategy: str = ""


class ViewerState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    known_claim_ids: list[str] = Field(default_factory=list)
    working_beliefs: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    emotional_posture: str = ""


class ViewerStateIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    working_beliefs: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    emotional_posture: str = ""


class InformationSequenceObjective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_id: str = Field(min_length=1)
    label: str = ""
    start_cue_index: int = Field(ge=0)
    end_cue_index: int = Field(ge=0)
    beat_ids: list[str] = Field(default_factory=list)
    objective: str = Field(min_length=1)
    viewer_state_after: ViewerStateIntent
    active_question: str = ""
    information_introduced_claim_ids: list[str] = Field(
        default_factory=list
    )
    information_withheld_claim_ids: list[str] = Field(
        default_factory=list
    )
    emotional_function: str = ""
    reveal_or_payoff: str = ""
    source_requirement_claim_ids: list[str] = Field(
        default_factory=list
    )
    visual_obligations: list[str] = Field(default_factory=list)
    tempo: str = ""
    transition_purpose: str = ""

    @model_validator(mode="after")
    def validate_cue_range(self) -> InformationSequenceObjective:
        if self.end_cue_index < self.start_cue_index:
            raise ValueError(
                "sequence end cue cannot precede its start cue"
            )
        return self


class SequenceObjective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_id: str = Field(min_length=1)
    label: str = ""
    start_cue_index: int = Field(ge=0)
    end_cue_index: int = Field(ge=0)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    cue_count: int | None = Field(default=None, ge=0)
    narration_excerpt: str = ""
    objective: str = Field(min_length=1)
    beat_ids: list[str] = Field(default_factory=list)
    viewer_state_before: ViewerState = Field(
        default_factory=ViewerState
    )
    viewer_state_after: ViewerState = Field(
        default_factory=ViewerState
    )
    active_question: str = ""
    information_introduced_claim_ids: list[str] = Field(
        default_factory=list
    )
    information_withheld_claim_ids: list[str] = Field(
        default_factory=list
    )
    emotional_function: str = ""
    reveal_or_payoff: str = ""
    source_requirement_claim_ids: list[str] = Field(
        default_factory=list
    )
    visual_obligations: list[str] = Field(default_factory=list)
    tempo: str = ""
    transition_purpose: str = ""

    @model_validator(mode="after")
    def validate_timing(self) -> SequenceObjective:
        if self.end_cue_index < self.start_cue_index:
            raise ValueError(
                "sequence end cue cannot precede its start cue"
            )
        if (
            self.start_seconds is not None
            and self.end_seconds is not None
            and self.end_seconds <= self.start_seconds
        ):
            raise ValueError(
                "sequence end time must follow its start time"
            )
        return self


class SequenceObjectivesArtifact(ArtifactIdentity):
    sequences: list[SequenceObjective] = Field(min_length=1)


class ViewerKnowledgeTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_claim_ids: list[str] = Field(default_factory=list)
    withheld_claim_ids: list[str] = Field(default_factory=list)
    active_question: str = ""
    reveal_or_payoff: str = ""


class ViewerKnowledgeState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    before: ViewerState
    transition: ViewerKnowledgeTransition
    after: ViewerState


class ViewerKnowledgeTimeline(ArtifactIdentity):
    states: list[ViewerKnowledgeState] = Field(default_factory=list)


class ScriptSequenceObjective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_id: str
    objective: str
    beat_ids: list[str] = Field(default_factory=list)
    active_question: str = ""
    reveal_or_payoff: str = ""
    tempo: str = ""
    visual_communication_needs: list[str] = Field(
        default_factory=list
    )


class ScriptBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_and_tone: str = ""
    opening_requirements: list[str] = Field(default_factory=list)
    sequence_objectives: list[ScriptSequenceObjective] = Field(
        min_length=1
    )
    prohibited_patterns: list[str] = Field(default_factory=list)


class StoryDevelopmentBundle(ArtifactIdentity):
    episode_charter: EpisodeCharter
    narrative_graph: NarrativeGraph
    story_arc: StoryArc
    script_brief: ScriptBrief


class InformationStoryBundle(ArtifactIdentity):
    episode_charter: EpisodeCharter
    narrative_graph: NarrativeGraph
    story_arc: StoryArc
    sequence_objectives: list[SequenceObjective] = Field(
        min_length=1
    )
    viewer_knowledge_timeline: list[
        ViewerKnowledgeState
    ] = Field(default_factory=list)


class InformationStoryStructureBundle(ArtifactIdentity):
    episode_charter: EpisodeCharter
    narrative_graph: NarrativeGraph
    story_arc: StoryArc


class InformationSequenceFlowBundle(ArtifactIdentity):
    opening_viewer_state: ViewerStateIntent = Field(
        default_factory=ViewerStateIntent
    )
    sequence_objectives: list[InformationSequenceObjective] = Field(
        min_length=1
    )


class CreativeEditorialBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience_promise: str = ""
    tone: str = ""
    evidence_hierarchy: list[str] = Field(default_factory=list)
    map_treatment: str = ""
    text_philosophy: str = ""
    motion_philosophy: str = ""
    case_reuse_philosophy: str = ""
    stock_reuse_philosophy: str = ""


class VisualLanguage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motifs: list[str] = Field(default_factory=list)
    case_material_treatments: list[str] = Field(
        default_factory=list
    )
    stock_treatments: list[str] = Field(default_factory=list)
    graphic_treatments: list[str] = Field(default_factory=list)
    prohibited_cliches: list[str] = Field(default_factory=list)


class EditingGrammar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hook_rhythm: str = ""
    body_rhythm: str = ""
    evidence_readability: str = ""
    transitions: list[str] = Field(default_factory=list)
    supporting_text_rules: list[str] = Field(
        default_factory=list
    )


class TimedCreativeSequence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_id: str = Field(min_length=1)
    label: str = ""
    start_cue_index: int = Field(ge=0)
    end_cue_index: int = Field(ge=0)
    objective: str = Field(min_length=1)
    visual_obligations: list[str] = Field(min_length=1)
    case_asset_priority: list[str] = Field(default_factory=list)
    stock_support_intents: list[str] = Field(default_factory=list)
    map_purpose: str = ""
    map_truth_constraint: str = ""
    rhythm_note: str = ""
    text_opportunities: list[str] = Field(default_factory=list)
    forbidden_implications: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sequence(self) -> TimedCreativeSequence:
        if self.end_cue_index < self.start_cue_index:
            raise ValueError(
                "timed sequence end cue precedes start cue"
            )
        if self.map_purpose and not self.map_truth_constraint:
            raise ValueError(
                "map purpose requires a map truth constraint"
            )
        return self


class AssetAcquisitionStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_web_query_strategy: list[str] = Field(
        default_factory=list
    )
    stock_video_query_strategy: list[str] = Field(
        default_factory=list
    )
    map_strategy: list[str] = Field(default_factory=list)
    coverage_completion_test: list[str] = Field(
        default_factory=list
    )


class CreativeDirectionBundle(ArtifactIdentity):
    editorial_brief: CreativeEditorialBrief
    visual_language: VisualLanguage
    editing_grammar: EditingGrammar
    timed_sequences: list[TimedCreativeSequence] = Field(
        min_length=1
    )
    asset_acquisition_strategy: AssetAcquisitionStrategy


class PreproductionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_development: StoryDevelopmentBundle
    creative_acquisition_brief: CreativeDirectionBundle


class EditorialSequenceNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_id: str
    creative_intent: str = ""
    rhythm_note: str = ""
    motif_or_treatment: str = ""


class EditorialBrief(ArtifactIdentity):
    thesis: str = ""
    audience_promise: str = ""
    tone: str = ""
    emotional_range: list[str] = Field(default_factory=list)
    point_of_view: str = ""
    visual_hierarchy: str = ""
    evidence_treatment: str = ""
    map_treatment: str = ""
    text_philosophy: str = ""
    motion_philosophy: str = ""
    sound_philosophy: str = ""
    prohibited_cliches: list[str] = Field(default_factory=list)
    sequence_notes: list[EditorialSequenceNote] = Field(
        default_factory=list
    )


class VisualObligation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obligation_id: str = Field(min_length=1)
    sequence_id: str = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)
    narration_intent: str = ""
    factual_function: str = ""
    emotional_function: str = ""
    preferred_visual_strategy: str = ""
    recommended_asset_ids: list[str] = Field(default_factory=list)
    acceptable_support_asset_ids: list[str] = Field(
        default_factory=list
    )
    forbidden_implications: list[str] = Field(default_factory=list)
    map_purpose: str = ""
    map_truth_constraint: str = ""
    priority: str = ""
    uniqueness_goal: str = ""
    unresolved_gap: bool = False
    gap_reason: str = ""

    @model_validator(mode="after")
    def validate_gap_and_map(self) -> VisualObligation:
        if self.unresolved_gap and not self.gap_reason:
            raise ValueError(
                "unresolved visual obligations require a reason"
            )
        if self.map_purpose and not self.map_truth_constraint:
            raise ValueError(
                "map purpose requires a truth constraint"
            )
        return self


class VisualCoverageGraph(ArtifactIdentity):
    obligations: list[VisualObligation] = Field(default_factory=list)
    global_rhythm_notes: list[str] = Field(default_factory=list)
    coverage_risks: list[str] = Field(default_factory=list)


class CreativeCoverageBundle(ArtifactIdentity):
    editorial_brief: EditorialBrief
    visual_coverage_graph: VisualCoverageGraph


class DirectorEpisodeObjective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thesis: str = ""
    audience_promise: str = ""
    central_question: str = ""
    hook_strategy: str = ""
    ending_strategy: str = ""


class DirectorDepartmentNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: str = ""
    point_of_view: str = ""
    visual_hierarchy: str = ""
    evidence_treatment: str = ""
    map_treatment: str = ""
    text_philosophy: str = ""
    motion_philosophy: str = ""
    sound_philosophy: str = ""
    prohibited_cliches: list[str] = Field(default_factory=list)


class DirectorNotes(ArtifactIdentity):
    episode_objective: DirectorEpisodeObjective
    department_notes: DirectorDepartmentNotes
    sequence_notes: list[EditorialSequenceNote] = Field(
        default_factory=list
    )


class ProductionTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_type: str
    sequence_id: str
    status: str
    priority: str
    objective: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    depends_on: list[str] = Field(default_factory=list)
    visual_obligation_ids: list[str] = Field(default_factory=list)
    blocking_obligation_ids: list[str] = Field(
        default_factory=list
    )
    next_output: str = ""


class ProductionGate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_id: str
    status: str
    blocking: bool | None = None
    actual_minutes: float | None = Field(default=None, ge=0)
    target_min_minutes: float | None = Field(default=None, ge=0)
    target_max_minutes: float | None = Field(default=None, ge=0)
    preference_status: str = ""
    editorial_note: str = ""
    blocked_sequence_count: int | None = Field(default=None, ge=0)


class ProductionPlan(ArtifactIdentity):
    status: str
    autonomy_mode: Literal["fully_autonomous"]
    execution_boundary: str
    gates: list[ProductionGate] = Field(default_factory=list)
    tasks: list[ProductionTask] = Field(default_factory=list)


class EditorialContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_charter: EpisodeCharter
    narrative_graph: NarrativeGraph
    story_arc: StoryArc
    sequence_objectives: SequenceObjectivesArtifact
    viewer_knowledge_timeline: ViewerKnowledgeTimeline
    editorial_brief: EditorialBrief
    director_notes: DirectorNotes
    visual_coverage_graph: VisualCoverageGraph
    global_asset_ledger: GlobalAssetLedger
    production_plan: ProductionPlan

    def prompt_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)


class VideoEnhancementRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str
    creative_summary: str
    revision_count: int = Field(ge=0)
    plan_path: str
    canonical_animation_plan_path: str
    selector_animation_plan_path: str


class ScriptQualityScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factual_grounding: float = Field(ge=0, le=100)
    hook: float = Field(ge=0, le=100)
    clarity: float = Field(ge=0, le=100)
    curiosity: float = Field(ge=0, le=100)
    reveal_timing: float = Field(ge=0, le=100)
    emotional_engagement: float = Field(ge=0, le=100)
    pacing: float = Field(ge=0, le=100)
    ending: float = Field(ge=0, le=100)


class ScriptBlockerCategory(StrEnum):
    FACTUAL_INTEGRITY = "factual_integrity"
    SENSITIVITY = "sensitivity"
    NARRATION_INTEGRITY = "narration_integrity"
    EDITORIAL_QUALITY = "editorial_quality"


class ScriptBlockingIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    category: ScriptBlockerCategory
    reason: str = Field(min_length=1)
    viewer_effect: str = Field(min_length=1)
    required_outcome: str = Field(min_length=1)
    exact_passages: list[str] = Field(default_factory=list)
    related_claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence(self) -> ScriptBlockingIssue:
        if (
            self.code == "unsupported_factual_framing"
            and not self.exact_passages
        ):
            raise ValueError(
                "unsupported factual framing requires an exact passage"
            )
        if (
            self.code == "unsupported_factual_framing"
            and self.category
            != ScriptBlockerCategory.FACTUAL_INTEGRITY
        ):
            raise ValueError(
                "unsupported factual framing must be categorized as "
                "factual_integrity"
            )
        return self


class ScriptQualityReview(ArtifactIdentity):
    approved: bool
    quality_scores: ScriptQualityScores
    blocking_issues: list[ScriptBlockingIssue] = Field(
        default_factory=list
    )
    advisory_notes: list[str] = Field(default_factory=list)
    revision_brief: str = ""

    @model_validator(mode="after")
    def validate_approval(self) -> ScriptQualityReview:
        if self.approved and self.blocking_issues:
            raise ValueError(
                "approved script review cannot contain blocking issues"
            )
        if not self.approved and not self.blocking_issues:
            raise ValueError(
                "rejected script review requires a blocking issue"
            )
        return self


class RetentionGateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str
    hook_notes: list[str] = Field(default_factory=list)
    reveal_notes: list[str] = Field(default_factory=list)
    dead_zones: list[str] = Field(default_factory=list)
    revision_requests: list[str] = Field(default_factory=list)
    approved: bool = False


class ScriptRevisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_signature: str = Field(min_length=1)
    previous_script_hash: str = Field(min_length=1)
    revised_script_hash: str = Field(min_length=1)
    revised_word_count: int = Field(ge=0)
    # Issue codes the reviser judged not to name a real weakness. Equal
    # previous and revised hashes with codes here mean the revision was
    # declined in full, which is a recorded outcome rather than a failure.
    unresolved_issue_codes: list[str] = Field(default_factory=list)
    release_integrity_issue_codes: list[str] = Field(
        default_factory=list
    )


class ScriptQualityIteration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_pass: int = Field(ge=1)
    review_contract_version: str = Field(min_length=1)
    review: ScriptQualityReview
    retention_gate: RetentionGateSnapshot
    script_hash: str = Field(min_length=1)
    word_count: int = Field(ge=0)
    revision: ScriptRevisionRecord | None = None


class ScriptReviewPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(min_length=1)
    retry_rule: str = Field(min_length=1)
    # Fingerprint of the writer's prompt pack at the time the approval was
    # earned. A saved approval speaks for the instructions it was reviewed
    # under; when the prompt pack moves, the approval is stale and the ledger
    # is discarded rather than honoured. Empty on ledgers written before the
    # field existed, which never match a real fingerprint -- the safe
    # direction (one re-review) for the back catalogue.
    prompt_pack_fingerprint: str = ""


class ScriptQualityIterations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str = Field(min_length=1)
    review_policy: ScriptReviewPolicy
    iterations: list[ScriptQualityIteration] = Field(
        default_factory=list
    )
