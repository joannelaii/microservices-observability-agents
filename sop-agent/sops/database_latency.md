# SOP: Database Latency

## Triggers
- Database query latency > SLO
- Sudden increase in DB response times

## Checks (in order)

1. Identify which queries or endpoints are causing DB load.

2. Check database metrics:
   - query latency
   - active connections
   - lock contention

3. Look for slow queries using database monitoring tools.

4. Verify connection pool configuration.

5. Check for long-running transactions.

6. Confirm database CPU and memory utilization.

## Immediate Mitigation

- Kill long-running queries.
- Increase connection pool size if saturated.
- Scale database resources temporarily.