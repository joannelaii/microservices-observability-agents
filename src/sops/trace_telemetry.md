# Trace Telemetry Investigation Instructions

## Keywords
trace investigation, trace ID, distributed tracing, span analysis, trace lookup, OpenTelemetry, Jaeger, Tempo, trace not found, missing trace

Use these instructions whenever `trace_id` is provided.

## Goal
Retrieve trace-focused telemetry and report whether data exists for the requested trace in the requested time window.

## Required Inputs
- `trace_id`: Trace identifier provided by user.
- `time_window`: Time range string (for example `20m`, `1h`).
- `service_name`: Optional service filter when available.

## Telemetry Tool Expectations
- Query traces first using `trace_id`.
- Query trace-correlated logs for the same `trace_id` and time range.
- Include metrics only when they add context for service-level impact.

## Validation Behavior
- If trace lookup returns no trace, explicitly state: trace ID not found.
- If trace exists but logs are empty, explicitly state: no trace-correlated logs found.
- If both trace and logs are missing, explicitly state: no telemetry found for this trace ID in the selected window.

## Output Requirements
- Keep output concise and action-oriented.
- Include whether each data source had results: traces, logs, metrics.
- Include clear next-step recommendation (for example: widen time window, verify correct environment, confirm trace propagation).
