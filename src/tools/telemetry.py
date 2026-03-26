from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
    def search(self, start_time: int, end_time: int, tags: Optional[Dict[str, str]] = None, limit: int = 20) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"start": start_time, "end": end_time, "limit": limit}
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

    def collect(
        self,
        start_time: str,
        end_time: str,
        service: str | None = None,
        trace_id: str | None = None,
        include: list[str] | None = None,
    ) -> dict:
        start_s = to_unix_seconds(start_time)
        end_s = to_unix_seconds(end_time)
        start_ns = start_s * 1_000_000_000
        end_ns = end_s * 1_000_000_000

        requested = set(include or ["metrics", "logs", "traces"])
        out: dict[str, Any] = {}
        if "metrics" in requested and trace_id is None:
            out["metrics"] = self._get_metrics(
                start_s=start_s,
                end_s=end_s,
                service=service,
            )

        if "logs" in requested:
            out["logs"] = self._get_logs(
                start_ns=start_ns,
                end_ns=end_ns,
                service=service,
                trace_id=trace_id,
            )

        if "traces" in requested:
            out["traces"] = self._get_traces(
                start_s=start_s,
                end_s=end_s,
                service=service,
                trace_id=trace_id,
            )

        return out

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
    ) -> dict:
        selector_parts = [f'k8s_namespace_name="{self.namespace}"']
        if service:
            selector_parts.append(f'service_name="{service}"')
        selector = "{" + ",".join(selector_parts) + "}"

        queries = {
            "all": selector,
            "errors": f'{selector} |= "error"',
            "exceptions": f'{selector} |= "exception"',
            "timeouts": f'{selector} |= "timeout"',
            "failures": f'{selector} |= "fail"',
            "panic": f'{selector} |= "panic"',
        }

        if trace_id:
            queries = {
                "trace_logs": f'{selector} |= "{trace_id}"'
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

    def _get_traces(
        self,
        start_s: int,
        end_s: int,
        service: str | None,
        trace_id: str | None,
    ) -> dict:
        if trace_id:
            try:
                return {"trace": self.tempo.get_trace(trace_id)}
            except Exception as e:
                return {"error": str(e)}

        tags = {}
        if service:
            tags["service.name"] = service

        try:
            matches = self.tempo.search(
                start_time=start_s,
                end_time=end_s,
                tags=tags or None,
                limit=self.max_traces if service else 10,
            )
            return {"matches": matches}
        except Exception as e:
            return {"error": str(e)}
    
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
    step=cfg.step,
    rollup_window=cfg.default_rollup_window,
)


@tool("get_relevant_telemetry")
def get_relevant_telemetry(
    start_time: str,
    end_time: str,
    service: Optional[str] = None,
    trace_id: Optional[str] = None,
    include: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Get relevant telemetry data for a service or trace ID."""
    return telemetry_service.collect(
        start_time=start_time,
        end_time=end_time,
        service=service,
        trace_id=trace_id,
        include=include,
    )