# Watch failure isolation

Precondition: health troubleshooting completed and no deployment is in progress. Internal HMAC and
public capability keys are independent; never route the internal listener through Cloudflare.

```sh
curl --fail --max-time 3 http://127.0.0.1:9010/health/ready
sudo systemctl show watch-web -p ActiveState -p Result
sudo systemctl restart watch-web
curl --fail --max-time 3 http://127.0.0.1:9011/health/ready
```

Postcondition: Discord process remained alive; Watch repository lease/stale cleanup completed before
public admission; signed loopback resumes without an in-process shared object. Restart intentionally
closes old Watch sessions under PHASE 6 semantics. Do not change hostname, forwarding rules, trust
headers or capability policy to bypass errors. Real public route/TLS/browser smoke is Phase 9.
