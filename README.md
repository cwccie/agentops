# AgentOps

**Multi-Agent Infrastructure Remediation Platform**

Specialized AI agents coordinate via A2A (Agent-to-Agent) protocol to detect, diagnose, and fix infrastructure issues — with human-in-the-loop approval and automatic rollback safety guarantees.

---

> *"By 2028, 40% of large enterprises will deploy agentic AI in SRE workflows, up from less than 5% in 2024."*
> — Gartner, Predicts 2025: IT Operations

AgentOps is what that future looks like: a coordinated team of purpose-built agents that handle the full incident lifecycle — from metric anomaly to verified fix — while keeping humans in control of every irreversible action.

---

## Why AgentOps?

Modern infrastructure generates thousands of alerts per day. Human operators spend 80% of their incident response time on diagnosis, not remediation. AgentOps automates the cognitive labor while preserving human judgment where it matters most.

| Without AgentOps | With AgentOps |
|---|---|
| Alert → page human → triage → diagnose → fix → verify | Alert → agents diagnose + plan fix → **human approves** → agents execute + verify |
| 30-90 min MTTR | **< 5 min MTTR** (with auto-approve) |
| Knowledge trapped in runbooks | Knowledge encoded in agent capabilities |
| Single-threaded incident response | Parallel multi-agent coordination |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Orchestrator                           │
│                  (DAG-based pipeline)                        │
│                                                             │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐ │
│   │ Monitor  │──▶│ Diagnose │──▶│Remediate │──▶│ Verify │ │
│   │  Agent   │   │  Agent   │   │  Agent   │   │ Agent  │ │
│   └──────────┘   └──────────┘   └──────────┘   └────────┘ │
│        │              │              │    ▲           │      │
│        │              │              │    │           │      │
│        ▼              ▼              ▼    │           ▼      │
│   ┌─────────┐   ┌─────────┐   ┌─────────┐    ┌─────────┐  │
│   │ Metrics │   │Evidence │   │Approval │    │Rollback │  │
│   │Threshold│   │Topology │   │  Gate   │    │ Manager │  │
│   │ Anomaly │   │  Corr.  │   │ (HITL)  │    │  (Auto) │  │
│   └─────────┘   └─────────┘   └─────────┘    └─────────┘  │
│                                                             │
│   ┌──────────────────────────────────────────────────────┐  │
│   │           A2A Protocol (Agent-to-Agent)              │  │
│   │  Agent Cards • Task Delegation • Priority Routing    │  │
│   └──────────────────────────────────────────────────────┘  │
│                                                             │
│   ┌──────────────────────────────────────────────────────┐  │
│   │              Safety Layer                            │  │
│   │  Kill Switch • Auto-Rollback • Blast Radius Limits  │  │
│   └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### The Four Agents

| Agent | Role | Capabilities |
|-------|------|-------------|
| **MonitorAgent** | Detection | Metric collection, threshold evaluation, anomaly detection (z-score), alert generation |
| **DiagnoserAgent** | Analysis | Root cause analysis, topology-aware correlation, evidence collection, hypothesis ranking |
| **RemediatorAgent** | Action | Fix generation from templates, config change proposals, rollback preparation, blast radius assessment |
| **VerifierAgent** | Validation | Post-fix metric comparison, SLA compliance checks, improvement scoring, rollback recommendation |

### A2A Protocol

Agents discover each other through **Agent Cards** — machine-readable capability declarations. The protocol handles:

- **Discovery**: Find agents by capability (`find_best_agent("root_cause_analysis")`)
- **Task Delegation**: Route work to the most capable available agent
- **Priority Routing**: Critical incidents jump the queue (P1 > P5 > P10)
- **Conversation Tracking**: Multi-message interactions maintain state
- **Broadcast**: System-wide announcements (kill signals, heartbeats)

### Safety-First Design

Every design decision prioritizes safety:

1. **Kill Switch**: Instantly halt all agents. One call pauses everything.
2. **Auto-Rollback**: If post-fix metrics don't improve within the observation window, changes are automatically reverted.
3. **HITL Approval Gate**: No remediation executes without human approval (configurable: always-require, auto-low-risk, auto-all for demos).
4. **Blast Radius Limits**: Plans exceeding the configured blast radius are automatically rejected.
5. **Audit Trail**: Every agent action, decision, and state change is logged.

## Quick Start

### Install

```bash
pip install -e .
```

### Run the Demo

See all five scenarios resolve end-to-end:

```bash
agentops demo
```

Output:
```
╭──── Demo Mode ────╮
│ AgentOps Full Demo │
│ Scenarios: 5       │
╰────────────────────╯

============================================================
Scenario: link-down
Device: core-rtr-01 | Description: Network link failure on core router
============================================================

  Result: RESOLVED
  Root Cause: Physical cable disconnected or damaged
  Confidence: high
  Plan: REM-a3f1b2c4 (high risk)
  Verification: passed

  ...

┌───────────── Demo Results Summary ──────────────┐
│ Scenario      │ Device       │ Result           │
├───────────────┼──────────────┼──────────────────┤
│ link-down     │ core-rtr-01  │ resolved         │
│ cpu-spike     │ web-srv-01   │ resolved         │
│ bgp-flap      │ core-rtr-02  │ resolved         │
│ disk-full     │ db-srv-01    │ resolved         │
│ memory-leak   │ web-srv-02   │ resolved         │
└───────────────┴──────────────┴──────────────────┘

Total: 5/5 incidents resolved automatically
```

