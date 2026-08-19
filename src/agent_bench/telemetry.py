"""Normalize heterogeneous JSONL and OpenTelemetry output from both harnesses."""

import json
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .models import Usage


def parse_json_events(text: str) -> List[Any]:
    """Extract valid JSON objects while tolerating non-JSON diagnostic lines."""

    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            # Some CLIs prefix structured events with a timestamp or log level.
            start = line.find("{")
            if start >= 0:
                try:
                    events.append(json.loads(line[start:]))
                except json.JSONDecodeError:
                    pass
    return events


def _walk(value: Any) -> Iterator[Dict[str, Any]]:
    """Yield nested mappings because harness event envelopes vary by version."""

    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _number(value: Any) -> float:
    """Coerce telemetry numbers without treating JSON booleans as token counts."""

    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _usage_from_mapping(value: Dict[str, Any]) -> Tuple[int, int, int, int, int]:
    """Read common snake_case, camelCase, and OpenCode token layouts."""

    cache = value.get("cache") if isinstance(value.get("cache"), dict) else {}
    return (
        int(_number(value.get("input", value.get("input_tokens", value.get("inputTokens"))))),
        int(_number(value.get("output", value.get("output_tokens", value.get("outputTokens"))))),
        int(
            _number(
                value.get("reasoning", value.get("reasoning_tokens", value.get("reasoningTokens")))
            )
        ),
        int(
            _number(
                value.get(
                    "cache_read",
                    value.get(
                        "cache_read_tokens",
                        value.get("cacheReadTokens", value.get("cacheRead", cache.get("read"))),
                    ),
                )
            )
        ),
        int(
            _number(
                value.get(
                    "cache_write",
                    value.get(
                        "cache_write_tokens",
                        value.get("cacheWriteTokens", value.get("cacheWrite", cache.get("write"))),
                    ),
                )
            )
        ),
    )


def parse_usage(text: str) -> Usage:
    """Aggregate per-turn usage while treating zero reported cost as unknown."""

    input_tokens = output_tokens = reasoning_tokens = 0
    cache_read_tokens = cache_write_tokens = 0
    reasoning_seen = False
    costs = []
    for event in parse_json_events(text):
        for mapping in _walk(event):
            for key in ("tokens", "usage"):
                values = mapping.get(key)
                if isinstance(values, dict):
                    parsed = _usage_from_mapping(values)
                    input_tokens += parsed[0]
                    output_tokens += parsed[1]
                    reasoning_tokens += parsed[2]
                    cache_read_tokens += parsed[3]
                    cache_write_tokens += parsed[4]
                    reasoning_seen = reasoning_seen or any(
                        name in values for name in ("reasoning", "reasoning_tokens", "reasoningTokens")
                    )
            attributes = mapping.get("attributes")
            if isinstance(attributes, dict):
                operation = attributes.get("gen_ai.operation.name")
                if operation not in (None, "chat"):
                    continue
                reasoning = int(
                    _number(
                        attributes.get(
                            "gen_ai.usage.reasoning.output_tokens",
                            attributes.get("gen_ai.usage.reasoning_tokens"),
                        )
                    )
                )
                cache_read = int(
                    _number(attributes.get("gen_ai.usage.cache_read.input_tokens"))
                )
                cache_write = int(
                    _number(attributes.get("gen_ai.usage.cache_creation.input_tokens"))
                )
                # Copilot's OTel totals include their cache and reasoning subsets. Normalize them
                # to the mutually exclusive buckets emitted directly by OpenCode.
                input_tokens += max(
                    int(_number(attributes.get("gen_ai.usage.input_tokens")))
                    - cache_read
                    - cache_write,
                    0,
                )
                output_tokens += max(
                    int(_number(attributes.get("gen_ai.usage.output_tokens"))) - reasoning,
                    0,
                )
                reasoning_tokens += reasoning
                reasoning_seen = reasoning_seen or any(
                    key in attributes
                    for key in (
                        "gen_ai.usage.reasoning.output_tokens",
                        "gen_ai.usage.reasoning_tokens",
                    )
                )
                cache_read_tokens += cache_read
                cache_write_tokens += cache_write
            direct_cost = _number(mapping.get("native_cost_usd"))
            if not direct_cost and ("tokens" in mapping or "usage" in mapping):
                cost_value = mapping.get("cost")
                if isinstance(cost_value, dict):
                    direct_cost = _number(cost_value.get("total"))
                else:
                    direct_cost = _number(cost_value)
            if direct_cost > 0:
                costs.append(direct_cost)
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens if reasoning_seen else None,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        native_cost_usd=sum(costs) if costs else None,
    )


