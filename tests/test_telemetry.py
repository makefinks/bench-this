from agent_bench.telemetry import extract_identity, parse_usage


def test_copilot_otel_fixture_parses_tokens_and_native_cost():
    raw = """{"name":"chat model","attributes":{"gen_ai.operation.name":"chat","gen_ai.usage.input_tokens":120,"gen_ai.usage.output_tokens":8,"gen_ai.usage.reasoning.output_tokens":2,"gen_ai.usage.cache_read.input_tokens":40,"gen_ai.usage.cache_creation.input_tokens":6,"github.copilot.cost":1}}
{"name":"invoke_agent","attributes":{"gen_ai.operation.name":"invoke_agent","gen_ai.usage.input_tokens":120,"gen_ai.usage.output_tokens":8,"github.copilot.cost":1}}
"""
    usage = parse_usage(raw)
    assert usage.input_tokens == 74
    assert usage.output_tokens == 6
    assert usage.reasoning_tokens == 2
    assert usage.cache_read_tokens == 40
    assert usage.cache_write_tokens == 6
    assert usage.native_cost_usd is None


def test_copilot_shutdown_event_parses_all_token_buckets():
    raw = """{"type":"session.shutdown","data":{"modelMetrics":{"gpt-fixed":{"requests":{"count":2,"cost":1},"usage":{"inputTokens":120,"outputTokens":8,"reasoningTokens":2,"cacheReadTokens":40,"cacheWriteTokens":6}}}}}
"""
    usage = parse_usage(raw)
    assert usage.input_tokens == 120
    assert usage.output_tokens == 8
    assert usage.reasoning_tokens == 2
    assert usage.cache_read_tokens == 40
    assert usage.cache_write_tokens == 6
    assert usage.native_cost_usd is None


def test_opencode_fixture_parses_tokens_but_zero_cost_is_unknown():
    raw = '{"type":"step_finish","part":{"tokens":{"input":100,"output":20,"reasoning":5,"cache":{"read":12,"write":3}},"cost":0}}'
    usage = parse_usage(raw)
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.reasoning_tokens == 5
    assert usage.cache_read_tokens == 12
    assert usage.cache_write_tokens == 3
    assert usage.native_cost_usd is None
def test_opencode_info_log_exposes_resolved_identity():
    raw = (
        "message=stream providerID=openai modelID=gpt-5.4-mini "
        "session.id=fixture small=false agent=build\n"
    )
    assert extract_identity(raw) == ("openai", "gpt-5.4-mini")
