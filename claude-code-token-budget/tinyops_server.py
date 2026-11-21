#!/usr/bin/env python3
"""Minimal MCP stdio server (no deps). argv[1] = how many tools to expose."""
import json, sys

TOOLS = [
 ("query_logs", "Search application logs for one service within a time window. Returns at most `limit` matching lines, newest first, each with timestamp, pod name and level. Use this before guessing at a cause; prefer narrow windows because wide windows are slow and truncated.",
  {"service": ("string", "Service name as registered in the deploy catalog, e.g. checkout-api"), "query": ("string", "Substring or regular expression to match against the log message"), "since_minutes": ("integer", "How far back to search, default 30, max 1440"), "level": ("string", "Minimum level: debug, info, warn or error"), "limit": ("integer", "Maximum lines to return, default 100")}),
 ("get_deploy_status", "Show the current rollout state of a service: desired and ready replicas, image tag, the last three revisions with their authors and timestamps, and whether a rollout is in progress or stuck.",
  {"service": ("string", "Service name"), "environment": ("string", "staging or production")}),
 ("list_alerts", "List alerts that are currently firing or were resolved within the window. Each alert includes rule name, severity, labels, start time and a link to the dashboard panel that triggered it.",
  {"severity": ("string", "Filter by severity: critical, warning or info"), "service": ("string", "Only alerts whose service label matches"), "include_resolved": ("boolean", "Also return alerts resolved in the last hour")}),
 ("restart_service", "Perform a rolling restart of every pod of a service. This is disruptive for single-replica services; the tool refuses production restarts unless `confirm` is exactly the service name.",
  {"service": ("string", "Service name"), "environment": ("string", "staging or production"), "confirm": ("string", "Must equal the service name for production")}),
 ("get_metrics", "Fetch a time series for a predefined metric of a service (request rate, error rate, p50/p95/p99 latency, CPU, memory). Returns points at the given step plus min, max and average.",
  {"service": ("string", "Service name"), "metric": ("string", "One of rps, error_rate, latency_p50, latency_p95, latency_p99, cpu, memory"), "since_minutes": ("integer", "Window size, default 60"), "step_seconds": ("integer", "Resolution, default 60")}),
 ("describe_incident", "Return the full record of an incident: timeline entries, affected services, current status, commander, linked alerts and the draft postmortem if one exists.",
  {"incident_id": ("string", "Incident identifier such as INC-1234")}),
 ("search_runbooks", "Full-text search over the team's runbooks. Returns the title, path and best-matching paragraph of each hit so you can decide which runbook to open.",
  {"query": ("string", "Words to search for"), "max_results": ("integer", "Default 5")}),
 ("create_ticket", "Open a ticket in the ops queue with a title, body and priority. Returns the ticket id. Use for follow-up work, not for paging people.",
  {"title": ("string", "One-line summary"), "body": ("string", "Markdown description including evidence"), "priority": ("string", "p1, p2, p3 or p4"), "service": ("string", "Service the ticket is about")}),
 ("get_oncall", "Show who is on call right now and next for a rotation, including handover time and escalation contacts.",
  {"rotation": ("string", "Rotation name, e.g. platform-primary")}),
 ("rollback_release", "Roll a service back to a previous revision. Without `revision`, rolls back one step. Returns the new rollout id; follow it with get_deploy_status.",
  {"service": ("string", "Service name"), "environment": ("string", "staging or production"), "revision": ("integer", "Target revision number, optional"), "reason": ("string", "Why, recorded in the audit log")}),
]
N = int(sys.argv[1]) if len(sys.argv) > 1 else len(TOOLS)
REQ = {"service", "query", "incident_id", "title", "rotation", "metric"}

def schema(params):
    props = {k: {"type": t, "description": d} for k, (t, d) in params.items()}
    return {"type": "object", "properties": props, "required": [k for k in params if k in REQ]}

def tools():
    return [{"name": n, "description": d, "inputSchema": schema(p)} for n, d, p in TOOLS[:N]]

for line in sys.stdin:
    if not line.strip():
        continue
    msg = json.loads(line)
    mid, method = msg.get("id"), msg.get("method")
    if mid is None:
        continue
    if method == "initialize":
        res = {"protocolVersion": msg["params"].get("protocolVersion", "2025-06-18"),
               "capabilities": {"tools": {}}, "serverInfo": {"name": "tinyops", "version": "0.1"}}
    elif method == "tools/list":
        res = {"tools": tools()}
    elif method == "tools/call":
        res = {"content": [{"type": "text", "text": json.dumps({"tool": msg["params"]["name"], "ok": True, "note": "dummy data"})}]}
    elif method == "ping":
        res = {}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}), flush=True)
