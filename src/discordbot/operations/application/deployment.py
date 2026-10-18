"""One bounded deployment transaction, with at most one compatibility-gated rollback."""

from discordbot.operations.ports.deployment import DeploymentPort, Outcome


class Deployment:
    def __init__(self, port: DeploymentPort) -> None:
        self.port = port

    def run(self, revision: str) -> Outcome:
        p = self.port
        with p.lock():
            previous = p.current()
            release = None
            disturbed = False
            stage = "build"
            p.audit("deployment", previous.identity if previous else "none", "started", stage)
            try:
                release = p.build(revision)
                if previous is not None and release.identity == previous.identity:
                    p.preflight(release)
                    p.audit("deployment", release.identity, "ok", "unchanged")
                    return Outcome(release.identity, "ok", "unchanged")
                for stage, action in (("preflight", p.preflight), ("test", p.test),
                                      ("compatibility", p.compatible), ("backup", p.backup),
                                      ("publish", p.publish)):
                    p.audit("deployment", release.identity, "started", stage)
                    action(release)
                stage = "stop"
                # A failed stop may have stopped only one process. Recover the pair.
                disturbed = True
                p.stop()
                stage = "activate"
                p.activate(release)
                stage = "start"
                p.start()
                stage = "readiness"
                p.ready(release)
                stage = "smoke"
                p.smoke(release)
                stage = "audit"
                p.audit("deployment", release.identity, "ok", "complete")
            except BaseException as error:
                rollback = "not_needed"
                if disturbed:
                    rollback = "failed"
                    try:
                        p.stop()
                        if previous is not None:
                            p.preflight(previous)
                            p.compatible(previous)  # Never downgrade the live data automatically.
                            p.audit("rollback", previous.identity, "started", "recovery")
                            p.activate(previous)
                            p.start()
                            p.ready(previous)
                            p.smoke(previous)
                            p.audit("rollback", previous.identity, "ok", "complete")
                            rollback = "ok"
                        else:
                            rollback = "no_previous_stopped"
                    except BaseException:
                        # Do not keep a half-ready pair running after failed rollback.
                        try:
                            p.stop()
                        except BaseException:
                            rollback = "failed_stop_unconfirmed"
                        else:
                            rollback = "failed"
                identity = release.identity if release else "none"
                p.audit("deployment", identity, "failed", stage + "_" + rollback)
                if release is not None and not disturbed:
                    p.discard(release)
                if not isinstance(error, Exception):
                    raise
                return Outcome(identity, "failed", stage, rollback)
            # Cleanup failure is observable but must not undo a healthy committed release.
            try:
                p.retain(release, previous)
            except Exception:
                p.audit("retention", release.identity, "failed", "cleanup")
                return Outcome(release.identity, "ok_cleanup_failed", "retention")
            return Outcome(release.identity, "ok", "complete")
