"""
AgentOps CLI — Command-line interface for the platform.

Commands:
  start              Start the AgentOps API server
  simulate-incident  Simulate an infrastructure incident
  approve            Approve a pending remediation plan
  status             Show platform and agent status
  dashboard          Start the web dashboard
  demo               Run a full end-to-end demonstration
"""

from __future__ import annotations

import json
import time

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from agentops.orchestrator.engine import Orchestrator, IncidentStatus

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="agentops")
def cli() -> None:
    """AgentOps — Multi-Agent Infrastructure Remediation Platform.

    Specialized AI agents coordinate via A2A protocol to detect, diagnose,
    and fix infrastructure issues with human-in-the-loop approval and
    automatic rollback safety guarantees.
    """
    pass


@cli.command()
@click.option("--host", default="0.0.0.0", help="API server host")
@click.option("--port", default=8080, help="API server port")
@click.option("--auto-approve", is_flag=True, help="Auto-approve all remediation plans")
def start(host: str, port: int, auto_approve: bool) -> None:
    """Start the AgentOps API server."""
    from agentops.api.routes import create_api_app

    console.print(Panel(
        "[bold cyan]AgentOps API Server[/bold cyan]\n\n"
        f"Host: {host}\n"
        f"Port: {port}\n"
        f"Auto-approve: {'[yellow]ON[/yellow]' if auto_approve else '[green]OFF (HITL required)[/green]'}",
        title="Starting",
        border_style="cyan",
    ))

    app = create_api_app(auto_approve=auto_approve)
    app.run(host=host, port=port, debug=False)


@cli.command("simulate-incident")
@click.option("--device", default="web-srv-01", help="Device ID")
@click.option(
    "--scenario",
    type=click.Choice(["link-down", "cpu-spike", "bgp-flap", "disk-full", "memory-leak"]),
    default="cpu-spike",
    help="Incident scenario",
)
@click.option("--auto-approve", is_flag=True, help="Auto-approve the remediation plan")
def simulate_incident(device: str, scenario: str, auto_approve: bool) -> None:
    """Simulate an infrastructure incident and process it through the pipeline."""
    # Map CLI scenario names to internal names
    scenario_map = {
        "link-down": "link_down",
        "cpu-spike": "cpu_spike",
        "bgp-flap": "bgp_flap",
        "disk-full": "disk_full",
        "memory-leak": "mem_leak",
    }
    internal_scenario = scenario_map.get(scenario, scenario)

    console.print()
    console.print(Panel(
        f"[bold red]INCIDENT SIMULATION[/bold red]\n\n"
        f"Scenario: [yellow]{scenario}[/yellow]\n"
        f"Device:   [cyan]{device}[/cyan]\n"
        f"Approval: {'[yellow]Auto[/yellow]' if auto_approve else '[green]Manual (HITL)[/green]'}",
        title="AgentOps",
        border_style="red",
    ))

    orch = Orchestrator(auto_approve=auto_approve)

    # Submit
    console.print("\n[bold]Stage 1: Incident Detection[/bold]")
    incident = orch.submit_incident(
        device_id=device,
        description=f"Simulated {scenario} on {device}",
        scenario=internal_scenario,
    )
    console.print(f"  Incident ID: [cyan]{incident.incident_id}[/cyan]")

    # Process
    console.print("\n[bold]Stage 2: Processing Pipeline[/bold]")
    with console.status("[bold cyan]Processing incident through agent pipeline..."):
        incident = orch.process_incident(incident.incident_id)

    # Display timeline
    console.print(f"\n[bold]Pipeline Result: [{_status_color(incident.status)}]{incident.status.value}[/{_status_color(incident.status)}][/bold]")

    console.print("\n[bold]Incident Timeline:[/bold]")
    for event in incident.timeline:
        color = "green" if "complete" in event["event"] or "resolved" in event["event"] else "cyan"
        details = event.get("details", {})
        detail_str = ""
        if details:
            detail_str = " — " + ", ".join(f"{k}={v}" for k, v in list(details.items())[:3])
        console.print(f"  [{color}]●[/{color}] {event['event']}{detail_str}")

    # Display remediation plan if generated
    if incident.remediation_plan:
        plan = incident.remediation_plan
        console.print(f"\n[bold]Remediation Plan: {plan.plan_id}[/bold]")
        console.print(f"  Risk Level: [{_risk_color(plan.risk_level.value)}]{plan.risk_level.value}[/{_risk_color(plan.risk_level.value)}]")
        console.print(f"  Status: {plan.status.value}")
        for step in plan.steps:
            mark = "[green]✓[/green]" if step.executed else "○"
            console.print(f"  {mark} Step {step.order}: {step.action} ({step.params.get('description', '')})")

    # Verification result
    if incident.verification_report:
        ver = incident.verification_report
        result_color = "green" if ver.overall_result.value == "passed" else "red"
        console.print(f"\n[bold]Verification: [{result_color}]{ver.overall_result.value.upper()}[/{result_color}][/bold]")
        if ver.rollback_recommended:
            console.print("  [bold red]⚠ Rollback was triggered[/bold red]")

    # If awaiting approval
    if incident.status == IncidentStatus.AWAITING_APPROVAL:
        console.print(
            f"\n[yellow]Plan is awaiting approval. Run with --auto-approve or approve via API/CLI.[/yellow]"
        )

    console.print()


