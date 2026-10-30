"""Run offline unittest cases on an authenticated, private virtual X display.

Use --xvfb /path/to/a/trusted/Xvfb. No packages, input hooks, desktop events or
system configuration are installed. Only the child display process is stopped.
"""

import argparse
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import tempfile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xvfb", type=Path, required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    arguments = args.arguments
    if arguments[:1] == ["--"]:
        arguments = arguments[1:]
    if not args.xvfb.is_file():
        parser.error("Select an existing trusted Xvfb executable")
    with tempfile.TemporaryDirectory(prefix="evofox-display-", dir="/tmp/opencode") as temporary:
        root = Path(temporary)
        auth = root / "authority"
        part = lambda value: struct.pack("!H", len(value)) + value
        fd = os.open(auth, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(struct.pack("!H", 65535) + part(b"") + part(b"")
                         + part(b"MIT-MAGIC-COOKIE-1") + part(secrets.token_bytes(16)))
        read_fd, write_fd = os.pipe()
        with (root / "server.log").open("w") as log:
            server = subprocess.Popen([str(args.xvfb.resolve()), "-displayfd", str(write_fd),
                                       "-screen", "0", "1600x1200x24", "-nolisten", "tcp", "-auth", str(auth)],
                                      pass_fds=(write_fd,), stdout=log, stderr=log)
            os.close(write_fd)
            try:
                display = os.read(read_fd, 32).decode().strip()
                if not display.isdecimal():
                    raise RuntimeError("Private display failed: " + (root / "server.log").read_text())
                env = dict(os.environ, DISPLAY=f":{display}", XAUTHORITY=str(auth),
                           GDK_BACKEND="x11", TMPDIR="/tmp/opencode")
                return subprocess.run([sys.executable, "-m", "unittest",
                                       *(arguments or ["discover", "-s", "tests", "-v"])], env=env).returncode
            finally:
                os.close(read_fd)
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    raise SystemExit(main())
