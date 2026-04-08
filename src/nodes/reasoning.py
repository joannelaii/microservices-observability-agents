import json
import re
import uuid
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from .prompts import REASONING_AGENT_SYSTEM_PROMPT
from common.state import DiagnosticState
from common.util import llm, usage_update
from tools.sop import retrieve_sop
from tools.telemetry import get_relevant_telemetry

_REASONING_TOOLS = [retrieve_sop, get_relevant_telemetry]
_MAX_FILTERED_BYTES = 40_000
_CODING_TASK_RE = re.compile(r"^CODING_TASK:\s*(.+)$", re.MULTILINE)
_DEFAULT_TRACE_KEYS = {
    "service.name",
    "http.method",
    "http.url",
    "http.status_code",
    "rpc.service",
    "rpc.method",
    "rpc.grpc.status_code",
    "exception.message",
    "grpc.error_message",
    "code.function.name",
    "code.line.number",
}
_DEFAULT_LOG_KEYS = {"labels", "line"}

def run_reasoning_node(state: DiagnosticState) -> DiagnosticState:
    reasoning_messages = list(state.get("reasoning_messages") or [])
    step_count = int(state.get("reasoning_step_count", 0) or 0)
    sop_content = state.get("sop_content") or state.get("sop_guidance") or "No SOP available."
    code_analysis = state.get("code_analysis") or ""
    code_update = f"""
## Code Analysis Update
{code_analysis}

Use this new evidence in the next step of diagnosis.
""".strip()

    if not reasoning_messages:
        reasoning_messages = [
            SystemMessage(content=REASONING_AGENT_SYSTEM_PROMPT),
            HumanMessage(
                content=f"""
## Alarm Context
Service reported in alert: {state.get("service_name", "unknown")}
Trace ID from alert: {state.get("trace_id", "N/A")}
Start time: {state.get("start_time", "N/A")}
End time: {state.get("end_time", "N/A")}
Incident type: {(state.get("triage_metadata") or {}).get("incident_type", "unknown")}
Severity: {(state.get("triage_metadata") or {}).get("severity", "unknown")}

## Initial Telemetry Snapshot
{state.get("telemetry", "N/A")}

## SOP Document
{sop_content}

## Code Analysis
{state.get("code_analysis", "N/A")}

If Start time and End time are available, use those exact values in telemetry tool calls.
If only a Trace ID is available, use a trace_id-only telemetry tool call and do not invent timestamps.
If a Trace ID is provided, investigate that exact trace instead of searching for unrelated candidate traces.
If the affected service is known, always include service in telemetry tool calls.
If the incident appears latency-related, pass problem_type="latency" to telemetry.
If the incident appears error-related, pass problem_type="error" to telemetry.
"""
            ),
        ]
    has_code_update = any(
        isinstance(msg, HumanMessage) and str(msg.content).strip() == code_update
        for msg in reasoning_messages
    )

    if code_analysis and not has_code_update:
        reasoning_messages.append(
            HumanMessage(
                content=code_update
            )
        )

    has_sop = sop_content != "No SOP available."
    has_sop_tool_result = any(
        isinstance(msg, ToolMessage) and getattr(msg, "name", "") == "retrieve_sop"
        for msg in reasoning_messages
    )

    if not has_sop and not has_sop_tool_result:
        query = (
            state.get("diagnostic_plan")
            or f"Investigate incident affecting service {state.get('service_name', 'unknown')}"
        )
        tool_call = {
            "id": str(uuid.uuid4()),
            "name": "retrieve_sop",
            "args": {"query": query},
        }
        response = AIMessage(content="", tool_calls=[tool_call])
        print("tool_calls:", response.tool_calls)
        return {
            "reasoning_messages": reasoning_messages + [response],
            "reasoning_step_count": step_count + 1,
        }

    reasoning_llm = llm.bind_tools(_REASONING_TOOLS)
    response = reasoning_llm.invoke(reasoning_messages)

    print("tool_calls:", response.tool_calls)
    text = str(response.content or "")
    match = _CODING_TASK_RE.search(text)
    coding_task = match.group(1).strip() if match else None

    updates: DiagnosticState = {
        "reasoning_messages": reasoning_messages + [response],
        "reasoning_step_count": step_count + 1,
        "coding_task": coding_task,
        **usage_update(state, response),
    }

    if not response.tool_calls:
        updates["reasoning_output"] = text
        upper = text.upper()
        updates["root_cause_found"] = "VERDICT: ROOT_CAUSE_FOUND" in upper

    return updates


