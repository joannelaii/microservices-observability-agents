# SOP: Pod CrashLoopBackOff

## Keywords
CrashLoopBackOff, pod restart, container crash, back-off, exit code, init container failure, container restarting, pod keeps restarting

## Triggers
- Kubernetes pods repeatedly restarting
- `CrashLoopBackOff` status observed

## Checks (in order)

1. Inspect pod logs for error messages.

2. Verify container startup commands.

3. Check environment variables and configuration.

4. Confirm dependent services are reachable.

5. Verify resource limits are not exceeded.

6. Inspect recent deployments for misconfiguration.

## Immediate Mitigation

- Roll back deployment.
- Increase resource limits if resource exhaustion occurs.
- Fix configuration errors.