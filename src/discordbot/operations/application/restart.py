"""Strict normal restart and one evidence-gated same-code recovery, no restore."""
from discordbot.operations.ports.restart import RestartCleanupUnconfirmed, RestartOutcome, RestartPort


class Restart:
    """The CLI holds the existing kernel operation lock for this whole sequence.

    A prior online backup never excuses failed stopped preservation. Recovery
    needs a fresh stopped checkpoint and its independent restore/hash validation.
    There is no release activation, data restore, force kill or retry loop.
    """
    def __init__(self, port: RestartPort) -> None:
        self.port = port
        self.outcome: RestartOutcome | None = None

    def run(self) -> RestartOutcome:
        p = self.port
        stage, disturbed = 'audit', False
        try:
            p.audit('started', 'checkpoint')
            stage = 'preflight'; p.preflight()
            stage = 'compatibility'; p.compatible()
            stage = 'backup'
            online = p.checkpoint(); p.verify_checkpoint(online)
            stage = 'stop'; disturbed = True; p.stop()
            stage = 'checkpoint'
            p.quiescent(); p.compatible()
            stopped = p.checkpoint(); p.verify_checkpoint(stopped)
            p.quiescent()
            stage = 'start'; p.start()
            stage = 'readiness'; p.ready()
            stage = 'smoke'; p.smoke()
        except BaseException as original:
            recovery, recovery_stage, healthy = 'not_needed', 'not_needed', False
            control = original if not isinstance(original, Exception) else None
            if disturbed:
                recovery, recovery_stage = 'failed', 'stop'
                try:
                    p.stop_for_recovery()
                    recovery_stage = 'compatibility'; p.compatible()
                    recovery_stage = 'backup'
                    fresh = p.checkpoint(); p.verify_checkpoint(fresh)
                    recovery_stage = 'quiescence'; p.quiescent()
                    recovery_stage = 'start'; p.start()
                    recovery_stage = 'readiness'; p.ready()
                    recovery_stage = 'smoke'; p.smoke()
                except BaseException as recovery_error:
                    if isinstance(recovery_error, RestartCleanupUnconfirmed):
                        recovery, recovery_stage = 'failed_stop_unconfirmed', 'owned_cleanup'
                    if control is None and not isinstance(recovery_error, Exception):
                        control = recovery_error
                    try:
                        p.stop_for_recovery()
                    except BaseException as cleanup_error:
                        recovery = 'failed_stop_unconfirmed'
                        if control is None and not isinstance(cleanup_error, Exception):
                            control = cleanup_error
                else:
                    recovery, recovery_stage, healthy = 'ok', 'complete', True
            audit_failed = False
            try:
                p.audit('failed', stage + '_' + recovery)
            except BaseException as audit_error:
                audit_failed = True
                if control is None and not isinstance(audit_error, Exception):
                    control = audit_error
            self.outcome = RestartOutcome('failed', stage, recovery, recovery_stage, healthy, audit_failed)
            if control is not None:
                raise control
            return self.outcome
        # An audit failure after verified recovery/health must not stop a healthy
        # service pair merely to repeat the operation or its already-known work.
        try:
            p.audit('ok', 'complete')
        except BaseException as error:
            self.outcome = RestartOutcome('failed', 'audit', healthy=True, audit_failed=True)
            if not isinstance(error, Exception):
                raise
            return self.outcome
        self.outcome = RestartOutcome('ok', 'complete', healthy=True)
        return self.outcome
