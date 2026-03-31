# SOP: Response Abort

## Triggers
- HTTP client receives incomplete response or connection reset.
- Upstream proxy/gateway returns 502 Bad Gateway, 504 Gateway Timeout.
- Log entries showing "broken pipe", "connection reset by peer", "timeout", or "client abort".
- Ingress/load balancer logs indicate upstream request failures mid-stream.
- Application logs show context canceled or request aborted errors.

## Checks (in order)
1. Inspect application logs for request‑specific errors, especially around the time of abort.
2. Review proxy/ingress logs (e.g., Nginx, Envoy, HAProxy) for upstream connection failures, timeouts, or client disconnects.
3. Verify timeout configurations:
   - Proxy/load balancer: `proxy_read_timeout`, `proxy_connect_timeout`, `keepalive_timeout`.
   - Ingress controller: annotation‑based timeouts.
   - Application server: connection timeouts, idle timeouts.
4. Check network stability between client, proxy, and backend pods: use `tcpdump` or `kubectl exec` to test latency and packet loss.
5. Confirm backend pod resource limits: high CPU/memory pressure can cause slow responses leading to timeouts.
6. Validate that backend services are scaling appropriately under load; check pod count and request queue depths.
7. Examine load balancer settings for maximum connections, connection draining, and health check intervals.
8. Review recent changes to network policies, firewall rules, or routing that could affect connection establishment.
9. Check client behavior: large request/response bodies, streaming, or keep‑alive usage that may exceed buffer limits.
10. Inspect proxy/ingress error logs for specific upstream errors (e.g., `upstream prematurely closed connection`).

## Immediate Mitigation
- **Increase timeout values** at proxy/ingress level to allow longer processing.
- **Scale up backend replicas** to handle higher concurrency and reduce queue latency.
- **Add resource limits/requests** to prevent CPU throttling or OOM kills that slow responses.
- **Adjust buffer sizes** for headers and body in proxy configuration to accommodate larger payloads.
- **Disable or tune keep‑alive settings** if idle connections are being dropped prematurely.
- **Roll back recent configuration changes** to timeouts, network policies, or backend deployments.
- **Restart affected pods** or ingress controller pods to clear transient connection state.
- **Increase connection pool limits** if upstream connections are exhausted.
