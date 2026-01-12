#!/usr/bin/env python3
"""
ZenML → TRMNL Plugin
Fetches pipeline data from ZenML and pushes to TRMNL private plugin webhook.

Environment Variables:
    ZENML_SERVER_URL: ZenML server URL (required)
    ZENML_API_KEY: ZenML service account API key (required)
    ZENML_PROJECT: ZenML project name or ID (required for ZenML Cloud)
    TRMNL_WEBHOOK_URL: TRMNL webhook URL (required, unless --dry-run)
    VIEW_MODE: Display mode - recent_runs, pipelines_overview, running_only (default: recent_runs)
    DISPLAY_TIMEZONE: Timezone for timestamps (default: UTC, e.g., Europe/Berlin, America/New_York)

Usage:
    python zenml_trmnl.py              # Normal run
    python zenml_trmnl.py --dry-run    # Print payload without sending
"""

import argparse
import json
import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

# Configuration from environment variables
ZENML_SERVER_URL = os.environ.get("ZENML_SERVER_URL", "").rstrip("/")
ZENML_API_KEY = os.environ.get("ZENML_API_KEY", "")
ZENML_PROJECT = os.environ.get("ZENML_PROJECT", "default")
TRMNL_WEBHOOK_URL = os.environ.get("TRMNL_WEBHOOK_URL", "")

# Display settings
VIEW_MODE = os.environ.get("VIEW_MODE", "recent_runs")  # recent_runs, pipelines_overview, running_only
DISPLAY_TIMEZONE = os.environ.get("DISPLAY_TIMEZONE", "UTC")

# Constants
RUNS_FOR_DISPLAY = 12  # Number of runs to show in table
RUNS_FOR_STATS = 100   # Number of runs to fetch for 24h stats calculation


def get_display_tz() -> ZoneInfo:
    """Get the configured display timezone."""
    try:
        return ZoneInfo(DISPLAY_TIMEZONE)
    except Exception:
        print(f"Warning: Invalid timezone '{DISPLAY_TIMEZONE}', falling back to UTC")
        return ZoneInfo("UTC")


def get_zenml_headers() -> dict:
    """Get authorization headers for ZenML API."""
    return {
        "Authorization": f"Bearer {ZENML_API_KEY}",
        "Content-Type": "application/json",
    }


# Cache for project ID lookup
_project_id_cache: Optional[str] = None


