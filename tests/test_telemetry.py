from agent_bench.telemetry import extract_identity, parse_omp_transcript, parse_usage


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


def test_omp_camelcase_cache_fields_parse_without_triple_counting():
    raw = """{"type":"message_end","message":{"role":"assistant","usage":{"input":10,"output":4,"reasoningTokens":2,"cacheRead":40,"cacheWrite":6,"totalTokens":60,"cost":{"total":0.01}}}}
{"type":"turn_end","message":{"role":"assistant","usage":{"input":10,"output":4,"reasoningTokens":2,"cacheRead":40,"cacheWrite":6,"totalTokens":60,"cost":{"total":0.01}}}}
{"type":"agent_end","messages":[{"role":"assistant","usage":{"input":10,"output":4,"reasoningTokens":2,"cacheRead":40,"cacheWrite":6,"totalTokens":60,"cost":{"total":0.01}}}]}
"""
    usage = parse_omp_transcript(raw)
    assert usage.input_tokens == 10
    assert usage.output_tokens == 2
    assert usage.reasoning_tokens == 2
    assert usage.cache_read_tokens == 40
    assert usage.cache_write_tokens == 6
    assert usage.native_cost_usd == 0.01


def test_omp_sums_each_requests_cache_buckets():
    raw = (
        '{"type":"agent_end","messages":'
        '[{"role":"assistant","usage":{"input":5,"output":1,"cacheRead":100,"cacheWrite":10}},'
        '{"role":"assistant","usage":{"input":7,"output":2,"cacheRead":260,"cacheWrite":10}}]}\n'
    )
    usage = parse_omp_transcript(raw)
    assert usage.input_tokens == 12
    assert usage.output_tokens == 3
    assert usage.cache_read_tokens == 360
    assert usage.cache_write_tokens == 20


def test_omp_includes_task_tool_subagent_usage():
    raw = (
        '{"type":"agent_end","messages":['
        '{"role":"assistant","usage":{"input":10,"output":4,"reasoningTokens":2,'
        '"cacheRead":3,"cacheWrite":1,"cost":{"total":0.01}}},'
        '{"role":"toolResult","toolName":"task","details":{"usage":'
        '{"input":20,"output":8,"reasoningTokens":3,"cacheRead":5,"cacheWrite":2,'
        '"totalTokens":38,"cost":{"total":0.02}}}}]}'
    )

    usage = parse_omp_transcript(raw)

    assert usage.input_tokens == 30
    assert usage.output_tokens == 7
    assert usage.reasoning_tokens == 5
    assert usage.cache_read_tokens == 8
    assert usage.cache_write_tokens == 3
    assert usage.native_cost_usd == 0.03


def test_omp_includes_task_usage_when_agent_end_is_missing():
    raw = """{"type":"message_end","message":{"role":"assistant","usage":{"input":10,"output":2,"cacheRead":0,"cacheWrite":0,"cost":{"total":0.01}}}}
{"type":"turn_end","message":{"role":"assistant","usage":{"input":10,"output":2,"cacheRead":0,"cacheWrite":0,"cost":{"total":0.01}}},"toolResults":[{"role":"toolResult","toolName":"task","details":{"usage":{"input":20,"output":4,"cacheRead":3,"cacheWrite":1,"totalTokens":28,"cost":{"total":0.02}}}}]}
"""

    usage = parse_omp_transcript(raw)

    assert usage.input_tokens == 30
    assert usage.output_tokens == 6
    assert usage.cache_read_tokens == 3
    assert usage.cache_write_tokens == 1
    assert usage.native_cost_usd == 0.03


def test_omp_counts_subagent_once_when_stream_replays_tool_result():
    # Real OMP streams emit message_end for every toolResult (agent-loop
    # emitToolResult) before pairing the same object into turn_end.toolResults.
    # Without agent_end, the fallback must not aggregate that replay twice.
    raw = """{"type":"message_end","message":{"role":"assistant","usage":{"input":10,"output":2,"cacheRead":0,"cacheWrite":0,"cost":{"total":0.01}}}}
{"type":"message_end","message":{"role":"toolResult","toolCallId":"call_1","toolName":"task","details":{"usage":{"input":20,"output":4,"cacheRead":3,"cacheWrite":1,"totalTokens":28,"cost":{"total":0.02}}}}}
{"type":"turn_end","message":{"role":"assistant","usage":{"input":10,"output":2,"cacheRead":0,"cacheWrite":0,"cost":{"total":0.01}}},"toolResults":[{"role":"toolResult","toolCallId":"call_1","toolName":"task","details":{"usage":{"input":20,"output":4,"cacheRead":3,"cacheWrite":1,"totalTokens":28,"cost":{"total":0.02}}}}]}
"""

    usage = parse_omp_transcript(raw)

    assert usage.input_tokens == 30
    assert usage.output_tokens == 6
    assert usage.cache_read_tokens == 3
    assert usage.cache_write_tokens == 1
    assert usage.native_cost_usd == 0.03


def test_omp_uses_message_end_once_when_agent_end_is_missing():
    raw = """{"type":"message_end","message":{"role":"assistant","usage":{"input":10,"output":4,"reasoningTokens":2,"cacheRead":40,"cacheWrite":6,"cost":{"total":0.01}}}}
{"type":"turn_end","message":{"role":"assistant","usage":{"input":10,"output":4,"reasoningTokens":2,"cacheRead":40,"cacheWrite":6,"cost":{"total":0.01}}}}
"""
    usage = parse_omp_transcript(raw)
    assert usage.input_tokens == 10
    assert usage.output_tokens == 2
    assert usage.reasoning_tokens == 2
    assert usage.cache_read_tokens == 40
    assert usage.cache_write_tokens == 6
    assert usage.native_cost_usd == 0.01


def test_omp_transcript_falls_back_to_generic_parser_without_agent_end():
    raw = '{"type":"step_finish","part":{"tokens":{"input":100,"output":20,"reasoning":5,"cache":{"read":12,"write":3}},"cost":0}}'
    usage = parse_omp_transcript(raw)
    assert usage.input_tokens == 100
    assert usage.output_tokens == 20
    assert usage.reasoning_tokens == 5
    assert usage.cache_read_tokens == 12
    assert usage.cache_write_tokens == 3
