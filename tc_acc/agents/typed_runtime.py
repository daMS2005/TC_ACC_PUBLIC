from __future__ import annotations

from collections.abc import Callable, Collection
import os
from pathlib import Path
import time
from typing import Any, TypeVar

from pydantic import BaseModel, RootModel

from ..token_preflight import require_token_preflight
from ..storage import write_text_if_changed
from ..usage import record_usage
from ..providers.model_client import (
    fallback_model_for,
    is_qwen_credential_fallback_error,
    is_qwen_model,
    is_quota_or_auth_model_error,
    is_transient_model_error,
    log_model_fallback,
    model_fallback_circuit_is_open,
    model_provider_name,
    qwen_credential_pools,
)
from ..run_logging import log_detail, log_event


OutputT = TypeVar("OutputT")

TYPED_AGENT_OPERATION = "pydantic_ai.structured_agent"

# The typed agents used to go straight at their configured model and re-raise
# the typed-contract failure, so a Gemini quota wall ended a run that the rest
# of the pipeline would have carried on the fallback provider. The ladder here
# is the same one providers/openai_json.py runs: bounded backoff for transient
# provider trouble, then an announced failover to the declared fallback model.
TYPED_TRANSIENT_MAX_ATTEMPTS = 3
TYPED_TRANSIENT_RETRY_DELAYS_SECONDS = (5.0, 20.0)


class JsonObjectOutput(RootModel[dict[str, Any]]):
    pass


def provider_model_name(model: str) -> str:
    if ":" in model:
        return model
    if model.startswith("gemini"):
        return f"google:{model}"
    return f"openai:{model}"


def resolve_agent_model(model: str | Any) -> Any:
    if not isinstance(model, str):
        return model
    if is_qwen_model(model):
        from pydantic_ai.models.openai import OpenAIResponsesModel
        from pydantic_ai.models.fallback import FallbackModel
        from pydantic_ai.providers.openai import OpenAIProvider

        models = [
            OpenAIResponsesModel(
                model,
                provider=OpenAIProvider(
                    api_key=pool.api_key,
                    base_url=pool.base_url,
                ),
                settings={
                    "extra_body": {
                        "enable_thinking": True,
                    }
                },
            )
            for pool in qwen_credential_pools()
        ]
        if len(models) == 1:
            return models[0]
        return FallbackModel(
            models[0],
            *models[1:],
            fallback_on=_typed_qwen_credential_fallback,
        )
    resolved = provider_model_name(model)
    if not resolved.startswith("google:"):
        return resolved
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing GEMINI_API_KEY for the PydanticAI Google provider."
        )
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider

    return GoogleModel(
        resolved.split(":", 1)[1],
        provider=GoogleProvider(api_key=api_key),
    )


def _typed_qwen_credential_fallback(exc: Exception) -> bool:
    should_fallback = is_qwen_credential_fallback_error(exc)
    if should_fallback:
        event = {
            "error_type": type(exc).__name__,
            "error": str(exc),
            "credential_order": ["payg", "token"],
        }
        log_event("qwen_typed_credential_pool_fallback", **event)
        log_detail("qwen_typed_credential_pool_fallback", **event)
    return should_fallback


def _agent_output_contract(
    model: str | Any,
    output_type: type[OutputT],
) -> Any:
    if not isinstance(model, str) or not is_qwen_model(model):
        return output_type
    from pydantic_ai.output import PromptedOutput

    # Qwen thinking mode rejects the forced tool_choice used by
    # tool-based structured output. PromptedOutput keeps thinking enabled
    # while PydanticAI still validates the returned JSON into output_type.
    return PromptedOutput(
        output_type,
        template=(
            "Return only one JSON object matching this JSON schema. "
            "Do not include markdown fences or commentary:\n{schema}"
        ),
    )


def _error_chain(exc: BaseException) -> list[BaseException]:
    """The exception and the causes PydanticAI wrapped it around."""

    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and len(chain) < 10:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _provider_failure_kind(exc: BaseException) -> str:
    """Classify a typed-contract failure: quota/auth, transient, or ours.

    PydanticAI raises its own error type with the provider status folded into
    the message, and sometimes with the provider exception as the cause, so
    the whole chain is classified rather than just the outermost error.
    """

    chain = _error_chain(exc)
    if any(
        is_quota_or_auth_model_error(item)
        for item in chain
        if isinstance(item, Exception)
    ):
        return "quota_or_auth"
    if any(
        is_transient_model_error(item)
        for item in chain
        if isinstance(item, Exception)
    ):
        return "transient"
    return ""


