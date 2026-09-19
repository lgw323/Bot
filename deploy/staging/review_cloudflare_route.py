"""Read the current connector's config event; emit only requested routing metadata."""
import json
import re
import subprocess
from urllib.parse import urlsplit

HOST = "watch.lgw323.com"


def summarize(config: dict) -> dict:
    ingress = config.get("ingress")
    if not isinstance(ingress, list):
        raise ValueError("Ingress missing")
    targets, private = [], 0
    for rule in ingress:
        target = rule.get("service", "")
        try:
            parsed = urlsplit(target)
            port = parsed.port
        except (TypeError, ValueError):
            parsed, port = None, None
        private += int(port in {9001, 9010, 9011})
        if rule.get("hostname") == HOST:
            safe = (isinstance(target, str) and parsed is not None and parsed.scheme in {"http", "https"}
                    and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                    and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)
            targets.append(target if safe else "other_target_withheld")
    return {"hostname": HOST, "matching_route_count": len(targets), "origin_targets": targets,
            "internal_port_route_count": private, "ingress_rule_count": len(ingress)}


def main() -> None:
    invocation = subprocess.check_output(["systemctl", "show", "cloudflared", "-p", "InvocationID", "--value"], text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{32}", invocation):
        raise ValueError("Running connector invocation required")
    result = subprocess.run(["journalctl", "_SYSTEMD_INVOCATION_ID=" + invocation, "-n", "300",
                             "--no-pager", "--quiet", "--output=json", "--output-fields=MESSAGE,__REALTIME_TIMESTAMP"],
                            capture_output=True, text=True, timeout=30, check=True)
    configs = []
    for line in result.stdout.splitlines():
        row = json.loads(line)
        message = row.get("MESSAGE", "")
        if not isinstance(message, str) or "Updated to new configuration" not in message or "config=" not in message:
            continue
        raw = message.split("config=", 1)[1]
        try:
            value, _ = json.JSONDecoder().raw_decode(raw)
            config = json.loads(value) if isinstance(value, str) else value
            configs.append((config, row.get("__REALTIME_TIMESTAMP")))
        except (ValueError, TypeError):
            continue
    if not configs:
        print(json.dumps({"status": "current_configuration_event_unavailable", "configuration_events": 0}))
        return
    config, timestamp = configs[-1]
    print(json.dumps({"status": "current_invocation_last_configuration_event", "configuration_events": len(configs),
                      "event_time_unix_us": timestamp, **summarize(config)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
