"""Best-effort phase hints, separate from durable evidence and backend results."""

import os


PROGRESS_FD = "EVOFOX_BLAZE_PROGRESS_FD"
PHASES = {
    "validating": "Checking mouse",
    "reading": "Reading settings",
    "backup": "Saving backup",
    "writing": "Writing settings",
    "verifying": "Verifying settings",
    "activating": "Sending activation sequence",
    "checking": "Checking saved result",
}


def event_phase(event, fields):
    if event in ("state_feature_intent", "button_feature_intent", "shortcut_block_begin", "get_feature_intent"):
        return "verifying" if fields.get("phase") == "verify" else "reading"
    if event in ("config_write_intent", "button_write_intent", "shortcut_write_begin"):
        return "writing"
    if event == "activation_begin":
        return "activating"
    return None


class PhaseReporter:
    def __init__(self):
        try:
            self.fd = int(os.environ[PROGRESS_FD])
        except (KeyError, ValueError):
            self.fd = None
        if self.fd is not None and not 3 <= self.fd <= 0x7fffffff:
            self.fd = None
        self.previous = None

    def report(self, phase):
        if self.fd is None or phase not in PHASES or phase == self.previous:
            return
        self.previous = phase
        try:
            os.write(self.fd, (phase + "\n").encode("ascii"))
        except OSError:
            # A lost UI must not interrupt or retry a device transaction.
            self.fd = None


class OperationProgress:
    """Main-loop delivery with a per-operation token to reject late callbacks."""

    def __init__(self, overlays):
        self.overlays = overlays
        self.token = None

    def start(self):
        from gi.repository import GLib
        token = self.token = object()
        self._deliver(token, "validating")

        def progress(phase):
            if phase in PHASES:
                GLib.idle_add(self._deliver, token, phase)
        return progress

    def _deliver(self, token, phase):
        if self.token is token:
            self._update(phase)
        return False

    def _update(self, phase):
        for overlay in self.overlays():
            overlay.set_phase(phase)

    def finish(self, *, checking=False):
        self.token = None
        if checking:
            self._update("checking")
