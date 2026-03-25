#!/usr/bin/env python3
"""GPU reservation scheduler — polls GitHub Issues, manages GPU access, notifies Teams.

Runs on the GPU machine (heliosr). Polls for new gpu-request issues every POLL_INTERVAL
seconds, processes claim/release/status commands, and posts notifications to Teams
via Incoming Webhook.

Usage:
    # Run continuously (default 30s poll interval)
    python3 scripts/gpu_scheduler.py

    # Custom poll interval
    python3 scripts/gpu_scheduler.py --interval 15

    # Single poll (for cron)
    python3 scripts/gpu_scheduler.py --once

    # With Teams webhook
    export TEAMS_WEBHOOK_URL="https://outlook.webhook.office.com/..."
    python3 scripts/gpu_scheduler.py

Environment:
    TEAMS_WEBHOOK_URL  — Teams Incoming Webhook URL (optional, skip Teams if unset)
    GITHUB_REPO        — repo to poll (default: sunway513/project-dashboard)
    GPU_LEASE_HOURS    — max lease duration before auto-release (default: 4)
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "gpu-usage" / "state.json"
HISTORY_FILE = ROOT / "data" / "gpu-usage" / "history.json"

REPO = os.environ.get("GITHUB_REPO", "sunway513/project-dashboard")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")
GPU_LEASE_HOURS = int(os.environ.get("GPU_LEASE_HOURS", "4"))
POLL_INTERVAL = 30  # seconds, overridable via --interval


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state():
    """Load current reservation state."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "gpu": "mi450",
        "hostname": "heliosr",
        "owner": None,
        "claimed_at": None,
        "expires_at": None,
        "workload": None,
        "issue_number": None,
        "queue": [],
    }