class FieldSelection(BaseModel):
    trace_keys: List[str] = Field(default_factory=list)
    log_keys: List[str] = Field(default_factory=list)


def _parse_json(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except Exception:
            return None
    if isinstance(content, list):
        text_parts: List[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            else:
                text_parts.append(str(item))
        try:
            return json.loads("".join(text_parts))
        except Exception:
            return None
    return content if isinstance(content, (dict, list)) else None


def _trace_keys(data: dict[str, Any]) -> List[str]:
    keys: set[str] = set()
    for trace_entry in data.get("traces", {}).get("traces", []):
        trace = trace_entry.get("trace", {}) or {}
        for batch in trace.get("batches", []):
            for attr in batch.get("resource", {}).get("attributes", []):
                key = attr.get("key")
                if key:
                    keys.add(str(key))
            for scope_spans in batch.get("scopeSpans", []):
                for span in scope_spans.get("spans", []):
                    for attr in span.get("attributes", []):
                        key = attr.get("key")
                        if key:
                            keys.add(str(key))
                    for event in span.get("events", []):
                        for attr in event.get("attributes", []):
                            key = attr.get("key")
                            if key:
                                keys.add(str(key))
    return sorted(keys)


def _log_keys(data: dict[str, Any]) -> List[str]:
    keys: set[str] = set()
    for trace_log in data.get("logs", {}).get("trace_logs", []):
        for entry in trace_log.get("entries", []):
            for key in entry.keys():
                if key != "ts_ns":
                    keys.add(str(key))
    return sorted(keys)


def _attr_value(value: dict[str, Any] | None) -> Any:
    if not value:
        return None
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return value["intValue"]
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "arrayValue" in value:
        vals = value.get("arrayValue", {}).get("values", [])
        return [_attr_value(v) for v in vals]
    return value


def _attr_map(attrs: List[dict[str, Any]], keep: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for attr in attrs:
        key = attr.get("key")
        if key in keep:
            out[str(key)] = _attr_value(attr.get("value"))
    return out


def _compact_status(status: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if status.get("code"):
        out["code"] = status["code"]
    if status.get("message"):
        out["message"] = status["message"]
    return out


def _compact_events(events: List[dict[str, Any]], keep: set[str]) -> List[dict[str, Any]]:
    out: List[dict[str, Any]] = []
    for event in events:
        item: dict[str, Any] = {}
        if event.get("name"):
            item["name"] = event["name"]
        if event.get("timeUnixNano"):
            item["timeUnixNano"] = event["timeUnixNano"]

        attrs = _attr_map(event.get("attributes", []), keep)
        if attrs:
            item["attributes"] = attrs

        if item:
            out.append(item)
    return out


def _filter_traces(data: dict[str, Any], keep: set[str]) -> dict[str, Any]:
    out = {"traces": {"traces": []}}

    for trace_entry in data.get("traces", {}).get("traces", []):
        compact_entry: dict[str, Any] = {
            "trace_id": trace_entry.get("trace_id"),
        }
        if trace_entry.get("durationMs") is not None:
            compact_entry["durationMs"] = trace_entry.get("durationMs")

        spans: List[dict[str, Any]] = []
        trace = trace_entry.get("trace", {}) or {}
        for batch in trace.get("batches", []):
            resource_attrs = _attr_map(
                batch.get("resource", {}).get("attributes", []),
                keep,
            )

            for scope_spans in batch.get("scopeSpans", []):
                scope = scope_spans.get("scope", {}) or {}
                for span in scope_spans.get("spans", []):
                    item: dict[str, Any] = {}

                    if scope.get("name"):
                        item["scope"] = scope["name"]
                    if span.get("name"):
                        item["name"] = span["name"]
                    if span.get("kind"):
                        item["kind"] = span["kind"]
                    if span.get("startTimeUnixNano"):
                        item["startTimeUnixNano"] = span["startTimeUnixNano"]
                    if span.get("endTimeUnixNano"):
                        item["endTimeUnixNano"] = span["endTimeUnixNano"]
                    if span.get("durationMs") is not None:
                        item["durationMs"] = span["durationMs"]

                    status = _compact_status(span.get("status", {}) or {})
                    if status:
                        item["status"] = status

                    attrs = _attr_map(span.get("attributes", []), keep)
                    if attrs:
                        item["attributes"] = attrs

                    if resource_attrs:
                        item["resource"] = resource_attrs

                    events = _compact_events(span.get("events", []), keep)
                    if events:
                        item["events"] = events

                    spans.append(item)

        compact_entry["spans"] = spans
        out["traces"]["traces"].append(compact_entry)

    return out


def _filter_logs(data: dict[str, Any], keep: set[str]) -> dict[str, Any]:
    filtered = {"logs": {"trace_logs": []}}
    for trace_log in data.get("logs", {}).get("trace_logs", []):
        trimmed_log: dict[str, Any] = {"trace_id": trace_log.get("trace_id")}
        if "error" in trace_log:
            trimmed_log["error"] = trace_log.get("error")
        entries = trace_log.get("entries", [])
        trimmed_entries: List[dict[str, Any]] = []
        for entry in entries:
            trimmed_entry = {"ts_ns": entry.get("ts_ns")}
            for key in keep:
                if key in entry:
                    trimmed_entry[key] = entry[key]
            trimmed_entries.append(trimmed_entry)
        trimmed_log["entries"] = trimmed_entries
        filtered["logs"]["trace_logs"].append(trimmed_log)
    return filtered


def _filter_payload(data: dict[str, Any], trace_keep: set[str], log_keep: set[str]) -> dict[str, Any]:
    filtered = {
        key: json.loads(json.dumps(value))
        for key, value in data.items()
        if key not in {"traces", "logs"}
    }

    if "traces" in data:
        filtered.update(_filter_traces(data, trace_keep))
    if "logs" in data:
        filtered.update(_filter_logs(data, log_keep))

    return filtered


def _payload_bytes(data: dict[str, Any]) -> int:
    return len(json.dumps(data).encode("utf-8"))


def _is_error_span(span: dict[str, Any]) -> bool:
    status = span.get("status", {}) or {}
    code = str(status.get("code", "")).upper()
    if code and code not in {"STATUS_CODE_OK", "STATUS_CODE_UNSET"}:
        return True

    attrs = span.get("attributes", {}) or {}
    for key in ("http.status_code", "http.response.status_code", "rpc.grpc.status_code"):
        val = attrs.get(key)
        if val is None:
            continue
        text = str(val)
        if key == "rpc.grpc.status_code":
            if text not in {"0", ""}:
                return True
        else:
            try:
                if int(text) >= 400:
                    return True
            except Exception:
                pass

    return any(event.get("name") == "exception" for event in span.get("events", []))


def _trim_payload(data: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    trimmed = json.loads(json.dumps(data))
    if _payload_bytes(trimmed) <= max_bytes:
        return trimmed

    for trace_entry in trimmed.get("traces", {}).get("traces", []):
        spans = trace_entry.get("spans", [])
        trace_entry["spans"] = [span for span in spans if _is_error_span(span)] or spans[:10]
    if _payload_bytes(trimmed) <= max_bytes:
        return trimmed

    for trace_entry in trimmed.get("traces", {}).get("traces", []):
        for span in trace_entry.get("spans", []):
            span.pop("events", None)
    if _payload_bytes(trimmed) <= max_bytes:
        return trimmed

    for trace_log in trimmed.get("logs", {}).get("trace_logs", []):
        trace_log["entries"] = trace_log.get("entries", [])[:10]
    if _payload_bytes(trimmed) <= max_bytes:
        return trimmed

    for trace_entry in trimmed.get("traces", {}).get("traces", []):
        trace_entry["spans"] = trace_entry.get("spans", [])[:10]
    return trimmed


def run_filter_node(state: DiagnosticState) -> DiagnosticState:
    print("\n[FILTER]")
    msgs = list(state.get("reasoning_messages") or [])
    if not msgs:
        print("no messages")
        return {}

    end = len(msgs)
    start = end
    while start > 0 and isinstance(msgs[start - 1], ToolMessage):
        start -= 1

    if start == end:
        print("last message not ToolMessage")
        return {}

    batch = msgs[start:end]
    if start == 0 or not isinstance(msgs[start - 1], AIMessage):
        print("tool batch missing parent AIMessage")
        return {}

    replacements: List[ToolMessage] = []
    saw_telemetry = False

    for msg in batch:
        if getattr(msg, "name", "") != "get_relevant_telemetry":
            continue

        saw_telemetry = True
        data = _parse_json(msg.content)
        if not isinstance(data, dict):
            print("telemetry JSON parse failed")
            continue

        original_bytes = _payload_bytes(data)
        target_bytes = min(_MAX_FILTERED_BYTES, max(25_000, original_bytes // 4))
        t_keys = _trace_keys(data)
        l_keys = _log_keys(data)

        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Return valid JSON only with this schema:\n"
                        '{"trace_keys": ["..."], "log_keys": ["..."]}\n'
                        "Do not include markdown or extra text."
                    )
                ),
                HumanMessage(
                    content=f"""
Select only the most useful telemetry fields for debugging incidents.
Prefer service/protocol/error/code context.
Avoid business or app-domain-specific keys unless essential.
Reduce the payload aggressively when needed.

Original telemetry size: {original_bytes} bytes
Target filtered size: at most {target_bytes} bytes

Trace attribute keys:
{json.dumps(t_keys)}

Log keys:
{json.dumps(l_keys)}
"""
                ),
            ]
        )
        selected = FieldSelection.model_validate_json(str(response.content or "{}"))

        trace_keep = set(selected.trace_keys)
        log_keep = set(selected.log_keys)
        if not trace_keep and t_keys:
            trace_keep = {key for key in t_keys if key in _DEFAULT_TRACE_KEYS}
        if not log_keep and l_keys:
            log_keep = {key for key in l_keys if key in _DEFAULT_LOG_KEYS}

        filtered = _filter_payload(data, trace_keep, log_keep)
        filtered = _trim_payload(filtered, target_bytes)
        filtered_json = json.dumps(filtered)

        print(
            f"telemetry bytes: original={original_bytes} "
            f"reduced={len(filtered_json.encode('utf-8'))}"
        )

        replacements.append(
            ToolMessage(
                content=filtered_json,
                tool_call_id=msg.tool_call_id,
                name=msg.name,
                id=msg.id,
            )
        )
        state = {**state, **usage_update(state, response)}

    if not saw_telemetry:
        print("no telemetry tool output in batch")
        return {}
    return {
        "reasoning_messages": replacements,
        "meta_input_tokens": int(state.get("meta_input_tokens", 0) or 0),
        "meta_output_tokens": int(state.get("meta_output_tokens", 0) or 0),
        "meta_total_tokens": int(state.get("meta_total_tokens", 0) or 0),
    }
