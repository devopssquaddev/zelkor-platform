---
title: runs/wait requires assistant_id
description: POST /runs/wait returns 422 assistant_id Field required.
type: kb
sidebar_group: KB
sidebar_order: 21
audience: both
edition: ce
---

# `POST /runs/wait` returns 422 `assistant_id`

## Symptom

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "assistant_id"],
      "msg": "Field required"
    }
  ]
}
```

The JSON body has `graph_id`. The request may also send `X-Graph-ID`.

## Cause

Aegra requires `assistant_id` on `/runs/wait`. Envoy uses `X-Graph-ID` or `?graph_id=` only for routing. It does not copy those into the body.

## Confirm

Replay with the same headers and a body that includes only `graph_id`. Expect 422.

## Fix

Send both ids (same value as `X-Graph-ID`):

```bash
curl -X POST https://agents.example.com/runs/wait \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -H "X-Graph-ID: my-agent-id" \
  -d '{
    "assistant_id": "my-agent-id",
    "graph_id": "my-agent-id",
    "input": {
      "messages": [{"role": "human", "content": "hello"}]
    }
  }'
```

Or create a thread first (`POST /threads`) and pass `thread_id` with `assistant_id`.

## See also

- [Deploy an Agent](../agent-deploy.md)
- [Agent Protocol](../reference/agent-protocol.md)
