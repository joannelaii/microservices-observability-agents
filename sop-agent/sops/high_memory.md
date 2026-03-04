# SOP: High Memory Usage

## Triggers
- Memory utilization > 85%
- Gradual increase in memory over time without release

## Checks (in order)

1. Identify which pods or services are consuming the most memory.

2. Check memory metrics:
   - `container_memory_usage_bytes`
   - `container_memory_working_set_bytes`

3. Inspect application logs for excessive object allocations.

4. Verify whether garbage collection is occurring normally.

5. Check for large caches or in-memory data structures.

6. Compare memory usage before and after the last deployment.

## Immediate Mitigation

- Restart affected pods to reclaim memory.
- Reduce cache sizes.
- Roll back recent deployments if memory spike started after deployment.