def get_project_id() -> str:
    """Get the project ID, resolving from name if necessary.

    ZenML Cloud requires project scoping for all API calls.
    This function looks up the project by name and returns its ID.
    """
    global _project_id_cache

    if _project_id_cache is not None:
        return _project_id_cache

    # Try to find the project by name
    url = f"{ZENML_SERVER_URL}/api/v1/projects"
    params = {"name": ZENML_PROJECT}

    response = requests.get(url, headers=get_zenml_headers(), params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    items = data.get("items", [])

    if not items:
        # Maybe ZENML_PROJECT is already a UUID - try using it directly
        _project_id_cache = ZENML_PROJECT
        return _project_id_cache

    # Get the ID from the first matching project
    _project_id_cache = items[0].get("id", ZENML_PROJECT)
    print(f"Resolved project '{ZENML_PROJECT}' to ID: {_project_id_cache}")
    return _project_id_cache


def fetch_pipelines(limit: int = 20) -> list:
    """Fetch pipelines from ZenML."""
    project_id = get_project_id()
    url = f"{ZENML_SERVER_URL}/api/v1/pipelines"
    params = {
        "size": limit,
        "sort_by": "desc:updated",
        "hydrate": "true",
        "project": project_id,
    }

    response = requests.get(url, headers=get_zenml_headers(), params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    return data.get("items", [])


def fetch_runs(limit: int = RUNS_FOR_STATS, in_progress_only: bool = False) -> list:
    """Fetch pipeline runs from ZenML."""
    project_id = get_project_id()
    url = f"{ZENML_SERVER_URL}/api/v1/runs"
    params = {
        "size": limit,
        "sort_by": "desc:created",
        "hydrate": "true",
        "project": project_id,
    }

    if in_progress_only:
        params["in_progress"] = "true"

    response = requests.get(url, headers=get_zenml_headers(), params=params, timeout=30)
    response.raise_for_status()

    data = response.json()
    return data.get("items", [])


def get_status_icon(status: str) -> str:
    """Convert status to a simple text indicator for e-ink."""
    status_map = {
        "completed": "✓",
        "running": "►",
        "failed": "✗",
        "initializing": "○",
        "provisioning": "○",
        "cached": "≡",
        "stopped": "■",
        "stopping": "□",
        "retried": "↻",
    }
    return status_map.get(status, "?")


def parse_timestamp(iso_timestamp: str) -> datetime:
    """Parse an ISO timestamp, handling various formats. Always returns UTC-aware datetime."""
    # Replace Z with +00:00 for fromisoformat compatibility
    ts = iso_timestamp.replace("Z", "+00:00")

    # Parse the timestamp
    dt = datetime.fromisoformat(ts)

    # If naive (no timezone), assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def format_time_ago(iso_timestamp: Optional[str]) -> str:
    """Convert ISO timestamp to human-readable 'time ago' string."""
    if not iso_timestamp:
        return "-"

    try:
        dt = parse_timestamp(iso_timestamp)
        now = datetime.now(timezone.utc)
        diff = now - dt

        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds >= 3600:
            return f"{diff.seconds // 3600}h ago"
        elif diff.seconds >= 60:
            return f"{diff.seconds // 60}m ago"
        else:
            return "just now"
    except (ValueError, TypeError):
        return "-"


def format_duration(start: Optional[str], end: Optional[str]) -> str:
    """Calculate and format duration between two timestamps."""
    if not start:
        return "-"

    try:
        start_dt = parse_timestamp(start)

        if end:
            end_dt = parse_timestamp(end)
        else:
            end_dt = datetime.now(timezone.utc)

        diff = end_dt - start_dt
        total_seconds = int(diff.total_seconds())

        if total_seconds < 0:
            return "-"
        elif total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            return f"{total_seconds // 60}m {total_seconds % 60}s"
        else:
            hours = total_seconds // 3600
            mins = (total_seconds % 3600) // 60
            return f"{hours}h {mins}m"
    except (ValueError, TypeError):
        return "-"


def format_local_time() -> str:
    """Format current time in the configured display timezone."""
    tz = get_display_tz()
    now = datetime.now(tz)
    tz_abbrev = now.strftime("%Z") or DISPLAY_TIMEZONE
    return now.strftime(f"%H:%M {tz_abbrev}")


def get_24h_stats(runs: list) -> dict:
    """Calculate status counts for runs in the last 24 hours."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    status_counts = {
        "running": 0,
        "completed": 0,
        "failed": 0,
        "cached": 0,
        "other": 0,
    }

    for run in runs:
        # Check if run started in last 24h
        metadata = run.get("metadata", {})
        start_time_str = metadata.get("start_time")

        if start_time_str:
            try:
                start_time = parse_timestamp(start_time_str)
                if start_time < cutoff:
                    continue  # Skip runs older than 24h
            except (ValueError, TypeError):
                continue

        status = run.get("body", {}).get("status", "unknown")

        if status in status_counts:
            status_counts[status] += 1
        else:
            status_counts["other"] += 1

    return status_counts


def build_recent_runs_data(runs: list) -> dict:
    """Build merge variables for recent runs view."""
    runs_data = []

    for run in runs[:RUNS_FOR_DISPLAY]:
        body = run.get("body", {})
        metadata = run.get("metadata", {})
        resources = run.get("resources", {})

        pipeline_name = resources.get("pipeline", {}).get("name", "Unknown")
        status = body.get("status", "unknown")

        runs_data.append({
            "name": run.get("name", "Unknown")[:30],
            "pipeline": pipeline_name[:20],
            "status": status,
            "status_icon": get_status_icon(status),
            "started": format_time_ago(metadata.get("start_time")),
            "duration": format_duration(
                metadata.get("start_time"),
                metadata.get("end_time")
            ),
            "in_progress": body.get("in_progress", False),
            "is_failed": status == "failed",  # For row emphasis in markup
        })

    # Get 24h stats from all fetched runs
    stats = get_24h_stats(runs)

    return {
        "view": "recent_runs",
        "title": "Recent Pipeline Runs",
        "runs": runs_data,
        "total_runs": len(runs_data),
        "running_count": stats["running"],
        "completed_count": stats["completed"],
        "failed_count": stats["failed"],
        "cached_count": stats["cached"],
        "stats_period": "24h",
        "updated_at": format_local_time(),
    }


def build_pipelines_overview_data(pipelines: list) -> dict:
    """Build merge variables for pipelines overview."""
    pipelines_data = []

    for pipeline in pipelines[:RUNS_FOR_DISPLAY]:
        body = pipeline.get("body", {})
        latest_status = body.get("latest_run_status", "never run")

        pipelines_data.append({
            "name": pipeline.get("name", "Unknown")[:25],
            "latest_status": latest_status,
            "status_icon": get_status_icon(latest_status),
            "is_failed": latest_status == "failed",
        })

    return {
        "view": "pipelines_overview",
        "title": "Pipelines Overview",
        "pipelines": pipelines_data,
        "total_pipelines": len(pipelines),
        "updated_at": format_local_time(),
    }


def build_running_only_data(runs: list, all_runs: list) -> dict:
    """Build merge variables for currently running pipelines.

    If no runs are currently running, automatically falls back to recent_runs view.
    """
    running_runs = [r for r in runs if r.get("body", {}).get("in_progress", False)]

    # Auto-switch: if nothing running, return recent_runs view instead
    if not running_runs:
        print("No pipelines running, switching to recent_runs view")
        return build_recent_runs_data(all_runs)

    runs_data = []
    for run in running_runs[:6]:
        body = run.get("body", {})
        metadata = run.get("metadata", {})
        resources = run.get("resources", {})

        pipeline_name = resources.get("pipeline", {}).get("name", "Unknown")

        runs_data.append({
            "name": run.get("name", "Unknown")[:30],
            "pipeline": pipeline_name[:20],
            "status": body.get("status", "running"),
            "started": format_time_ago(metadata.get("start_time")),
            "duration": format_duration(metadata.get("start_time"), None),
        })

    return {
        "view": "running_only",
        "title": "Running Pipelines",
        "runs": runs_data,
        "running_count": len(running_runs),
        "updated_at": format_local_time(),
    }


def push_to_trmnl(merge_variables: dict, dry_run: bool = False) -> None:
    """Push data to TRMNL webhook."""
    payload = {"merge_variables": merge_variables}

    if dry_run:
        print("\n=== DRY RUN - Payload that would be sent ===")
        print(json.dumps(payload, indent=2, default=str))
        print(f"\nPayload size: {len(json.dumps(payload))} bytes")
        print("=== End of payload ===\n")
        return

    response = requests.post(
        TRMNL_WEBHOOK_URL,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    print(f"Successfully pushed to TRMNL: {response.status_code}")


def main():
    parser = argparse.ArgumentParser(description="Push ZenML pipeline data to TRMNL display")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload to console without sending to TRMNL"
    )
    args = parser.parse_args()

    # Validate configuration
    required_vars = [ZENML_SERVER_URL, ZENML_API_KEY]
    if not args.dry_run:
        required_vars.append(TRMNL_WEBHOOK_URL)

    if not all(required_vars):
        print("Error: Missing required environment variables:")
        print("  ZENML_SERVER_URL, ZENML_API_KEY", end="")
        if not args.dry_run:
            print(", TRMNL_WEBHOOK_URL")
        else:
            print()
        sys.exit(1)

    print(f"Fetching data from ZenML: {ZENML_SERVER_URL}")
    print(f"Project: {ZENML_PROJECT}")
    print(f"View mode: {VIEW_MODE}")
    print(f"Display timezone: {DISPLAY_TIMEZONE}")
    if args.dry_run:
        print("DRY RUN MODE - will not send to TRMNL")

    try:
        if VIEW_MODE == "pipelines_overview":
            pipelines = fetch_pipelines(limit=20)
            data = build_pipelines_overview_data(pipelines)
        elif VIEW_MODE == "running_only":
            # Fetch both in-progress and all runs for fallback
            runs_in_progress = fetch_runs(limit=20, in_progress_only=True)
            all_runs = fetch_runs(limit=RUNS_FOR_STATS, in_progress_only=False)
            data = build_running_only_data(runs_in_progress, all_runs)
        else:  # recent_runs (default)
            runs = fetch_runs(limit=RUNS_FOR_STATS)
            data = build_recent_runs_data(runs)

        print(f"Fetched data, pushing to TRMNL...")
        push_to_trmnl(data, dry_run=args.dry_run)
        print("Done!")

    except requests.exceptions.RequestException as e:
        print(f"Error communicating with API: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
