# Agent 03 — Genesis Research Agent

## Test Metadata
- **Tested:** 2026-05-23
- **Endpoint:** `POST https://swarmsync-agents.onrender.com/agents/genesis_research_x402/run`
- **Marketplace slug:** `genesis_research_x402`
- **Gateway slug:** `genesis-research` (bundle slug)

## HTTP Status
- **Full payload:** HTTP 000 (timeout — same ConduitBridge issue)
- **Short probe:** HTTP 200 (endpoint alive)
- **Earlier attempt:** HTTP 429 (throttler)

## Root Cause
`genesis-research` bundle lists `conduit`, `web_search`, `web_fetch`, and `job_mode: "async"` in tools_advertised. AgentRuntime attempts Patchright browser startup + async job queue init before LLM call. Both paths exceed Render's 30s proxy timeout. `mode: "live_test"` forces sync path (skips job queue) but does NOT bypass AgentRuntime — so browser startup still blocks.

## Issues
| Severity | Issue |
|----------|-------|
| Critical | Same ConduitBridge startup timeout as Builder |
| Medium | `job_mode: "async"` means this agent was designed for async polling — testing with sync calls will always time out even after the fix |

## Recommended Fix
1. Apply `mode: "live_test"` bypass to all agents in main.py
2. For research/async agents: expose a `GET /agents/{slug}/jobs/{jobId}` polling endpoint and test via that flow

## Scores
- **Execution score: 0/5**
- **Routing score: 0/5**

## Verdict
**ENDPOINT LIVE BUT NOT EXECUTING** (ConduitBridge timeout + async job mode)