@cli.command()
@click.argument("plan_id", required=False)
@click.option("--all", "approve_all", is_flag=True, help="Approve all pending plans")
def approve(plan_id: str | None, approve_all: bool) -> None:
    """Approve a pending remediation plan."""
    console.print("[yellow]Approval requires a running API server. Use the API endpoint:[/yellow]")
    console.print("  POST /api/v1/incidents/<incident_id>/approve")
    console.print("\nOr use --auto-approve with simulate-incident for demo purposes.")


@cli.command()
def status() -> None:
    """Show platform and agent status."""
    orch = Orchestrator()

    table = Table(title="Agent Status", border_style="cyan")
    table.add_column("Agent", style="bold")
    table.add_column("State")
    table.add_column("Capabilities")

    for agent in orch._agents:
        state = agent.state.value
        color = "green" if state == "active" else "yellow"
        table.add_row(
            agent.name,
            f"[{color}]{state}[/{color}]",
            ", ".join(agent.card.capabilities[:2]),
        )

    console.print(table)

    console.print(f"\n  Protocol stats: {orch.protocol.get_stats()}")
    console.print(f"  Incidents: {len(orch.incidents)}")


@cli.command()
@click.option("--host", default="0.0.0.0", help="Dashboard host")
@click.option("--port", default=8888, help="Dashboard port")
def dashboard(host: str, port: int) -> None:
    """Start the web dashboard."""
    from agentops.dashboard.app import create_dashboard_app

    console.print(Panel(
        f"[bold cyan]AgentOps Dashboard[/bold cyan]\n\n"
        f"URL: http://{host}:{port}\n"
        f"Press Ctrl+C to stop.",
        title="Dashboard",
        border_style="cyan",
    ))

    app = create_dashboard_app()
    app.run(host=host, port=port, debug=False)


@cli.command()
@click.option(
    "--scenario",
    type=click.Choice(["all", "link-down", "cpu-spike", "bgp-flap", "disk-full", "memory-leak"]),
    default="all",
    help="Which scenario to demo",
)
def demo(scenario: str) -> None:
    """Run a full end-to-end demonstration of all scenarios."""
    scenarios = {
        "link-down": ("core-rtr-01", "link_down", "Network link failure on core router"),
        "cpu-spike": ("web-srv-01", "cpu_spike", "CPU spike on web server"),
        "bgp-flap": ("core-rtr-02", "bgp_flap", "BGP session instability"),
        "disk-full": ("db-srv-01", "disk_full", "Database server disk approaching capacity"),
        "memory-leak": ("web-srv-02", "mem_leak", "Memory leak in application server"),
    }

    if scenario == "all":
        run_scenarios = list(scenarios.items())
    else:
        key = scenario
        run_scenarios = [(key, scenarios[key])]

    console.print(Panel(
        "[bold cyan]AgentOps Full Demo[/bold cyan]\n\n"
        "Running the complete multi-agent incident resolution pipeline\n"
        "with auto-approval enabled for demonstration purposes.\n\n"
        f"Scenarios: {len(run_scenarios)}",
        title="Demo Mode",
        border_style="cyan",
    ))

    orch = Orchestrator(auto_approve=True)

    results = []
    for name, (device, scen, desc) in run_scenarios:
        console.print(f"\n{'='*60}")
        console.print(f"[bold yellow]Scenario: {name}[/bold yellow]")
        console.print(f"Device: {device} | Description: {desc}")
        console.print(f"{'='*60}")

        incident = orch.submit_incident(device, desc, scen)
        incident = orch.process_incident(incident.incident_id)

        status_color = _status_color(incident.status)
        console.print(f"\n  Result: [{status_color}]{incident.status.value.upper()}[/{status_color}]")

        if incident.diagnosis_report and incident.diagnosis_report.primary_hypothesis:
            console.print(f"  Root Cause: {incident.diagnosis_report.primary_hypothesis.description}")
            console.print(f"  Confidence: {incident.diagnosis_report.confidence_level}")

        if incident.remediation_plan:
            console.print(f"  Plan: {incident.remediation_plan.plan_id} ({incident.remediation_plan.risk_level.value} risk)")

        if incident.verification_report:
            console.print(f"  Verification: {incident.verification_report.overall_result.value}")

        console.print(f"  Timeline events: {len(incident.timeline)}")

        results.append({
            "scenario": name,
            "status": incident.status.value,
            "device": device,
        })

    # Summary table
    console.print(f"\n{'='*60}")
    table = Table(title="Demo Results Summary", border_style="cyan")
    table.add_column("Scenario", style="bold")
    table.add_column("Device")
    table.add_column("Result")

    for r in results:
        color = "green" if r["status"] == "resolved" else "red"
        table.add_row(r["scenario"], r["device"], f"[{color}]{r['status']}[/{color}]")

    console.print(table)

    resolved = sum(1 for r in results if r["status"] == "resolved")
    console.print(f"\n[bold]Total: {resolved}/{len(results)} incidents resolved automatically[/bold]")
    console.print()


def _status_color(status: IncidentStatus) -> str:
    """Get Rich color for an incident status."""
    colors = {
        IncidentStatus.RESOLVED: "green",
        IncidentStatus.ROLLED_BACK: "red",
        IncidentStatus.AWAITING_APPROVAL: "yellow",
        IncidentStatus.FAILED: "red",
        IncidentStatus.ESCALATED: "magenta",
    }
    return colors.get(status, "cyan")


def _risk_color(risk: str) -> str:
    """Get Rich color for a risk level."""
    return {"low": "green", "medium": "yellow", "high": "red", "critical": "bold red"}.get(risk, "white")


if __name__ == "__main__":
    cli()
