from __future__ import annotations

import os
import time
import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()


def to_unix_seconds(value):
    if isinstance(value, (int, float)):
        return int(value)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _iso_from_ns(value_ns: int) -> str:
    return datetime.fromtimestamp(value_ns / 1_000_000_000, tz=timezone.utc).isoformat()


@dataclass
class TelemetryConfig:
    loki_base_url: str
    prometheus_base_url: str
    tempo_base_url: str
    namespace: str = "otel-demo"
    timeout: int = 10
    max_log_lines: int = 200
    max_traces: int = 20
    default_rollup_window: str = "5m"
    step: str = "30s"


class HTTPClient:
    def __init__(self, base_url: str, timeout: int = 20):
        self.base_url = base_url.rstrip("/") + "/"
        self.session = requests.Session()
        self.timeout = timeout

    def get_json(self, path: str, params=None):
        url = urljoin(self.base_url, path.lstrip("/"))
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()


class LokiClient(HTTPClient):
    def query_range(self, query: str, start_ns: int, end_ns: int, limit: int, direction: str = "backward") -> List[Dict[str, Any]]:
        data = self.get_json(
            "/loki/api/v1/query_range",
            params={
                "query": query,
                "start": start_ns,
                "end": end_ns,
                "limit": limit,
                "direction": direction,
            },
        )
        return data.get("data", {}).get("result", [])

    @staticmethod
    def flatten(result: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for stream in result:
            labels = stream.get("stream", {})
            for ts, line in stream.get("values", []):
                out.append({"ts_ns": ts, "labels": labels, "line": line})
        out.sort(key=lambda x: x["ts_ns"], reverse=True)
        return out


class PrometheusClient(HTTPClient):
    def query_range(self, query: str, start_time: int, end_time: int, step: str) -> List[Dict[str, Any]]:
        data = self.get_json(
            "/api/v1/query_range",
            params={
                "query": query,
                "start": start_time,
                "end": end_time,
                "step": step,
            },
        )
        return data.get("data", {}).get("result", [])


class TempoClient(HTTPClient):
    def search(
        self,
        start_time: int,
        end_time: int,
        tags: Optional[Dict[str, str]] = None,
        limit: int = 20,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"start": start_time, "end": end_time, "limit": limit}
        if query:
            params["q"] = query
        if tags:
            for k, v in tags.items():
                params[f"tags[{k}]"] = v
        data = self.get_json("/api/search", params=params)
        return data.get("traces", data.get("data", []))

    def get_trace(self, trace_id: str) -> Dict[str, Any]:
        return self.get_json(f"/api/traces/{trace_id}")


class TelemetryService:
    def __init__(
        self,
        loki: LokiClient,
        prom: PrometheusClient,
        tempo: TempoClient,
        namespace: str = "otel-demo",
        max_log_lines: int = 200,
        max_traces: int = 20,
        step: str = "30s",
        rollup_window: str = "5m",
    ):
        self.loki = loki
        self.prom = prom
        self.tempo = tempo
        self.namespace = namespace
        self.max_log_lines = max_log_lines
        self.max_traces = max_traces
        self.step = step
        self.rollup_window = rollup_window

    def _pod_regex(self, service: str) -> str:
        return f"{service}-.*"

    def collect(
        self,
        start_time: str | None = None,
        end_time: str | None = None,
        service: str | None = None,
        trace_id: str | None = None,
        problem_type: str | None = None,
        mode: str = "full",
    ) -> dict:
        start_s: int | None = None
        end_s: int | None = None
        start_ns: int | None = None
        end_ns: int | None = None
        if start_time and end_time:
            start_s = to_unix_seconds(start_time)
            end_s = to_unix_seconds(end_time)
            start_ns = start_s * 1_000_000_000
            end_ns = end_s * 1_000_000_000

        if mode not in {"metrics", "full"}:
            raise ValueError("mode must be either 'metrics' or 'full'")

        if not trace_id and (start_s is None or end_s is None):
            raise ValueError("start_time and end_time are required unless trace_id is provided")

        out: dict[str, Any] = {}
        if mode == "metrics":
            out["metrics"] = self._get_metrics(
                start_s=start_s,
                end_s=end_s,
                service=service,
            )
            return out

        traces_result = self._get_traces(
            start_s=start_s,
            end_s=end_s,
            service=service,
            trace_id=trace_id,
            problem_type=problem_type,
        )
        out["traces"] = traces_result

        if start_ns is None or end_ns is None:
            trace_window = self._extract_trace_window(traces_result)
            if trace_window is not None:
                start_ns, end_ns = trace_window
                start_s = start_ns // 1_000_000_000
                end_s = end_ns // 1_000_000_000
                out["start_time"] = _iso_from_ns(start_ns)
                out["end_time"] = _iso_from_ns(end_ns)
        else:
            out["start_time"] = start_time
            out["end_time"] = end_time

        trace_ids = self._extract_trace_ids(traces_result)
        if start_ns is not None and end_ns is not None:
            out["logs"] = self._get_logs(
                start_ns=start_ns,
                end_ns=end_ns,
                service=service,
                trace_id=trace_id,
                trace_ids=trace_ids,
            )
        else:
            out["logs"] = {"trace_logs": []}

        return out

    def get_trace_window(self, trace_id: str) -> tuple[str | None, str | None]:
        traces_result = self._get_traces(
            start_s=None,
            end_s=None,
            service=None,
            trace_id=trace_id,
        )
        window = self._extract_trace_window(traces_result)
        if window is None:
            return None, None
        start_ns, end_ns = window
        return _iso_from_ns(start_ns), _iso_from_ns(end_ns)

    def _add_span_durations(self, trace: dict[str, Any]) -> dict[str, Any]:
        for batch in trace.get("batches", []):
            for scope_spans in batch.get("scopeSpans", []):
                for span in scope_spans.get("spans", []):
                    start_ns = span.get("startTimeUnixNano")
                    end_ns = span.get("endTimeUnixNano")
                    if start_ns is None or end_ns is None:
                        continue
                    try:
                        span["durationMs"] = round((int(end_ns) - int(start_ns)) / 1_000_000, 3)
                    except Exception:
                        continue
        return trace

    def _get_metrics(
        self,
        start_s: int,
        end_s: int,
        service: str | None,
    ) -> dict:
        step = self._compute_step(start_s, end_s)

        span_filters = [f'k8s_namespace_name="{self.namespace}"']
        if service:
            span_filters.append(f'service_name="{service}"')
        span_filter = ",".join(span_filters)

        kube_filters = [f'namespace="{self.namespace}"']
        kube_filter = ",".join(kube_filters)

        queries = {
            "request_rate": (
                f'sum by (service_name, status_code) ('
                f'rate(traces_span_metrics_calls_total{{{span_filter}}}[{self.rollup_window}]))'
            ),
            "error_rate": (
                f'sum by (service_name) ('
                f'rate(traces_span_metrics_calls_total{{{span_filter},status_code="STATUS_CODE_ERROR"}}[{self.rollup_window}]))'
            ),
            "latency_p95_ms": (
                f'histogram_quantile(0.95, sum by (le, service_name) ('
                f'rate(traces_span_metrics_duration_milliseconds_bucket{{{span_filter}}}[{self.rollup_window}])))'
            ),
            "pod_restarts": (
                f'sum by (pod, container) ('
                f'increase(kube_pod_container_status_restarts_total{{namespace="{self.namespace}"}}[15m]))'
            ),
        }

        if service:
            pod_regex = self._pod_regex(service)
            queries["cpu_usage"] = (
                f'sum by (pod) ('
                f'rate(container_cpu_usage_seconds_total{{namespace="{self.namespace}",pod=~"{pod_regex}",container!="",image!=""}}[{self.rollup_window}]))'
            )
            queries["cpu_throttling_ratio"] = (
                f'sum by (pod) ('
                f'rate(container_cpu_cfs_throttled_periods_total{{namespace="{self.namespace}",pod=~"{pod_regex}",container!=""}}[{self.rollup_window}]))'
                f' / '
                f'sum by (pod) ('
                f'rate(container_cpu_cfs_periods_total{{namespace="{self.namespace}",pod=~"{pod_regex}",container!=""}}[{self.rollup_window}]))'
            )
            queries["cpu_limits"] = (
                f'max by (pod, container) ('
                f'kube_pod_container_resource_limits{{namespace="{self.namespace}",pod=~"{pod_regex}",resource="cpu"}})'
            )
            queries["cpu_requests"] = (
                f'max by (pod, container) ('
                f'kube_pod_container_resource_requests{{namespace="{self.namespace}",pod=~"{pod_regex}",resource="cpu"}})'
            )

        out = {}
        for name, query in queries.items():
            try:
                out[name] = self.prom.query_range(query, start_s, end_s, step)
            except Exception as e:
                out[name] = {"error": str(e)}

        return out

    def _get_logs(
        self,
        start_ns: int,
        end_ns: int,
        service: str | None,
        trace_id: str | None,
        trace_ids: Optional[list[str]] = None,
    ) -> dict:
        namespace_selector = "{" + f'k8s_namespace_name="{self.namespace}"' + "}"
        service_selector_parts = [f'k8s_namespace_name="{self.namespace}"']
        if service:
            service_selector_parts.append(f'service_name="{service}"')
        service_selector = "{" + ",".join(service_selector_parts) + "}"

        if trace_id:
            return self._get_logs_for_trace_ids(
                selector=namespace_selector,
                start_ns=start_ns,
                end_ns=end_ns,
                trace_ids=[trace_id],
            )

        if trace_ids:
            return self._get_logs_for_trace_ids(
                selector=namespace_selector,
                start_ns=start_ns,
                end_ns=end_ns,
                trace_ids=trace_ids,
            )

        queries = {
            # "all": selector,
            "errors": f'{service_selector} |= "error"',
            "exceptions": f'{service_selector} |= "exception"',
            "timeouts": f'{service_selector} |= "timeout"',
            "failures": f'{service_selector} |= "fail"',
            "panic": f'{service_selector} |= "panic"',
        }

        out = {}
        for name, query in queries.items():
            try:
                log_lines = self._compute_log_lines(start_ns, end_ns, service)
                streams = self.loki.query_range(query, start_ns, end_ns, limit=log_lines)
                out[name] = self.loki.flatten(streams)
            except Exception as e:
                out[name] = {"error": str(e)}

        return out

    def _get_logs_for_trace_ids(
        self,
        selector: str,
        start_ns: int,
        end_ns: int,
        trace_ids: list[str],
    ) -> dict:
        selected_trace_ids = trace_ids[: self.max_traces]
        print(f"trace_ids for logs: {selected_trace_ids}")
        grouped_logs: List[Dict[str, Any]] = []

        for current_trace_id in selected_trace_ids:
            try:
                streams = self.loki.query_range(
                    f'{selector} | trace_id="{current_trace_id}"',
                    start_ns,
                    end_ns,
                    limit=min(10, self.max_log_lines),
                )
                grouped_logs.append(
                    {
                        "trace_id": current_trace_id,
                        "entries": self.loki.flatten(streams),
                    }
                )
            except Exception as e:
                grouped_logs.append(
                    {
                        "trace_id": current_trace_id,
                        "error": str(e),
                    }
                )

        return {"trace_logs": grouped_logs}

    def _get_traces(
        self,
        start_s: int | None,
        end_s: int | None,
        service: str | None,
        trace_id: str | None,
        problem_type: str | None = None,
    ) -> dict:
        if trace_id:
            try:
                return {
                    "traces": [
                        {
                            "trace_id": trace_id,
                            "trace": self._add_span_durations(self.tempo.get_trace(trace_id)),
                        }
                    ]
                }
            except Exception as e:
                return {"error": str(e)}

        try:
            if start_s is None or end_s is None:
                raise ValueError("start_s and end_s are required for trace search")
            query = None
            if service:
                query = f'{{resource.service.name="{service}"}}'
            matches = self.tempo.search(
                start_time=start_s,
                end_time=end_s,
                limit=max(self.max_traces, 50),
                query=query,
            )

            selected: List[Dict[str, Any]] = []
            rank_mode = (problem_type or "error").strip().lower()

            for match in matches:
                current_trace_id = match.get("traceID")
                if not current_trace_id:
                    continue

                try:
                    trace = self._add_span_durations(self.tempo.get_trace(current_trace_id))
                except Exception:
                    continue

                trace_services = set()
                has_problem = False

                for batch in trace.get("batches", []):
                    resource_service = None
                    for attr in batch.get("resource", {}).get("attributes", []):
                        if attr.get("key") == "service.name":
                            value = attr.get("value", {})
                            if "stringValue" in value:
                                resource_service = value["stringValue"]
                            elif "intValue" in value:
                                resource_service = str(value["intValue"])
                            elif "boolValue" in value:
                                resource_service = str(value["boolValue"]).lower()
                            break

                    if resource_service:
                        trace_services.add(resource_service)

                    for scope_spans in batch.get("scopeSpans", []):
                        for span in scope_spans.get("spans", []):
                            status = span.get("status", {})
                            if status.get("code") == "STATUS_CODE_ERROR":
                                has_problem = True

                            for event in span.get("events", []):
                                if event.get("name") == "exception":
                                    has_problem = True
                                    break

                            for attr in span.get("attributes", []):
                                key = attr.get("key")
                                value = attr.get("value", {})

                                if "stringValue" in value:
                                    attr_value = value["stringValue"]
                                elif "intValue" in value:
                                    attr_value = str(value["intValue"])
                                elif "boolValue" in value:
                                    attr_value = str(value["boolValue"]).lower()
                                else:
                                    continue

                                if key == "error" and attr_value == "true":
                                    has_problem = True

                                elif key in {"rpc.grpc.status_code", "grpc.status_code"} and attr_value != "0":
                                    has_problem = True

                                elif key in {"http.status_code", "http.response.status_code"}:
                                    try:
                                        if int(attr_value) >= 400:
                                            has_problem = True
                                    except Exception:
                                        pass

                                elif key in {"net.peer.name", "server.address"} and attr_value:
                                    trace_services.add(attr_value)

                if service and service not in trace_services:
                    continue

                if rank_mode == "latency" or has_problem:
                    selected.append({
                        "trace_id": current_trace_id,
                        "trace": trace,
                        "durationMs": match.get("durationMs", -1),
                    })

            selected.sort(
                key=lambda x: int(x["durationMs"]) if x["durationMs"] is not None else -1,
                reverse=True,
            )

            return {"traces": selected[:3]}

        except Exception as e:
            return {"error": str(e)}

    def _extract_trace_ids(self, traces_result: dict) -> list[str]:
        trace_ids: list[str] = []
        for trace_entry in traces_result.get("traces", []):
            trace_id = (
                trace_entry.get("trace_id")
                or trace_entry.get("traceID")
                or trace_entry.get("traceId")
            )
            if trace_id:
                trace_ids.append(trace_id)
        return trace_ids

    def _extract_trace_window(self, traces_result: dict) -> tuple[int, int] | None:
        min_start: int | None = None
        max_end: int | None = None

        for trace_entry in traces_result.get("traces", []):
            trace = trace_entry.get("trace", {}) or {}
            for batch in trace.get("batches", []):
                for scope_spans in batch.get("scopeSpans", []):
                    for span in scope_spans.get("spans", []):
                        start_raw = span.get("startTimeUnixNano")
                        end_raw = span.get("endTimeUnixNano")
                        try:
                            start_val = int(start_raw) if start_raw is not None else None
                            end_val = int(end_raw) if end_raw is not None else None
                        except Exception:
                            continue

                        if start_val is not None:
                            min_start = start_val if min_start is None else min(min_start, start_val)
                        if end_val is not None:
                            max_end = end_val if max_end is None else max(max_end, end_val)

        if min_start is None or max_end is None:
            return None

        pad_ns = 30 * 1_000_000_000
        return min_start - pad_ns, max_end + pad_ns
    
    def _compute_step(self, start_s: int, end_s: int) -> str:
        duration = end_s - start_s

        if duration <= 5 * 60:
            return "15s"
        elif duration <= 60 * 60:
            return "30s"
        else:
            return "1m"
    
    def _compute_log_lines(self, start_ns: int, end_ns: int, service: str | None) -> int:
        duration = (end_ns - start_ns) // 1_000_000_000

        if service is None:
            return 100
        if duration > 30 * 60:
            return 300
        return self.max_log_lines


cfg = TelemetryConfig(
    loki_base_url=os.environ["LOKI_BASE_URL"],
    prometheus_base_url=os.environ["PROM_BASE_URL"],
    tempo_base_url=os.environ["TEMPO_BASE_URL"],
    namespace=os.getenv("OTEL_NAMESPACE", "otel-demo"),
    timeout=int(os.getenv("TELEMETRY_TIMEOUT", "20")),
)

telemetry_service = TelemetryService(
    loki=LokiClient(cfg.loki_base_url, timeout=cfg.timeout),
    prom=PrometheusClient(cfg.prometheus_base_url, timeout=cfg.timeout),
    tempo=TempoClient(cfg.tempo_base_url, timeout=cfg.timeout),
    namespace=cfg.namespace,
    max_log_lines=cfg.max_log_lines,
    max_traces=cfg.max_traces,
    rollup_window=cfg.default_rollup_window,
)


@tool("get_relevant_telemetry")
def get_relevant_telemetry(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    service: Optional[str] = None,
    trace_id: Optional[str] = None,
    problem_type: Optional[str] = None,
    mode: str = "full",
) -> Dict[str, Any]:
    """
    Retrieve telemetry data from the observability stack for diagnosing system
    issues within a specified time window.

    It can be used for:
    - Metrics-only analysis
    - Full incident diagnosis with metrics, traces, and trace-linked logs
    - Request-level debugging (with trace_id)

    Args:
        start_time (str, optional):
            Start of the time range (ISO 8601 format, e.g. "2026-03-30T10:00:00Z").

        end_time (str, optional):
            End of the time range (ISO 8601 format).

        service (str, optional):
            Service name to filter telemetry (e.g. "payment", "frontend").
            If None, queries across all services.

        trace_id (str, optional):
            Specific trace ID to retrieve detailed trace and related logs.
            If provided:
                - Metrics will NOT be returned
                - Logs and traces will be filtered to this trace
                - start_time and end_time may be omitted

        problem_type (str, optional):
            Optional ranking hint for trace selection when searching by time window.
            Use:
                - "error" for the current error-focused ranking
                - "latency" to rank candidate traces by duration

        mode (str, optional):
            Retrieval mode. Options:
                - "metrics": return only metrics
                - "full": return metrics, relevant traces, and logs narrowed to
                  the selected trace IDs
            Defaults to "full".

    Returns:
        Dict[str, Any]:
            Dictionary containing telemetry data. Depending on mode:
            {
                "metrics": {...},
                "logs": {...},
                "traces": {...}
            }

    Notes:
        - Use broader time ranges for incident investigation.
        - Use narrower time ranges for precise debugging.
    """
    return telemetry_service.collect(
        start_time=start_time,
        end_time=end_time,
        service=service,
        trace_id=trace_id,
        problem_type=problem_type,
        mode=mode,
    )

# TEST - get all telemetry for a service in last 10 minutes
if __name__ == "__main__":
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=10)

    output = get_relevant_telemetry.invoke({
        "start_time": start_time.isoformat().replace("+00:00", "Z"),
        "end_time": end_time.isoformat().replace("+00:00", "Z"),
        "service": "checkout",
        "mode": "full",
    })
    s = json.dumps(output, default=str)
    print(output)
    print("chars: ", len(s))
