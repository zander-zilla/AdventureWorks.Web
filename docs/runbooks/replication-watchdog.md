# Replication watchdog runbook (C2-6)

The watchdog on the Replication monitor page reads the replication status (the monitor API on AWS, recorded scenarios locally),
classifies the cause with fixed rules (`WatchRules.Classify`, src/AdventureWorks.Web/Ai/Watchdog.cs) and asks the model to explain it.
The model never decides the cause and never acts: every step below is done by a person.

## healthy
Lag under the 60 s target, empty dead-letter queue (DLQ), consumer running. Nothing to do.

## paused
The consumer was paused (`POST /api/pause`, usually for maintenance). Changes queue up and are not lost.
Resume with `POST /api/resume` when the work is done, then watch the queue drain.

## backlog
Lag is above 60 s and more than 1,000 changes are queued: a burst (bulk update, load test, catch-up after a restart).
Watch the queue drain on the monitor. If it keeps growing for 15 minutes, raise the Lambda reserved concurrency /
batch size (infra/modules/cdc) or check DMS task health.

## slow-apply
Lag is above 60 s with a short queue: each change applies slowly. Check DynamoDB throttling (CloudWatch
`ThrottledRequests`), the consumer logs for retries, and recent deploys.

## dead-letter-orphans
Child rows (for example order lines) reached the DLQ because their parent order had not replicated after 5 lookups.
Wait until the parent appears in DynamoDB, then redrive the DLQ (SQS console: *Start DLQ redrive*).

## dead-letter-queue
Changes failed for another reason (stale `src_lsn` condition, validation). Read each message's error (the watchdog shows
table, operation and a redacted error only; message bodies may hold customer data), fix the cause, then redrive.

## unavailable
The app could not read the monitor API (AWS only, `Ai__MonitorApiUrl` set). Check that the monitor API Lambda is deployed
(`enable_monitor_api`), its logs, and that the app task role has `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction` on
`<name>-monitor-api` (Terraform adds both when `enable_ai` and the monitor API are on). The watchdog does not fall back to a
recorded scenario on AWS, so it never shows "healthy" while it is blind.
