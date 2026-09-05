from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from typing import Any, Literal


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def to_plain(value: Any) -> Any:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        options = {"mode": "json"}
        if getattr(value, "_tc_acc_exclude_unset", False):
            options.update(
                exclude_none=True,
                exclude_unset=True,
            )
        return to_plain(model_dump(**options))
    if is_dataclass(value):
        return {key: to_plain(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_plain(item) for key, item in value.items()}
    return value


@dataclass
class SourceRecord:
    source_type: str
    source_name: str
    source_url: str
    title: str
    raw_text: str
    author: str | None = None
    score: int | None = None
    created_at: str | None = None
    external_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    accepted: bool
    score: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evaluator: str = "rules"
    labels: list[str] = field(default_factory=list)


@dataclass
class CaseLead:
    lead_id: str
    source_type: str
    source_name: str
    source_url: str
    title: str
    summary: str
    raw_text: str
    case_keywords: list[str]
    people: list[str]
    locations: list[str]
    date_hint: str | None
    score: float
    discovered_at: str
    dedupe_hash: str
    status: Literal["accepted", "rejected", "needs_review"] = "needs_review"
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceNote:
    title: str
    url: str
    note: str = ""
    reliability: str = "unknown"


ClaimConfidence = Literal["low", "medium", "high"]
ClaimVerificationStatus = Literal[
    "unverified",
    "verified",
    "contested",
]


def normalize_claim_confidence(value: object) -> ClaimConfidence:
    normalized = str(value or "").strip().lower()
    for level in ("high", "medium", "low"):
        if normalized == level or normalized.startswith(f"{level} "):
            return level  # type: ignore[return-value]
    return "medium"


def normalize_claim_verification(
    value: object,
) -> tuple[ClaimVerificationStatus, str]:
    raw = str(value or "").strip()
    normalized = raw.lower()
    if normalized in {"verified", "unverified", "contested"}:
        return normalized, ""  # type: ignore[return-value]
    if any(
        term in normalized
        for term in ("contested", "disputed", "conflicting")
    ):
        status: ClaimVerificationStatus = "contested"
    elif normalized.startswith("verified") and not any(
        term in normalized
        for term in ("unconfirmed", "unverified", "not verified")
    ):
        status = "verified"
    else:
        status = "unverified"
    return status, raw


@dataclass
class Claim:
    claim_id: str
    text: str
    source_urls: list[str]
    confidence: ClaimConfidence = "medium"
    verification_status: ClaimVerificationStatus = "unverified"
    script_usage: list[str] = field(default_factory=list)
    verification_notes: str = ""

    def __post_init__(self) -> None:
        self.confidence = normalize_claim_confidence(self.confidence)
        status, inferred_notes = normalize_claim_verification(
            self.verification_status
        )
        self.verification_status = status
        if not self.verification_notes:
            self.verification_notes = inferred_notes


@dataclass
class ClaimLedger:
    case_id: str
    claims: list[Claim] = field(default_factory=list)


TimelineEntryKind = Literal[
    "case_event",
    "investigation",
    "publication",
    "research",
]

# What an entry decodes to when the research stage did not label it. This is
# NOT a fifth kind the model may emit -- it is where twelve episodes of
# dossiers written before ``entry_kind`` existed land, and where any word
# outside the enum lands. Nothing may treat it as case history; see
# ``chronology_admissible``.
TIMELINE_ENTRY_KIND_UNKNOWN = "unknown"

TimelineEntryKindOrUnknown = Literal[
    "case_event",
    "investigation",
    "publication",
    "research",
    "unknown",
]

_TIMELINE_ENTRY_KINDS: frozenset[str] = frozenset(
    {"case_event", "investigation", "publication", "research"}
)


def normalize_timeline_entry_kind(
    value: object,
) -> TimelineEntryKindOrUnknown:
    """Exactly one of the four kinds, or ``unknown``.

    The match is exact after folding case and separators, deliberately unlike
    ``normalize_claim_confidence``'s prefix match. A near miss lands on
    ``unknown``: the cost of an unknown is one stop a strip declines to draw,
    and the cost of guessing ``case_event`` is a fabricated record under
    editorial law 7.5.
    """

    normalized = (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )
    if normalized in _TIMELINE_ENTRY_KINDS:
        return normalized  # type: ignore[return-value]
    return TIMELINE_ENTRY_KIND_UNKNOWN  # type: ignore[return-value]


def timeline_entry_kind(entry: object) -> TimelineEntryKindOrUnknown:
    """The kind of one dossier timeline entry, in whatever shape it arrived."""

    if isinstance(entry, Mapping):
        return normalize_timeline_entry_kind(entry.get("entry_kind"))
    return normalize_timeline_entry_kind(getattr(entry, "entry_kind", None))


def chronology_admissible(entry: object) -> bool:
    """Whether an entry may be pinned on a ChronologyStrip. Fails closed.

    Editorial law 7.1 strips the event prose off a chronology stop, and that is
    exactly what makes an unlabelled entry dangerous: with the text gone, the
    day this pipeline ran its research is indistinguishable from the day the
    body was found. Only ``case_event`` is admissible. ``unknown`` is refused,
    so a dossier written before the field existed yields no strip at all rather
    than a wrong one.
    """

    return timeline_entry_kind(entry) == "case_event"


def normalize_timeline_entries(entries: object) -> list[Any]:
    """Timeline entries carrying an explicit, canonical ``entry_kind``.

    Stamping the field rather than leaving it absent is what makes a legacy
    dossier legible: after a load it says ``unknown`` in writing instead of
    saying nothing, and an unlabelled entry from a current research pass is not
    mistaken for one the field predates.
    """

    normalized: list[Any] = []
    for entry in entries or []:  # type: ignore[union-attr]
        if not isinstance(entry, Mapping):
            normalized.append(entry)
            continue
        item = dict(entry)
        item["entry_kind"] = normalize_timeline_entry_kind(
            item.get("entry_kind")
        )
        normalized.append(item)
    return normalized


@dataclass
class ResearchDossier:
    case_id: str
    case_name: str
    lead: CaseLead
    summary: str
    timeline: list[dict[str, Any]] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    verified_claims: list[str] = field(default_factory=list)
    uncertain_claims: list[str] = field(default_factory=list)
    avoid_claims: list[str] = field(default_factory=list)
    sources: list[SourceNote] = field(default_factory=list)
    sensitivity_notes: list[str] = field(default_factory=list)
    legal_notes: list[str] = field(default_factory=list)
    visual_opportunities: list[str] = field(default_factory=list)
    geo_asset_recommendation: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.timeline = normalize_timeline_entries(self.timeline)


@dataclass
class TimelineStory:
    case_id: str
    beats: list[dict[str, Any]]
    reveal_order: list[str] = field(default_factory=list)
    missing_context: list[str] = field(default_factory=list)


@dataclass
class SensitivityReview:
    case_id: str
    flags: list[dict[str, Any]] = field(default_factory=list)
    script_guidance: list[str] = field(default_factory=list)
    blocked_claims: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class ScriptPackage:
    episode_id: str
    case_id: str
    working_title: str
    target_minutes: tuple[int, int] = (12, 18)
    # Presentation copy, declared ahead of the narration for the same
    # reason the prompt asks for it there: generation is left to right, and
    # a hook line written after the script is a hook line copied from the
    # script's first sentence. Measured -- the schema-only arm of the
    # headroom experiment did exactly that in 3/3 runs.
    case_title: str = ""
    hook_line: str = ""
    welcome_line: str = ""
    script: str = ""
    hook_text: str = ""
    chapters: list[dict[str, Any]] = field(default_factory=list)
    outro_lines: list[str] = field(default_factory=list)
    # Quotations of the record with their speakers. Empty is a real answer:
    # a quotation with no establishable attribution is a page of the record
    # nobody said, which editorial law 7.5 rates worse than being off-brand.
    quotations: list[dict[str, Any]] = field(default_factory=list)
    # The editorial marks. ``None`` means the writer declined to make the
    # call, and every consumer must be able to draw nothing -- a ``lift``
    # where nothing was ever hidden is named in editorial law 7.5 as a
    # fabricated record, so an absent mark is safer than a default one.
    testimony_quote: dict[str, Any] | None = None
    detail_of_record: dict[str, Any] | None = None
    redaction_directive: Literal["lift", "strike"] | None = None
    sensitivity_notes: list[str] = field(default_factory=list)
    pacing_notes: list[str] = field(default_factory=list)


# The fields a narration revision neither authors nor invalidates.
SCRIPT_PRESENTATION_FIELDS = (
    "case_title",
    "hook_line",
    "welcome_line",
    "outro_lines",
    "quotations",
    "testimony_quote",
    "detail_of_record",
    "redaction_directive",
)


def carried_script_presentation(package: Any) -> dict[str, Any]:
    """Presentation copy and marks, ready to splat into a rebuilt package.

    Every revision path rebuilds ScriptPackage field by field rather than
    mutating it, so a field the rebuilder does not name silently resets to
    its default. Without this the title sequence and the edit marks would
    survive on runs that took no revision and vanish on runs that did --
    the worst shape of bug, because it is invisible until the one episode
    that needed a fix comes out with no sign-off.

    The revisers rewrite narration; they are not asked for this copy and
    do not return it. Provenance for a quotation is ``source_claim_id``
    against the record, which a narration edit cannot move. ``cue`` is the
    exception: it names a narration phrase and can go stale here, so the
    extractor downstream must resolve cues against the script it actually
    has rather than trusting them.

    Reads by name so it works on the dataclass, on the validated artifact
    model the workflow state swaps in, and on the saved artifact dict a
    resume reads back off disk -- the three shapes a package arrives in.
    """

    read = (
        package.get
        if isinstance(package, dict)
        else lambda name, default=None: getattr(package, name, default)
    )
    return {
        name: to_plain(read(name))
        for name in SCRIPT_PRESENTATION_FIELDS
        if read(name) is not None
    }


@dataclass
class PacingReview:
    episode_id: str
    hook_notes: list[str] = field(default_factory=list)
    reveal_notes: list[str] = field(default_factory=list)
    dead_zones: list[str] = field(default_factory=list)
    revision_requests: list[str] = field(default_factory=list)
    approved: bool = False


@dataclass
class ScenePlan:
    episode_id: str
    scenes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AssetPlan:
    episode_id: str
    assets_needed: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AssetClassification:
    asset_type: str
    person_role: str = "none"
    source_type: str = "unknown"
    sensitivity_level: Literal["low", "medium", "high", "blocked"] = "medium"
    usage_kind: Literal["evidentiary", "contextual", "editorial", "decorative", "thumbnail_packaging"] = "contextual"
    allowed_usage: list[str] = field(default_factory=list)
    blocked_usage: list[str] = field(default_factory=list)
    validation_required: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class AssetRecord:
    asset_id: str
    asset_type: str
    description: str
    classification: AssetClassification | None = None
    local_path: str | None = None
    source_url: str | None = None
    rights_status: str = "unknown"
    attribution_required: bool = False
    commercial_youtube_ok: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class AssetManifest:
    episode_id: str
    assets: list[AssetRecord] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class AssetRequest:
    """One visual the asset plan asked for, before anyone went looking.

    Deliberately *not* an `AssetRecord`. It has no media, no rights, and no
    id anything can render; what it has is a description of what should
    exist. These used to be minted straight into the asset manifest as
    `research-needed-*` records with `rights_status="source_research_needed"`,
    where they were indistinguishable from an asset that had been acquired
    and had merely failed to download -- and where every count that read the
    manifest counted them.
    """

    request_id: str
    # One of the six acquisition types, so this can be compared against what
    # search came back with. The plan is not written in those six words on any
    # path, so this is a reading of `planned_asset_type` rather than a copy of
    # it -- see `tc_acc.assets.tools.normalize_request_asset_type`.
    asset_type: str
    description: str
    # The plan's own word for it, kept so a request can be traced back to the
    # plan item it was read from.
    planned_asset_type: str = ""
    plan_index: int = 0
    classification: AssetClassification | None = None
    # Whether visual search can answer this at all. Music and sound effects
    # are requests nobody can resolve with a provider query, so no work order
    # is owed for them and no "we searched and found nothing" claim is made
    # about them either.
    searchable: bool = False
    # The query derived from `description`, before the case-identity scrub the
    # stock channel needs. `issued_query` is what search actually ran, which
    # is what fulfilment is scored against.
    search_query: str = ""
    issued_query: str = ""
    fulfilled: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class AssetPlanRequests:
    """What the asset plan asked for, and what acquisition came back with.

    The record of intent, kept next to the manifest rather than inside it.
    Knowing which visuals were wanted is the "we could not cover this beat"
    signal, and it is the reason these are relocated rather than deleted.

    Two shortfalls are recorded here, at the two granularities that are
    actually true, and they do not overlap:

    `unserved_asset_types` is the type-level claim -- a requested type that
    acquisition returned *nothing* for. Nobody could cover that beat at all.

    `unfulfilled_request_ids` is the request-level claim, and it is only
    possible because search now issues one work order per searchable request:
    the request's own query ran and no accepted asset came back from it. It is
    scored only within types that were partly served, because when a type
    returned nothing the type-level line already says it once and repeating it
    per request is noise.
    """

    episode_id: str
    requests: list[AssetRequest] = field(default_factory=list)
    acquired_by_asset_type: dict[str, int] = field(default_factory=dict)
    unserved_asset_types: list[str] = field(default_factory=list)
    unfulfilled_request_ids: list[str] = field(default_factory=list)


@dataclass
class CourtRecordResource:
    title: str
    url: str = ""
    source_type: str = "unknown"
    jurisdiction: str = "unknown"
    record_types: list[str] = field(default_factory=list)
    related_people: list[str] = field(default_factory=list)
    reliability: str = "unknown"
    access_notes: list[str] = field(default_factory=list)
    usage_notes: list[str] = field(default_factory=list)


@dataclass
class CourtRecordResourceLedger:
    case_id: str
    resources: list[CourtRecordResource] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class NewsInterviewResource:
    title: str
    url: str = ""
    outlet: str = ""
    source_type: str = "unknown"
    interview_subjects: list[str] = field(default_factory=list)
    related_people: list[str] = field(default_factory=list)
    date: str = ""
    usable_quotes: list[str] = field(default_factory=list)
    possible_clip_notes: list[str] = field(default_factory=list)
    reliability: str = "unknown"
    rights_notes: list[str] = field(default_factory=list)
    sensitivity_notes: list[str] = field(default_factory=list)


@dataclass
class NewsInterviewResourceLedger:
    case_id: str
    resources: list[NewsInterviewResource] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class LocationMapRequest:
    label: str
    request_scope: str = "location_only"
    location_name: str = ""
    location_role: str = "unknown"
    address_or_query: str = ""
    route_from: str = ""
    route_to: str = ""
    requested_media: list[str] = field(default_factory=list)
    map_queries: list[str] = field(default_factory=list)
    rights_notes: list[str] = field(default_factory=list)
    sensitivity_notes: list[str] = field(default_factory=list)
    usage_guidance: str = ""


@dataclass
class LocationMapResearchPlan:
    episode_id: str
    requests: list[LocationMapRequest] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class AssetValidationReport:
    episode_id: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    approved: bool = False
    issues: list[str] = field(default_factory=list)


@dataclass
class AssetEditorialIndex:
    episode_id: str
    assets: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


@dataclass
class AnimationPlan:
    episode_id: str
    scenes: list[dict[str, Any]] = field(default_factory=list)
    overlay_contract_version: int = 0
    allowed_motion_presets: list[str] = field(default_factory=list)
    style_notes: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class SoundDesignPlan:
    episode_id: str
    cues: list[dict[str, Any]] = field(default_factory=list)
    music_assets: list[dict[str, Any]] = field(default_factory=list)
    sfx_assets: list[dict[str, Any]] = field(default_factory=list)
    mix_notes: list[str] = field(default_factory=list)
    rights_notes: list[str] = field(default_factory=list)


@dataclass
class VoiceManifest:
    episode_id: str
    # The three narrators in tc_acc/providers/voice.py's registry. Widen this
    # and VoiceManifestArtifact together when one is added -- the artifact
    # contract forbids extras and validates this member list, so a provider
    # missing from either one records audio the run then cannot write down.
    provider: Literal["elevenlabs", "fishaudio", "openai"]
    voice_name: str
    audio_path: str | None = None
    timing_path: str | None = None
    # The narration, and only the narration. Every downstream timing check
    # sums this list -- the renderer tiles it across the composition, the
    # timing summary measures the episode from it, the animation plan's shot
    # boundaries are cut against that measurement -- so anything spoken that
    # is not narration cannot live here. See tc_acc/presentation_voice.py.
    chunks: list[dict[str, Any]] = field(default_factory=list)
    # The presenter's copy: the title-sequence question, the channel greeting,
    # the sign-off. Recorded and measured, deliberately unmounted. Empty for
    # any episode whose writer produced no presentation copy, which is every
    # episode recorded before the writer had the fields.
    presentation_segments: list[dict[str, Any]] = field(default_factory=list)
    # Records a deviation from the configured narration provider; empty when
    # narration uses that provider. `provider` and `voice_name` describe the
    # actual recording, while this field identifies fallback narration.
    provider_fallback: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


@dataclass
class RenderManifest:
    episode_id: str
    canvas: tuple[int, int] = (1920, 1080)
    preview_paths: list[str] = field(default_factory=list)
    screenshot_paths: list[str] = field(default_factory=list)
    final_video_path: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    cache_hits: list[str] = field(default_factory=list)


@dataclass
class RenderReview:
    episode_id: str
    frame_checks: list[dict[str, Any]] = field(default_factory=list)
    audio_checks: list[dict[str, Any]] = field(default_factory=list)
    revision_requests: list[str] = field(default_factory=list)
    approved: bool = False


@dataclass
class MetadataPackage:
    episode_id: str
    title_options: list[str] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    source_list: list[str] = field(default_factory=list)
    pinned_comment: str = ""
    thumbnail_prompt: str = ""
    # The episode's own critique, shipped beside it. Publishing metadata is
    # where a human looks first, so the findings report is named here rather
    # than left for someone to discover in the run directory.
    showrunner_findings_path: str = ""
    showrunner_findings_count: int = 0


@dataclass
class ReviewStatus:
    episode_id: str
    automated_passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    reviewed_at: str = field(default_factory=utc_now_iso)


@dataclass
class DeliveryManifest:
    episode_id: str
    target: Literal["local", "gcs"]
    local_video_path: str | None = None
    gcs_uri: str | None = None
    delivered: bool = False
    issues: list[str] = field(default_factory=list)
    # Reported, never enforced: a delivered episode names its findings report
    # so the critique travels with the render instead of dying with the run.
    showrunner_findings_path: str = ""
    showrunner_findings_count: int = 0
    truth_class_findings_count: int = 0


def asset_record_from_payload(payload: dict) -> AssetRecord:
    classification = payload.get("classification")
    return AssetRecord(
        asset_id=str(payload.get("asset_id", "")),
        asset_type=str(payload.get("asset_type", "")),
        description=str(payload.get("description", "")),
        classification=AssetClassification(**classification) if classification else None,
        local_path=payload.get("local_path"),
        source_url=payload.get("source_url"),
        rights_status=str(payload.get("rights_status", "unknown")),
        attribution_required=bool(payload.get("attribution_required", False)),
        commercial_youtube_ok=bool(payload.get("commercial_youtube_ok", False)),
        metadata=dict(payload.get("metadata", {})),
        notes=list(payload.get("notes", [])),
    )
