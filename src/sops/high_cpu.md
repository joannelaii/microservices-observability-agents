# SOP: High CPU Utilization

## Triggers
- CPU utilization > 80% for 5 minutes
- Sudden spike in CPU usage across multiple pods

## Checks (in order)

1. Identify affected services and pods.
   - Use Prometheus metrics: `container_cpu_usage_seconds_total`

2. Check for recent deployments or configuration changes.

3. Examine request traffic volume.
   - Determine if increased load is causing CPU saturation.

4. Inspect logs for excessive retries, loops, or expensive computations.

5. Check for inefficient queries or data processing tasks.

6. Verify autoscaling behavior.
   - Ensure HPA is functioning correctly.

## Immediate Mitigation

- Scale up replicas temporarily.
- Roll back recent deployments if correlated.
- Disable non-critical background tasks.