def _typed_failover_metadata(
    stage_name: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    return {"stage": stage_name, **(metadata or {})}


def run_typed_agent(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str | Any,
    output_type: type[OutputT],
    stage_name: str,
    metadata: dict[str, Any] | None = None,
    max_attempts: int = 2,
    validator: Callable[[OutputT], list[str]] | None = None,
    trace_path: Path | None = None,
) -> OutputT:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    require_token_preflight()

    model = _model_after_circuit_preflight(
        model,
        stage_name=stage_name,
        metadata=metadata,
    )
    try:
        return _run_typed_agent_on_model(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            output_type=output_type,
            stage_name=stage_name,
            metadata=metadata,
            max_attempts=max_attempts,
            validator=validator,
            trace_path=trace_path,
        )
    except Exception as exc:
        failure_kind = _provider_failure_kind(exc)
        if not failure_kind or not isinstance(model, str):
            raise
        fallback = fallback_model_for(model)
        if not fallback:
            if failure_kind == "quota_or_auth":
                # Failing fast beats burning the rest of the ladder's budget
                # on a provider that has already said no.
                raise RuntimeError(
                    f"Provider {model_provider_name(model)} refused the "
                    f"{stage_name} typed-contract request for {model} "
                    "(quota exhausted or credentials rejected) and no "
                    "fallback model is configured for that provider: "
                    f"{exc}"
                ) from exc
            raise
        log_model_fallback(
            operation=TYPED_AGENT_OPERATION,
            requested_model=model,
            fallback_model=fallback,
            exc=exc,
            metadata={
                **_typed_failover_metadata(stage_name, metadata),
                "failure_kind": failure_kind,
            },
        )
        return _run_typed_agent_on_model(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=fallback,
            output_type=output_type,
            stage_name=stage_name,
            metadata={
                **(metadata or {}),
                "fallback_from_model": model,
            },
            max_attempts=max_attempts,
            validator=validator,
            trace_path=trace_path,
        )


def _model_after_circuit_preflight(
    model: str | Any,
    *,
    stage_name: str,
    metadata: dict[str, Any] | None,
) -> str | Any:
    """Start on the fallback while the primary's circuit is still open."""

    if not isinstance(model, str):
        return model
    fallback = fallback_model_for(model)
    if not fallback or not model_fallback_circuit_is_open(model):
        return model
    event = {
        "operation": TYPED_AGENT_OPERATION,
        "requested_model": model,
        "fallback_model": fallback,
        "reason": "prior_provider_outage_in_run",
        **_typed_failover_metadata(stage_name, metadata),
    }
    log_event("model_fallback_circuit_open", **event)
    log_detail("model_fallback_circuit_open", **event)
    return fallback


def _run_typed_agent_on_model(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str | Any,
    output_type: type[OutputT],
    stage_name: str,
    metadata: dict[str, Any] | None,
    max_attempts: int,
    validator: Callable[[OutputT], list[str]] | None,
    trace_path: Path | None,
) -> OutputT:
    """One model's turn: bounded transient retries, then the failure."""

    for attempt in range(1, TYPED_TRANSIENT_MAX_ATTEMPTS + 1):
        try:
            return _run_typed_agent_once(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                output_type=output_type,
                stage_name=stage_name,
                metadata=metadata,
                max_attempts=max_attempts,
                validator=validator,
                trace_path=trace_path,
            )
        except Exception as exc:
            if (
                attempt == TYPED_TRANSIENT_MAX_ATTEMPTS
                or _provider_failure_kind(exc) != "transient"
            ):
                raise
            delay_seconds = TYPED_TRANSIENT_RETRY_DELAYS_SECONDS[attempt - 1]
            retry_metadata = {
                "operation": TYPED_AGENT_OPERATION,
                "model": str(model),
                "provider": _provider_name(model),
                "attempt": attempt,
                "next_attempt": attempt + 1,
                "max_attempts": TYPED_TRANSIENT_MAX_ATTEMPTS,
                "delay_seconds": delay_seconds,
                "error_type": type(exc).__name__,
                "error": str(exc),
                **_typed_failover_metadata(stage_name, metadata),
            }
            log_event("model_transient_retry", **retry_metadata)
            log_detail("model_transient_retry", **retry_metadata)
            time.sleep(delay_seconds)
    raise RuntimeError(
        "Typed agent transient retry loop exited unexpectedly."
    )


def _run_typed_agent_once(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str | Any,
    output_type: type[OutputT],
    stage_name: str,
    metadata: dict[str, Any] | None,
    max_attempts: int,
    validator: Callable[[OutputT], list[str]] | None,
    trace_path: Path | None,
) -> OutputT:
    try:
        from pydantic_ai import (
            Agent,
            ModelRetry,
            RunContext,
            UsageLimits,
            capture_run_messages,
        )
        from pydantic_ai.messages import ModelMessagesTypeAdapter
        from pydantic_ai.usage import RunUsage
    except ImportError as exc:
        raise RuntimeError(
            "PydanticAI is required for typed agent execution. "
            "Install the project's full dependency set."
        ) from exc

    resolved_model = resolve_agent_model(model)
    agent = Agent(
        resolved_model,
        output_type=_agent_output_contract(model, output_type),
        system_prompt=system_prompt.strip(),
        retries={"output": max_attempts - 1},
        name=_agent_name(stage_name),
    )
    if validator is not None:

        @agent.output_validator
        def validate_output(
            _context: RunContext[object],
            output: OutputT,
        ) -> OutputT:
            errors = validator(output)
            if errors:
                raise ModelRetry("; ".join(errors))
            return output

    usage = RunUsage()
    with capture_run_messages() as messages:
        try:
            result = agent.run_sync(
                user_prompt.strip(),
                usage=usage,
                usage_limits=UsageLimits(request_limit=max_attempts),
                metadata=metadata or {},
            )
            return result.output
        finally:
            if trace_path is not None and messages:
                write_text_if_changed(
                    trace_path,
                    ModelMessagesTypeAdapter.dump_json(
                        messages,
                        indent=2,
                    ).decode("utf-8"),
                )
            provider = _provider_name(model)
            record_usage(
                provider,
                "pydantic_ai.structured_agent",
                model=str(model),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                resource_units={
                    "requests": usage.requests,
                    "tool_calls": usage.tool_calls,
                    **dict(usage.details),
                },
                metadata={
                    "stage": stage_name,
                    "max_attempts": max_attempts,
                    "system_prompt_chars": len(system_prompt),
                    "user_prompt_chars": len(user_prompt),
                    **(metadata or {}),
                },
            )


def pydantic_json_agent(
    system_prompt: str,
    user_prompt: str,
    model: str,
    metadata: dict[str, Any] | None = None,
    *,
    max_attempts: int = 2,
    output_model: type[BaseModel] | None = None,
    output_model_exclude: Collection[str] = (),
) -> dict[str, Any]:
    """Run one JSON-object contract call on the typed runtime.

    `output_model` is opt-in. Without it this is what it has always been: the
    output type is an unconstrained object, so the model is told nothing about
    the shape its caller is about to demand and discovers it by rejection.

    With it, the request carries a strict schema derived from that contract,
    so the provider enforces the shape instead. Nothing is removed: the
    caller's validation and its correction lap remain the fallback, which is
    where every cross-field and semantic rule still lives.

    `max_attempts` is the caller's to set. It used to be inferred from
    whether `metadata` carried an "attempt" key, on the theory that only a
    caller running its own retry loop would stamp one. That is not what the
    key means: "attempt" is observability, stamped all over this codebase for
    logs and usage records, and any caller that added it for a log line
    silently halved its own contract-retry budget. A caller that owns the
    outer loop now says so by passing max_attempts=1.

    This budget is per model. The failover ladder in run_typed_agent spends
    it again on the fallback model, which is the point: a budget of one means
    one attempt on each rung, not one attempt in total.
    """

    if output_model is not None:
        structured = _structured_json_call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            metadata=metadata,
            output_model=output_model,
            output_model_exclude=output_model_exclude,
            max_attempts=max_attempts,
        )
        if structured is not None:
            return structured

    output = run_typed_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        output_type=JsonObjectOutput,
        stage_name=str((metadata or {}).get("stage") or "json_agent"),
        metadata=metadata,
        max_attempts=max_attempts,
    )
    return output.root