### Simulate a Single Incident

```bash
# With human approval required (default)
agentops simulate-incident --device web-srv-01 --scenario cpu-spike

# With auto-approval for demo
agentops simulate-incident --device core-rtr-01 --scenario link-down --auto-approve
```

### Start the API Server

```bash
agentops start --port 8080
```

Then interact via REST:

```bash
# Submit an incident
curl -X POST http://localhost:8080/api/v1/incidents \
  -H "Content-Type: application/json" \
  -d '{"device_id": "web-srv-01", "scenario": "cpu_spike", "description": "High CPU"}'

# Process it
curl -X POST http://localhost:8080/api/v1/incidents/INC-xxxx/process

# Check status
curl http://localhost:8080/api/v1/status
```

### Start the Dashboard

```bash
agentops dashboard --port 8888
```

Open `http://localhost:8888` for the web interface showing agent status, incidents, approval queue, and audit trail.

### Docker

```bash
docker compose up -d
```

- API: `http://localhost:8080`
- Dashboard: `http://localhost:8888`

## Pre-Built Scenarios

| Scenario | Device | What Happens | Remediation |
|----------|--------|-------------|-------------|
| `link-down` | core-rtr-01 | Physical link failure, error rate spikes | Bounce interface, activate failover path |
| `cpu-spike` | web-srv-01 | Runaway process, response time degrades | Identify process, apply CPU limit, restart service |
| `bgp-flap` | core-rtr-02 | BGP prefixes drop, routing instability | Soft reset BGP, apply route dampening |
| `disk-full` | db-srv-01 | Disk utilization >90%, database at risk | Rotate logs, clean temp files, expand volume |
| `memory-leak` | web-srv-02 | Gradual memory increase, OOM risk | Capture heap dump, set memory limit, graceful restart |

## Testing

```bash
# Run all tests
pytest -v

# With coverage
pytest --cov=agentops --cov-report=term-missing

# Run specific test category
pytest tests/test_orchestrator.py -v
```

The test suite includes 50+ tests covering:
- Agent lifecycle and state machine transitions
- Threshold evaluation and anomaly detection
- Root cause analysis and hypothesis ranking
- Remediation plan generation, approval, execution, rollback
- Verification and SLA compliance
- A2A protocol discovery and routing
- Kill switch and safety mechanisms
- REST API endpoints
- End-to-end integration for all 5 scenarios

## Project Structure

```
agentops/
├── src/agentops/
│   ├── agents/          # Agent implementations
│   │   ├── base.py      #   Base class, Agent Card, lifecycle
│   │   ├── monitor.py   #   Metric collection, thresholds, anomaly detection
│   │   ├── diagnoser.py #   Root cause analysis, evidence, hypotheses
│   │   ├── remediator.py#   Fix plans, approval gates, rollback
│   │   └── verifier.py  #   Post-fix validation, SLA checks
│   ├── protocol/        # A2A protocol
│   │   ├── a2a.py       #   Discovery, routing, conversations
│   │   └── messages.py  #   Message types, task delegation
│   ├── orchestrator/    # Pipeline orchestration
│   │   └── engine.py    #   DAG execution, incident lifecycle
│   ├── safety/          # Safety mechanisms
│   │   ├── kill_switch.py#  Immediate halt
│   │   ├── rollback.py  #   Auto-rollback on metric degradation
│   │   └── approval.py  #   HITL approval gates
│   ├── observe/         # Observability
│   │   └── tracer.py    #   OTel tracing, decision audit, metrics
│   ├── inventory/       # Infrastructure inventory
│   │   └── registry.py  #   Devices, topology, dependencies
│   ├── api/             # REST API
│   │   └── routes.py    #   Flask API endpoints
│   ├── dashboard/       # Web dashboard
│   │   └── app.py       #   Flask dashboard with embedded templates
│   └── cli.py           # Click CLI
├── tests/               # 50+ tests
├── scenarios/           # 5 pre-built incident scenarios
├── pyproject.toml       # Project configuration
├── Dockerfile           # Container image
├── docker-compose.yml   # Multi-service deployment
└── README.md            # This file
```

## Philosophy

AgentOps is built on three convictions:

1. **Agents should be specialists, not generalists.** A monitoring agent that does one thing extremely well is more reliable than an all-purpose agent. Specialization enables composability.

2. **Safety is not a feature — it's the architecture.** Kill switches, rollback guarantees, blast radius limits, and HITL gates aren't bolted on. They're structural. Removing them would require rewriting the system.

3. **Observability is non-negotiable.** Every agent action, every decision, every state change is traced and logged. When something goes wrong (and it will), you need to reconstruct exactly what happened and why.

## License

MIT License — see [LICENSE](LICENSE)

## Author

**Corey A. Wade** — [GitHub](https://github.com/cwccie)

---

*AgentOps demonstrates the architecture and coordination patterns for multi-agent infrastructure remediation. All agent implementations use mock infrastructure for safe demonstration without requiring real devices.*
