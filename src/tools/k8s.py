import subprocess

from langchain_core.tools import tool

NS = "otel-demo"


def _get_pod_name(service_name: str) -> str:
    """Resolve the first pod name for a given otel-demo service component label."""
    result = subprocess.run(
        [
            "kubectl", "get", "pods", "-n", NS,
            "-l", f"app.kubernetes.io/component={service_name}",
            "-o", "jsonpath={.items[0].metadata.name}",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip()


def _run(cmd: list[str]) -> str:
    """Run a command and return combined stdout+stderr, or an error string."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = (result.stdout + result.stderr).strip()
        return output if output else "Command produced no output."
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
    except Exception as e:
        return f"Error ({type(e).__name__}): {e}"


@tool
def get_pod_status(service_name: str) -> str:
    """Get the running status, readiness, and restart count of pods for the given service."""
    return _run([
        "kubectl", "get", "pods", "-n", NS,
        "-l", f"app.kubernetes.io/component={service_name}",
    ])


@tool
def get_pod_logs(service_name: str, tail: int = 50) -> str:
    """Fetch the most recent log lines from the primary pod of the given service."""
    pod = _get_pod_name(service_name)
    if not pod:
        return f"No pod found for service '{service_name}' in namespace {NS}."
    return _run(["kubectl", "logs", "-n", NS, pod, f"--tail={tail}"])


@tool
def describe_pod(service_name: str) -> str:
    """Describe the primary pod for the given service, showing resource limits, events, and container state."""
    pod = _get_pod_name(service_name)
    if not pod:
        return f"No pod found for service '{service_name}' in namespace {NS}."
    return _run(["kubectl", "describe", "pod", "-n", NS, pod])


@tool
def get_pod_env(service_name: str) -> str:
    """List all environment variables from inside the primary pod of the given service to discover configured dependency addresses."""
    pod = _get_pod_name(service_name)
    if not pod:
        return f"No pod found for service '{service_name}' in namespace {NS}."
    return _run(["kubectl", "exec", "-n", NS, pod, "--", "env"])


@tool
def check_dns(service_name: str, target_host: str) -> str:
    """Perform a DNS lookup for target_host from within the primary pod of the given service."""
    pod = _get_pod_name(service_name)
    if not pod:
        return f"No pod found for service '{service_name}' in namespace {NS}."
    result = _run(["kubectl", "exec", "-n", NS, pod, "--", "nslookup", target_host])
    if "not found" in result.lower() or "nslookup: not found" in result.lower():
        result = _run(["kubectl", "exec", "-n", NS, pod, "--", "getent", "hosts", target_host])
    if "not found" in result.lower() or "getent: not found" in result.lower():
        result = _run(["kubectl", "exec", "-n", NS, pod, "--", "dig", "+short", target_host])
    return result


@tool
def check_http_connectivity(service_name: str, url: str) -> str:
    """Check HTTP connectivity to a URL from within the primary pod of the given service."""
    pod = _get_pod_name(service_name)
    if not pod:
        return f"No pod found for service '{service_name}' in namespace {NS}."
    result = _run(["kubectl", "exec", "-n", NS, pod, "--", "wget", "-qO-", "--spider", url])
    if "not found" in result.lower() or "wget: not found" in result.lower():
        result = _run(["kubectl", "exec", "-n", NS, pod, "--", "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url])
    if "not found" in result.lower() or "curl: not found" in result.lower():
        result = _run(["kubectl", "exec", "-n", NS, pod, "--", "python3", "-c",
                       f"import urllib.request; r=urllib.request.urlopen('{url}',timeout=5); print(r.status)"])
    return result


@tool
def check_tcp_connectivity(service_name: str, host: str, port: int) -> str:
    """Check TCP connectivity to host:port from within the primary pod of the given service."""
    pod = _get_pod_name(service_name)
    if not pod:
        return f"No pod found for service '{service_name}' in namespace {NS}."
    result = _run(["kubectl", "exec", "-n", NS, pod, "--", "nc", "-z", "-w5", host, str(port)])
    if "not found" in result.lower() or "nc: not found" in result.lower():
        result = _run(["kubectl", "exec", "-n", NS, pod, "--", "bash", "-c",
                       f"(echo >/dev/tcp/{host}/{port}) 2>/dev/null && echo 'open' || echo 'closed'"])
    return result


@tool
def ping_host(service_name: str, target_host: str) -> str:
    """Ping a target host from within the primary pod of the given service to check basic network reachability."""
    pod = _get_pod_name(service_name)
    if not pod:
        return f"No pod found for service '{service_name}' in namespace {NS}."
    return _run(["kubectl", "exec", "-n", NS, pod, "--", "ping", "-c3", "-W2", target_host])


K8S_TOOLS = [
    get_pod_status,
    get_pod_logs,
    describe_pod,
    get_pod_env,
    check_dns,
    check_http_connectivity,
    check_tcp_connectivity,
    ping_host,
]