def _structured_json_call(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    metadata: dict[str, Any] | None,
    output_model: type[BaseModel],
    output_model_exclude: Collection[str],
    max_attempts: int,
) -> dict[str, Any] | None:
    """Run the request through the provider's strict structured-output path.

    Returns None when this model cannot be asked for a strict schema, so the
    caller falls back to the typed runtime it has always used. Only the
    OpenAI-family Responses surface is routed here: Qwen reaches the same
    endpoint without honouring the schema, and Gemini needs its own dialect
    through its own client.
    """

    provider = model_provider_name(model)
    if provider != "openai":
        event = {
            "stage": str((metadata or {}).get("stage") or "json_agent"),
            "model": model,
            "provider": provider,
            "output_model": output_model.__name__,
            "reason": "structured_output_unsupported_for_provider",
        }
        log_event("model_structured_output_degraded", **event)
        log_detail("model_structured_output_degraded", **event)
        return None

    from ..providers.openai_json import openai_json

    return openai_json(
        system_prompt,
        user_prompt,
        model=model,
        metadata=metadata,
        output_model=output_model,
        output_model_exclude=output_model_exclude,
        # The caller's retry budget is the caller's. A stage running its own
        # correction loop passes 1, and the repair inside one call must not
        # quietly multiply it.
        max_contract_attempts=max_attempts,
    )


def _provider_name(model: str | Any) -> str:
    if not isinstance(model, str):
        return "pydantic_ai_test"
    return model_provider_name(model)


def _agent_name(stage_name: str) -> str:
    normalized = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in stage_name
    ).strip("_")
    return normalized or "typed_agent"
