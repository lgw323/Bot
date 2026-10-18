"""Aggregate an observed journal window; never emit message text or arbitrary fields."""

from collections import Counter
import json
import subprocess
import time

UNITS = {"watch-web.service", "discordbot-staging-discord.service", "cloudflared.service",
         "systemd-journald.service", "rsyslog.service", "discordbot-backup.service"}
EVENTS = {"task.started", "task.succeeded", "task.failed", "task.cancelled",
          "task.deadline_exceeded", "task.retrying"}
TASKS = {"server-maintenance", "telemetry-drain", "database-probe"}


def event_category(message: object) -> str:
    """Only source-defined enum labels may leave the in-memory message parser."""
    if not isinstance(message, str):
        return "other"
    try:
        value = json.loads(message)
    except (ValueError, TypeError):
        return "other"
    if not isinstance(value, dict):
        return "other"
    event, task = value.get("event"), value.get("task_name")
    if not isinstance(event, str) or event not in EVENTS:
        return "other"
    task = task if isinstance(task, str) and task in TASKS else "other"
    return event + ":" + task


def main() -> None:
    command = ["journalctl", "--since=@1789437747", "--until=@1789524148", "--no-pager", "--quiet",
               "--output=json", "--output-fields=_SYSTEMD_UNIT,PRIORITY,MESSAGE"]
    counts = Counter()
    priorities = Counter()
    events = Counter()
    started = time.monotonic()
    limited = False
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        for number, line in enumerate(process.stdout, 1):
            if number > 2_000_000 or time.monotonic() - started > 45:
                limited = True
                process.kill()
                break
            value = json.loads(line)
            unit = value.get("_SYSTEMD_UNIT", "other")
            unit = unit if isinstance(unit, str) and unit in UNITS else "other"
            priority = value.get("PRIORITY", "unknown")
            priority = priority if isinstance(priority, str) and priority in set("01234567") else "unknown"
            counts[unit] += 1
            priorities[unit + ":" + priority] += 1
            events[unit + ":" + event_category(value.get("MESSAGE"))] += 1
        code = process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
    print(json.dumps({"window": [1789437747, 1789524148], "limited": limited, "exit_code": code,
                      "unit_counts": dict(counts), "priority_counts": dict(priorities),
                      "event_counts": dict(events)}))


if __name__ == "__main__":
    main()
