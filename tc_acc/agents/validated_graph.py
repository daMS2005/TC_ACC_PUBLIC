from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..run_logging import log_event
from ..storage import write_json
from ..utils import stable_hash
from .contract_shaping import shape_payload_to_contract


class ValidatedAgentAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(ge=1)
    response_hash: str = Field(min_length=1)
    validation_errors: list[str] = Field(default_factory=list)


class ValidatedAgentGraphState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(ge=1)
    correction: str = ""
    raw_payload: dict[str, object] = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)
    attempts: list[ValidatedAgentAttempt] = Field(
        default_factory=list
    )
    status: Literal[
        "pending",
        "retry",
        "accepted",
        "rejected",
    ] = "pending"


class ValidatedAgentResult[OutputT: BaseModel](BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected"]
    output: OutputT | None = None
    attempt: int = Field(ge=0)
    validation_errors: list[str] = Field(default_factory=list)
    attempts: list[ValidatedAgentAttempt] = Field(
        default_factory=list
    )


def run_validated_agent_graph[OutputT: BaseModel](
    *,
    stage_name: str,
    system_prompt: str,
    user_prompt: str,
    model: str,
    output_type: type[OutputT],
    validator: Callable[[OutputT], list[str]],
    json_agent: Callable[..., dict[str, object]],
    attempts_path: Path,
    max_attempts: int,
    validator_policy_version: str,
    before_call: Callable[[], None] | None = None,
    run_id: str = "",
    payload_context: dict[str, object] | None = None,
    payload_normalizer: (
        Callable[[dict[str, object]], dict[str, object]]
        | None
    ) = None,
    payload_normalizer_version: str = "",
    strict_output_schema: bool = False,
    strict_output_schema_exclude: Collection[str] = (),
) -> ValidatedAgentResult[OutputT]:
    """Run an agent until its output satisfies ``output_type`` and ``validator``.

    ``strict_output_schema`` opts this stage into provider-enforced shape. The
    schema is derived from ``output_type`` -- the very model the result is
    validated against on the way back -- so the request and the acceptance test
    cannot describe different things.

    The retry loop below is unchanged and remains the fallback. A schema can
    promise shape; it cannot promise that the claim IDs exist or that the cues
    are covered exactly once, and those are the rejections this loop is for.
    """

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph with SQLite checkpointing is required for validated "
            "agent execution. Install the project's full dependency set."
        ) from exc

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    if not validator_policy_version.strip():
        raise ValueError(
            "validator_policy_version must be a non-empty caller-owned "
            "version"
        )
    attempts_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path = attempts_path.with_suffix(
        ".langgraph.sqlite"
    )
    fixed_context = dict(payload_context or {})
    # The pipeline merges its own context into every response, so those fields
    # must never be asked of the model: a field the model was forced to answer
    # is not the same as a field the pipeline filled in.
    schema_exclude = frozenset(
        {*strict_output_schema_exclude, *fixed_context}
    ) & frozenset(output_type.model_fields)
    structured_kwargs: dict[str, object] = (
        {
            "output_model": output_type,
            "output_model_exclude": schema_exclude,
        }
        if strict_output_schema
        and _accepts_structured_output(json_agent)
        else {}
    )
    if strict_output_schema and not structured_kwargs:
        log_event(
            "model_structured_output_degraded",
            stage=stage_name,
            run_id=run_id,
            output_model=output_type.__name__,
            reason="json_agent_does_not_accept_output_model",
        )

    def call_agent(
        state: ValidatedAgentGraphState,
    ) -> dict[str, object]:
        if before_call:
            before_call()
        attempt = state.attempt + 1
        response = json_agent(
            system_prompt,
            user_prompt + state.correction,
            model=model,
            metadata={
                "stage": f"v2_{stage_name}",
                "attempt": attempt,
            },
            # This graph is the retry loop: it re-asks with a correction
            # appended, up to max_attempts times, and records every attempt.
            # An inner contract retry on top of that would multiply the
            # budget, so the agent gets one attempt per call. Said here
            # rather than inferred from the "attempt" metadata above, which
            # is a log field and not a statement about retries.
            max_attempts=1,
            **structured_kwargs,
        )
        raw_payload = (
            {**response, **fixed_context}
            if isinstance(response, dict)
            else {"invalid_response": response, **fixed_context}
        )
        if payload_normalizer is not None:
            raw_payload = payload_normalizer(raw_payload)
        # Strip what the contract forbids before validating, so the errors the
        # retry sees are the ones it can actually act on rather than a list
        # dominated by invented keys.
        dropped: list[str] = []
        raw_payload = shape_payload_to_contract(
            raw_payload,
            output_type,
            dropped=dropped,
        )
        if dropped:
            log_event(
                "v2_contract_shaped_payload",
                stage=stage_name,
                attempt=attempt,
                run_id=run_id,
                dropped=dropped[:40],
                dropped_count=len(dropped),
            )
        errors = _typed_validation_errors(
            raw_payload,
            output_type=output_type,
            validator=validator,
        )
        attempts = [
            *state.attempts,
            ValidatedAgentAttempt(
                attempt=attempt,
                response_hash=stable_hash(
                    json.dumps(
                        raw_payload,
                        sort_keys=True,
                        ensure_ascii=True,
                    )
                ),
                validation_errors=errors,
            ),
        ]
        write_json(
            attempts_path,
            {
                "stage": stage_name,
                "output_contract": output_type.__name__,
                "max_attempts": max_attempts,
                "validator_policy_version": validator_policy_version,
                "attempts": [
                    item.model_dump(mode="json")
                    for item in attempts
                ],
            },
        )
        return {
            "attempt": attempt,
            "raw_payload": raw_payload,
            "validation_errors": errors,
            "attempts": attempts,
            "status": (
                "accepted"
                if not errors
                else "rejected"
                if attempt >= max_attempts
                else "retry"
            ),
        }

    def prepare_retry(
        state: ValidatedAgentGraphState,
    ) -> dict[str, object]:
        return {
            "correction": (
                "\n\nDETERMINISTIC CONTRACT REJECTION:\n"
                f"{json.dumps(state.validation_errors, ensure_ascii=True)}\n"
                "Return a complete replacement JSON object that fixes only "
                "these contract errors while preserving valid work.\n"
                "Previous response:\n"
                f"{json.dumps(state.raw_payload, ensure_ascii=True)}"
            )
        }

    def route_after_call(
        state: ValidatedAgentGraphState,
    ) -> Literal["prepare_retry", "__end__"]:
        return (
            "prepare_retry"
            if state.status == "retry"
            else END
        )

    builder = StateGraph(ValidatedAgentGraphState)
    builder.add_node("call_agent", call_agent)
    builder.add_node("prepare_retry", prepare_retry)
    builder.add_edge(START, "call_agent")
    builder.add_conditional_edges("call_agent", route_after_call)
    builder.add_edge("prepare_retry", "call_agent")

    checkpoint_fingerprint = stable_hash(
        json.dumps(
            {
                "model": model,
                "system": system_prompt,
                "user": user_prompt,
                "output_schema": output_type.model_json_schema(),
                "payload_context": fixed_context,
                "payload_normalizer_version": (
                    payload_normalizer_version
                ),
                "validator_policy_version": validator_policy_version,
                "max_attempts": max_attempts,
            },
            sort_keys=True,
        )
    )
    thread_id = (
        f"{run_id or 'offline'}:{stage_name}:"
        f"{checkpoint_fingerprint[:16]}"
    )
    config = {"configurable": {"thread_id": thread_id}}
    initial = ValidatedAgentGraphState(
        max_attempts=max_attempts,
    )
    with SqliteSaver.from_conn_string(
        str(checkpoint_path)
    ) as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        snapshot = graph.get_state(config)
        if snapshot.next:
            result = graph.invoke(None, config=config)
        elif snapshot.values:
            result = snapshot.values
        else:
            result = graph.invoke(initial, config=config)
    final = ValidatedAgentGraphState.model_validate(result)
    current_validation_errors = _typed_validation_errors(
        final.raw_payload,
        output_type=output_type,
        validator=validator,
    )
    accepted = not current_validation_errors
    output = (
        output_type.model_validate(final.raw_payload)
        if accepted
        else None
    )
    return ValidatedAgentResult(
        status="accepted" if accepted else "rejected",
        output=output,
        attempt=final.attempt,
        validation_errors=current_validation_errors,
        attempts=final.attempts,
    )


def _accepts_structured_output(json_agent: Callable[..., object]) -> bool:
    """Can this agent be handed a strict output model?

    Callers may supply any callable here, including the small fakes the tests
    use. Asking one that never heard of ``output_model`` would turn an
    optimisation into a TypeError, so the opt-in is skipped -- and logged --
    rather than forced.
    """

    try:
        signature = inspect.signature(json_agent)
    except (TypeError, ValueError):
        return False
    parameters = signature.parameters
    if "output_model" in parameters:
        return True
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _typed_validation_errors[OutputT: BaseModel](
    payload: dict[str, object],
    *,
    output_type: type[OutputT],
    validator: Callable[[OutputT], list[str]],
) -> list[str]:
    try:
        output = output_type.model_validate(payload)
    except ValidationError as exc:
        return [
            (
                f"{'.'.join(str(part) for part in item['loc']) or '<root>'}: "
                f"{item['msg']}"
            )
            for item in exc.errors()
        ]
    return validator(output)