def save_state(state):
    """Save reservation state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def append_history(entry):
    """Append an event to the history log."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE) as f:
            history = json.load(f)
    history.append(entry)
    # Keep last 500 entries
    if len(history) > 500:
        history = history[-500:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


# ---------------------------------------------------------------------------
# GPU health check (local)
# ---------------------------------------------------------------------------

def get_gpu_info():
    """Get GPU status from the local machine."""
    info = {"available": True, "details": ""}

    # Try rocm-smi
    try:
        result = subprocess.run(
            ["rocm-smi", "--showuse", "--showmemuse", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            info["rocm_smi"] = data
            info["details"] = result.stdout.strip()
            return info
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    # Fallback: basic rocm-smi without JSON
    try:
        result = subprocess.run(
            ["rocm-smi"], capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            info["details"] = result.stdout.strip()
            return info
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    info["details"] = "rocm-smi not available"
    return info


def get_logged_in_users():
    """Check who is currently logged into the machine."""
    try:
        result = subprocess.run(
            ["who"], capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def get_gpu_processes():
    """Check for GPU-related processes."""
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5,
        )
        gpu_keywords = ["python", "pytorch", "vllm", "triton", "rocm", "hip"]
        lines = []
        for line in result.stdout.split("\n"):
            if any(kw in line.lower() for kw in gpu_keywords):
                lines.append(line.strip())
        return "\n".join(lines[:20])  # limit output
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


# ---------------------------------------------------------------------------
# GitHub API helpers (via gh CLI)
# ---------------------------------------------------------------------------

def gh_api(endpoint, method="GET", data=None):
    """Call GitHub API via gh CLI."""
    cmd = ["gh", "api", endpoint, "--method", method]
    if data:
        for key, value in data.items():
            cmd.extend(["-f", f"{key}={value}"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except subprocess.CalledProcessError as e:
        print(f"  gh api error: {e.stderr.strip()}", file=sys.stderr)
        return {}
    except json.JSONDecodeError:
        return {}


def get_open_gpu_issues():
    """Get open issues with gpu-request label, oldest first."""
    issues = gh_api(
        f"/repos/{REPO}/issues?labels=gpu-request&state=open&sort=created&direction=asc&per_page=20"
    )
    if isinstance(issues, list):
        return issues
    return []


def comment_and_close(issue_number, body):
    """Comment on an issue and close it."""
    gh_api(
        f"/repos/{REPO}/issues/{issue_number}/comments",
        method="POST",
        data={"body": body},
    )
    gh_api(
        f"/repos/{REPO}/issues/{issue_number}",
        method="PATCH",
        data={"state": "closed"},
    )


def comment_issue(issue_number, body):
    """Comment on an issue without closing."""
    gh_api(
        f"/repos/{REPO}/issues/{issue_number}/comments",
        method="POST",
        data={"body": body},
    )


# ---------------------------------------------------------------------------
# Teams notification
# ---------------------------------------------------------------------------

def notify_teams(message):
    """Post a message to Teams via Incoming Webhook (Adaptive Card format)."""
    if not TEAMS_WEBHOOK_URL:
        return
    try:
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": message,
                                "wrap": True,
                                "weight": "Bolder",
                                "size": "Medium",
                            }
                        ],
                    },
                }
            ],
        }
        payload = json.dumps(card)
        subprocess.run(
            ["curl", "-sS", "-H", "Content-Type: application/json",
             "-d", payload, TEAMS_WEBHOOK_URL],
            capture_output=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        print("  Teams webhook timeout", file=sys.stderr)


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

def parse_duration(text):
    """Parse duration string like '2h', '30m', '1h30m' into timedelta."""
    if not text:
        return timedelta(hours=GPU_LEASE_HOURS)

    text = text.strip().lower()
    hours = 0
    minutes = 0

    h_match = re.search(r"(\d+)\s*h", text)
    m_match = re.search(r"(\d+)\s*m", text)

    if h_match:
        hours = int(h_match.group(1))
    if m_match:
        minutes = int(m_match.group(1))

    if hours == 0 and minutes == 0:
        # Try plain number as hours
        try:
            hours = int(text)
        except ValueError:
            hours = GPU_LEASE_HOURS

    # Cap at max lease
    total = timedelta(hours=hours, minutes=minutes)
    max_lease = timedelta(hours=GPU_LEASE_HOURS)
    if total > max_lease:
        total = max_lease

    return total


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def handle_claim(issue, state):
    """Process a GPU claim request."""
    user = issue["user"]["login"]
    issue_num = issue["number"]
    body = issue.get("body", "") or ""

    # Parse duration from issue body
    duration_match = re.search(r"Estimated duration\s*\n\s*(.+)", body)
    duration_str = duration_match.group(1).strip() if duration_match else ""
    duration = parse_duration(duration_str)

    # Parse workload
    workload_match = re.search(r"Workload description\s*\n\s*(.+)", body)
    workload = workload_match.group(1).strip() if workload_match else "not specified"

    now = datetime.now(timezone.utc)
    expires = now + duration
    expires_str = expires.strftime("%Y-%m-%dT%H:%M:%SZ")
    duration_display = f"{int(duration.total_seconds() // 3600)}h{int((duration.total_seconds() % 3600) // 60)}m"

    # Check if already owned
    if state["owner"]:
        # Check if lease expired
        if state["expires_at"]:
            exp = datetime.fromisoformat(state["expires_at"].replace("Z", "+00:00"))
            if now > exp:
                # Auto-release expired lease
                old_owner = state["owner"]
                append_history({
                    "event": "auto_release",
                    "user": old_owner,
                    "timestamp": now_iso(),
                    "reason": "lease_expired",
                })
                notify_teams(f"**GPU auto-released** — {old_owner}'s lease expired")
                state["owner"] = None
            else:
                # GPU is busy, add to queue
                queue_entry = {"user": user, "issue_number": issue_num,
                               "workload": workload, "duration": duration_str,
                               "queued_at": now_iso()}

                # Don't double-queue
                if not any(q["user"] == user for q in state["queue"]):
                    state["queue"].append(queue_entry)
                    save_state(state)

                position = next(
                    (i + 1 for i, q in enumerate(state["queue"]) if q["user"] == user),
                    len(state["queue"]),
                )
                remaining = exp - now
                remaining_str = f"{int(remaining.total_seconds() // 3600)}h{int((remaining.total_seconds() % 3600) // 60)}m"

                msg = (
                    f"**GPU is busy**\n\n"
                    f"| | |\n|---|---|\n"
                    f"| Current owner | @{state['owner']} |\n"
                    f"| Time remaining | {remaining_str} |\n"
                    f"| Your queue position | #{position} |\n\n"
                    f"You'll be notified when the GPU is available."
                )
                comment_and_close(issue_num, msg)
                notify_teams(
                    f"**GPU queue** — @{user} is #{position} in queue "
                    f"(current: @{state['owner']}, {remaining_str} left)"
                )
                return state

    # GPU is free — assign it
    state["owner"] = user
    state["claimed_at"] = now_iso()
    state["expires_at"] = expires_str
    state["workload"] = workload
    state["issue_number"] = issue_num
    save_state(state)

    append_history({
        "event": "claim",
        "user": user,
        "timestamp": now_iso(),
        "expires_at": expires_str,
        "workload": workload,
        "issue_number": issue_num,
    })

    gpu_info = get_gpu_info()
    users_online = get_logged_in_users()

    msg = (
        f"**GPU assigned to @{user}**\n\n"
        f"| | |\n|---|---|\n"
        f"| Duration | {duration_display} |\n"
        f"| Expires | {expires_str} |\n"
        f"| Workload | {workload} |\n"
        f"| Queue | {len(state['queue'])} waiting |\n\n"
    )
    if users_online:
        msg += f"**Users currently logged in:**\n```\n{users_online}\n```\n"

    comment_and_close(issue_num, msg)
    notify_teams(
        f"**GPU claimed** by @{user}\n"
        f"Duration: {duration_display} | Workload: {workload}"
    )
    return state


def handle_release(issue, state):
    """Process a GPU release."""
    user = issue["user"]["login"]
    issue_num = issue["number"]
    body = issue.get("body", "") or ""

    # Parse notes
    notes_match = re.search(r"Notes \(optional\)\s*\n\s*(.+)", body)
    notes = notes_match.group(1).strip() if notes_match else ""

    if state["owner"] != user:
        msg = f"**No active reservation for @{user}**"
        if state["owner"]:
            msg += f"\n\nGPU is currently held by @{state['owner']}"
        comment_and_close(issue_num, msg)
        return state

    # Release
    claimed_at = state.get("claimed_at", "")
    duration_used = ""
    if claimed_at:
        start = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
        used = datetime.now(timezone.utc) - start
        hours = int(used.total_seconds() // 3600)
        minutes = int((used.total_seconds() % 3600) // 60)
        duration_used = f"{hours}h{minutes}m"

    append_history({
        "event": "release",
        "user": user,
        "timestamp": now_iso(),
        "claimed_at": claimed_at,
        "duration_used": duration_used,
        "notes": notes,
    })

    state["owner"] = None
    state["claimed_at"] = None
    state["expires_at"] = None
    state["workload"] = None
    state["issue_number"] = None

    # Notify next in queue
    next_user_msg = ""
    if state["queue"]:
        next_entry = state["queue"][0]
        next_user_msg = f"\n\n**Next in queue:** @{next_entry['user']} — please create a new claim issue."
        notify_teams(
            f"**GPU released** by @{user} (used {duration_used})\n"
            f"**Next up:** @{next_entry['user']} — create a claim issue now!"
        )
        state["queue"].pop(0)
    else:
        notify_teams(f"**GPU released** by @{user} (used {duration_used}) — GPU is now **free**")

    save_state(state)

    msg = (
        f"**GPU released by @{user}**\n\n"
        f"| | |\n|---|---|\n"
        f"| Duration used | {duration_used} |\n"
        f"| Notes | {notes or 'none'} |"
        f"{next_user_msg}"
    )
    comment_and_close(issue_num, msg)
    return state


def handle_status(issue, state):
    """Report current GPU status."""
    issue_num = issue["number"]

    gpu_info = get_gpu_info()
    users_online = get_logged_in_users()
    gpu_procs = get_gpu_processes()

    if state["owner"]:
        exp = datetime.fromisoformat(state["expires_at"].replace("Z", "+00:00"))
        remaining = exp - datetime.now(timezone.utc)
        if remaining.total_seconds() > 0:
            remaining_str = f"{int(remaining.total_seconds() // 3600)}h{int((remaining.total_seconds() % 3600) // 60)}m"
        else:
            remaining_str = "EXPIRED"

        msg = (
            f"**GPU Status: RESERVED**\n\n"
            f"| | |\n|---|---|\n"
            f"| Owner | @{state['owner']} |\n"
            f"| Since | {state['claimed_at']} |\n"
            f"| Expires | {state['expires_at']} |\n"
            f"| Time remaining | {remaining_str} |\n"
            f"| Workload | {state.get('workload', 'n/a')} |\n"
            f"| Queue | {len(state['queue'])} waiting |\n"
        )
    else:
        msg = "**GPU Status: FREE**\n\nNo active reservation. Create a **GPU Claim** issue to reserve.\n"

    if state["queue"]:
        msg += "\n**Queue:**\n"
        for i, q in enumerate(state["queue"]):
            msg += f"{i + 1}. @{q['user']} (queued {q['queued_at']})\n"

    if users_online:
        msg += f"\n**Users logged in:**\n```\n{users_online}\n```\n"

    if gpu_procs:
        msg += f"\n**GPU-related processes (top 20):**\n```\n{gpu_procs}\n```\n"

    comment_and_close(issue_num, msg)
    return state


# ---------------------------------------------------------------------------
# Lease expiry check
# ---------------------------------------------------------------------------

def check_expired_leases(state):
    """Auto-release expired leases."""
    if not state["owner"] or not state["expires_at"]:
        return state

    exp = datetime.fromisoformat(state["expires_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)

    if now > exp:
        old_owner = state["owner"]
        claimed_at = state.get("claimed_at", "")
        duration_used = ""
        if claimed_at:
            start = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
            used = now - start
            hours = int(used.total_seconds() // 3600)
            minutes = int((used.total_seconds() % 3600) // 60)
            duration_used = f"{hours}h{minutes}m"

        append_history({
            "event": "auto_release",
            "user": old_owner,
            "timestamp": now_iso(),
            "claimed_at": claimed_at,
            "duration_used": duration_used,
            "reason": "lease_expired",
        })

        state["owner"] = None
        state["claimed_at"] = None
        state["expires_at"] = None
        state["workload"] = None
        state["issue_number"] = None

        next_msg = ""
        if state["queue"]:
            next_entry = state["queue"][0]
            next_msg = f"\nNext up: @{next_entry['user']}"
            state["queue"].pop(0)

        save_state(state)
        notify_teams(
            f"**GPU auto-released** — @{old_owner}'s {duration_used} lease expired{next_msg}"
        )
        print(f"  Auto-released expired lease for {old_owner}")

    return state


# ---------------------------------------------------------------------------
# Git push usage data
# ---------------------------------------------------------------------------

def push_usage_data():
    """Commit and push gpu-usage data to the repo."""
    try:
        subprocess.run(
            ["git", "-C", str(ROOT), "add", "data/gpu-usage/"],
            capture_output=True, check=True,
        )
        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--cached", "--quiet"],
            capture_output=True,
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "-C", str(ROOT), "commit", "-m", "data: update gpu-usage state"],
                capture_output=True, check=True,
            )
            subprocess.run(
                ["git", "-C", str(ROOT), "push"],
                capture_output=True, check=True,
            )
            print("  Pushed gpu-usage data")
    except subprocess.CalledProcessError as e:
        print(f"  Git push failed: {e.stderr}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def get_issue_labels(issue):
    """Get label names from an issue."""
    return [l["name"] for l in issue.get("labels", [])]


def process_issues():
    """Poll for new issues and process them."""
    state = load_state()

    # Check expired leases first
    state = check_expired_leases(state)

    issues = get_open_gpu_issues()
    if not issues:
        return

    processed = False
    for issue in issues:
        labels = get_issue_labels(issue)
        issue_num = issue["number"]
        user = issue["user"]["login"]

        # Skip pull requests that show up in issues API
        if issue.get("pull_request"):
            continue

        print(f"  Processing #{issue_num} from {user}: {labels}")

        if "claim" in labels:
            state = handle_claim(issue, state)
            processed = True
        elif "release" in labels:
            state = handle_release(issue, state)
            processed = True
        elif "status" in labels:
            state = handle_status(issue, state)
            processed = True
        else:
            # Has gpu-request but no recognized action label
            comment_and_close(
                issue_num,
                "Unrecognized GPU request. Please use one of the issue templates:\n"
                "- **GPU Claim** — reserve the GPU\n"
                "- **GPU Release** — release your reservation\n"
                "- **GPU Status** — check current status",
            )
            processed = True

    if processed:
        save_state(state)
        push_usage_data()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GPU reservation scheduler")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL,
                        help="Poll interval in seconds (default: 30)")
    parser.add_argument("--once", action="store_true",
                        help="Run once and exit (for cron)")
    args = parser.parse_args()

    print(f"GPU Scheduler starting")
    print(f"  Repo: {REPO}")
    print(f"  Teams webhook: {'configured' if TEAMS_WEBHOOK_URL else 'not set'}")
    print(f"  Max lease: {GPU_LEASE_HOURS}h")
    print(f"  State file: {STATE_FILE}")

    if args.once:
        process_issues()
        return

    print(f"  Poll interval: {args.interval}s")
    print(f"  Ctrl+C to stop\n")

    while True:
        try:
            process_issues()
        except KeyboardInterrupt:
            print("\nShutting down.")
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nShutting down.")
            break


if __name__ == "__main__":
    main()