def parse_omp_transcript(text: str) -> Usage:
    """Aggregate OMP usage from the authoritative final transcript.

    OMP's JSON stream replays every message's usage inside message_end, turn_end,
    and the closing agent_end transcript, so only the final transcript is used.
    Its output bucket includes reasoning, while cacheRead/cacheWrite are separate
    per-request buckets; normalize these to mutually exclusive runner buckets.
    """

    messages = []
    completed_messages = []
    completed_turns = []
    completed_tool_results = []
    for event in parse_json_events(text):
        if event.get("type") == "agent_end":
            messages = event.get("messages") or []
        elif event.get("type") == "message_end" and isinstance(event.get("message"), dict):
            completed_messages.append(event["message"])
        elif event.get("type") == "turn_end" and isinstance(event.get("message"), dict):
            completed_turns.append(event["message"])
            tool_results = event.get("toolResults")
            if isinstance(tool_results, list):
                completed_tool_results.extend(tool_results)
    if not messages:
        # Successful OMP runs can omit agent_end. message_end and turn_end replay
        # the same usage, so aggregate exactly one event family.
        messages = [*(completed_messages or completed_turns), *completed_tool_results]
    if not messages:
        return parse_usage(text)
    input_tokens = output_tokens = reasoning_tokens = 0
    cache_read_tokens = cache_write_tokens = 0
    reasoning_seen = False
    costs = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        usages = []
        if message.get("role") == "assistant" and isinstance(message.get("usage"), dict):
            usages.append(message["usage"])
        if message.get("role") == "toolResult" and message.get("toolName") == "task":
            details = message.get("details")
            if isinstance(details, dict) and isinstance(details.get("usage"), dict):
                usages.append(details["usage"])
        for usage in usages:
            parsed = _usage_from_mapping(usage)
            input_tokens += parsed[0]
            output_tokens += max(parsed[1] - parsed[2], 0)
            reasoning_tokens += parsed[2]
            cache_read_tokens += parsed[3]
            cache_write_tokens += parsed[4]
            reasoning_seen = reasoning_seen or any(
                name in usage
                for name in ("reasoning", "reasoning_tokens", "reasoningTokens")
            )
            cost = usage.get("cost")
            total = _number(cost.get("total")) if isinstance(cost, dict) else _number(cost)
            if total > 0:
                costs.append(total)
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens if reasoning_seen else None,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        native_cost_usd=sum(costs) if costs else None,
    )


def extract_identities(text: str) -> List[Tuple[Optional[str], str]]:
    """Collect resolved identities from JSON events and OpenCode stream logs."""

    identities: List[Tuple[Optional[str], str]] = []
    provider_keys = {"provider", "providerID", "provider_id", "gen_ai.provider.name"}
    model_keys = {
        "model",
        "modelID",
        "model_id",
        "resolved_model",
        "gen_ai.response.model",
        "gen_ai.request.model",
    }
    for event in parse_json_events(text):
        for mapping in _walk(event):
            provider = model = None
            for key, value in mapping.items():
                if key in provider_keys and isinstance(value, str):
                    provider = value
                if key in model_keys and isinstance(value, str):
                    model = value
            if model is not None:
                identities.append((provider, model))

    # OpenCode's raw JSON events omit identity, while its INFO stream lines
    # report every main and auxiliary model call in a stable key=value form.
    for line in text.splitlines():
        if "message=stream" not in line:
            continue
        provider_match = re.search(r"\bproviderID=([^\s]+)", line)
        model_match = re.search(r"\bmodelID=([^\s]+)", line)
        if model_match:
            identities.append(
                (provider_match.group(1) if provider_match else None, model_match.group(1))
            )
    return identities


def extract_omp_identities(text: str) -> List[Tuple[Optional[str], str]]:
    """Collect only direct OMP assistant identities, excluding tool-result metadata."""

    identities: List[Tuple[Optional[str], str]] = []
    for event in parse_json_events(text):
        messages = []
        if event.get("type") in {"message_start", "message_end", "turn_end"}:
            messages.append(event.get("message"))
        elif event.get("type") == "agent_end" and isinstance(event.get("messages"), list):
            messages.extend(event["messages"])
        for message in messages:
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            provider = message.get("provider")
            model = message.get("model")
            if isinstance(model, str):
                identities.append((provider if isinstance(provider, str) else None, model))
    return identities


def extract_identity(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return the last resolved identity for callers expecting one model."""

    identities = extract_identities(text)
    return identities[-1] if identities else (None, None)
