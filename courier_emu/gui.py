"""Loopback-only browser console for the existing CLI workers."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import webbrowser

from .panel import FRONT_PANEL_LEDS
from .dte_framing import DTE_FRAMINGS


def parse_lamps(line):
    """Decode the panel's positional on/off/unknown wire format."""
    tokens = line.split()
    if len(tokens) != len(FRONT_PANEL_LEDS):
        return None
    states = {}
    for led, token in zip(FRONT_PANEL_LEDS, tokens):
        if token == led.name:
            states[led.name] = True
        elif token == "." * len(led.name):
            states[led.name] = False
        elif token == "?" * len(led.name):
            states[led.name] = None
        else:
            return None
    return states


class Session:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.process = None
        self.stopping = False
        self.lock = threading.RLock()
        self.output = ""
        self.log = ""
        self.image = ""
        self.connection = {"mode": "simulated"}
        self.lamps = {led.name: None for led in FRONT_PANEL_LEDS}

    def _read_lamps(self, stream, process):
        try:
            pending = b""
            while chunk := os.read(stream.fileno(), 4096):
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    states = parse_lamps(line.decode("ascii", "replace"))
                    if states is not None:
                        with self.lock:
                            if self.process is process:
                                self.lamps = states
                # A corrupt/incomplete record must not grow memory indefinitely.
                if len(pending) > 4096:
                    pending = b""
        finally:
            stream.close()

    def images(self):
        # Deliberately avoid recursively indexing dumps/artifacts.
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_file() and p.suffix.lower() in {".xmf", ".rom", ".nac"})

    def _read(self, stream, field, process):
        try:
            while chunk := os.read(stream.fileno(), 4096):
                with self.lock:
                    if self.process is process:
                        setattr(self, field, (getattr(self, field) + chunk.decode("latin-1"))[-200000:])
        finally:
            stream.close()

    def _connection_options(self, connection, analog):
        """Return argv, public state and private child-environment overrides."""
        if connection is None:
            connection = {"mode": "simulated"}
        if not isinstance(connection, dict):
            raise ValueError("Connection must be an object")
        mode = connection.get("mode", "simulated")
        fields = {
            "simulated": {"mode"},
            "sip": {"mode", "server", "username", "password", "password_env", "target", "codec",
                    "sip_port", "rtp_port"},
            "peer": {"mode", "socket", "role", "audio_only"},
            "physical": {"mode", "helper", "rate", "gain", "confirmed"},
        }
        if not isinstance(mode, str) or mode not in fields:
            raise ValueError("Invalid connection mode")
        if connection.keys() - fields[mode]:
            raise ValueError("Unexpected connection settings; choose only one backend")
        if not analog and mode != "simulated":
            raise ValueError("These line backends are for analog XMF/ROM images, not NAC")

        def text(key, default="", required=False):
            value = connection.get(key, default)
            if (not isinstance(value, str) or len(value) > 1024
                    or any(ord(c) < 32 or ord(c) == 127 for c in value)):
                raise ValueError(f"Invalid {key}")
            value = value.strip()
            if required and not value:
                raise ValueError(f"{key} is required")
            return value

        def integer(key, default, low, high):
            value = connection.get(key, default)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} must be an integer from {low} to {high}")
            return value

        options = []
        environment = {}
        # Public state contains only the chosen backend, never SIP credentials.
        public = {"mode": mode}
        if mode == "sip":
            server = text("server", required=True)
            if not re.fullmatch(r"[A-Za-z0-9_.-]+(?::[0-9]{1,5})?", server):
                raise ValueError("SIP server must be an IPv4 host/name with optional :port")
            if ":" in server and not 1 <= int(server.rsplit(":", 1)[1]) <= 65535:
                raise ValueError("Invalid SIP server port")
            env = text("password_env", "COURIER_SIP_PASSWORD", required=True)
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env):
                raise ValueError("Invalid password environment variable name")
            if "password" in connection:
                password = connection["password"]
                if (not isinstance(password, str) or len(password) > 1024
                        or any(ord(c) < 32 or ord(c) == 127 for c in password)):
                    raise ValueError("Invalid SIP password (maximum 1024 characters, no control characters)")
                try:
                    password.encode("utf-8")
                except UnicodeEncodeError:
                    raise ValueError("Invalid SIP password encoding") from None
                # Preserve whitespace and keep the value out of both CLI
                # argv layers, shared os.environ, public state and logs.
                env = "COURIER_GUI_SIP_PASSWORD"
                environment[env] = password
            codec = text("codec", "pcmu")
            if codec not in {"pcmu", "pcma"}:
                raise ValueError("Choose PCMU or PCMA")
            target = text("target")
            # SipLine replaces these two tokens, not arbitrary format expressions.
            if target and (not target.startswith("sip:")
                           or re.search(r"[{}]", target.replace("{number}", "").replace("{server}", ""))):
                raise ValueError("Target must be a sip: URI; only {number} and {server} tokens are supported")
            options = ["--sip-server", server, "--sip-username", text("username", "courier", True),
                       "--sip-password-env", env, "--sip-codec", codec,
                       "--sip-local-port", str(integer("sip_port", 0, 0, 65535)),
                       "--rtp-local-port", str(integer("rtp_port", 0, 0, 65535))]
            if target:
                options += ["--sip-target", target]
            public["server"] = server
        elif mode == "peer":
            path = Path(text("socket", required=True)).expanduser()
            path = path if path.is_absolute() else self.root / path
            from .line import MAX_SOCKET_PATH
            if len(os.fsencode(path)) > MAX_SOCKET_PATH:
                raise ValueError(f"Socket path must fit {MAX_SOCKET_PATH} bytes")
            role = text("role", "connect")
            if role not in {"listen", "connect"}:
                raise ValueError("Peer role must be listen or connect")
            if role == "listen" and os.path.lexists(path):
                raise ValueError("Socket path already exists; choose another or remove it only after both peers stop")
            if not path.parent.is_dir():
                raise ValueError("Socket parent directory does not exist")
            audio_only = connection.get("audio_only", True)
            if type(audio_only) is not bool:
                raise ValueError("audio_only must be a boolean")
            options = ["--line-link", str(path)]
            if role == "listen":
                options.append("--line-listen")
            if audio_only:
                options.append("--line-audio-only")
            public.update(socket=str(path), role=role, audio_only=audio_only)
        elif mode == "physical":
            if connection.get("confirmed") is not True:
                raise ValueError("Confirm the physical FXO hardware and powered FXS/PBX line first")
            if sys.platform != "darwin":
                raise ValueError("The Apple USB modem line bridge requires macOS")
            helper = text("helper")
            path = Path(helper).expanduser() if helper else Path(__file__).resolve().parents[1] / ".build/apple_line"
            path = (path if path.is_absolute() else self.root / path).resolve()
            if not path.is_file() or not os.access(path, os.X_OK):
                raise ValueError("Apple line helper not executable; build tools/build_apple_line.py first")
            rate = integer("rate", 10286, 7200, 10286)
            if rate not in {7200, 8000, 8229, 8400, 9000, 9600, 10286}:
                raise ValueError("Unsupported Apple hardware rate")
            gain = connection.get("gain", 1.0)
            if type(gain) not in {int, float} or not 0 <= gain <= 1:
                raise ValueError("Apple transmit gain must be from 0 to 1")
            options = ["--apple-modem", str(path), "--apple-rate", str(rate), "--apple-tx-gain", str(gain)]
            public["helper"] = str(path)
        return options, public, environment

    @staticmethod
    def _board_options(board, analog):
        if board is None:
            board = {}
        if not isinstance(board, dict) or board.keys() - {"id", "nvram_fixture", "tick_source", "dte_framing"}:
            raise ValueError("Invalid board settings")
        if not analog and board:
            raise ValueError("Analog board settings do not apply to NAC images")
        options = []
        identity = board.get("id", "auto")
        if identity not in ("auto", "none", *(str(i) for i in range(16))):
            raise ValueError("Invalid board ID")
        options += ["--board-id", identity] if analog else []
        fixture = board.get("nvram_fixture", "")
        if not isinstance(fixture, str) or fixture not in {"", "idsdl302", "idsdl403"}:
            raise ValueError("Invalid EEPROM fixture")
        if fixture:
            options += ["--nvram-fixture", fixture]
        tick = board.get("tick_source", "")
        if not isinstance(tick, str) or tick not in {"", "dsp"}:
            raise ValueError("Invalid tick source")
        if tick:
            options += ["--tick-source", tick]
        framing = board.get("dte_framing", "8N1")
        if framing not in DTE_FRAMINGS:
            raise ValueError("Invalid DTE framing")
        if analog:
            options += ["--dte-framing", framing]
        return options

    def start(self, image, dsp=False, line="disconnected", connection=None, board=None):
        with self.lock:
            if self.stopping:
                raise ValueError("Wait for the current session to stop")
            if self.process is not None and self.process.poll() is None:
                raise ValueError("Stop the current session first")
            if image not in self.images():
                raise ValueError("Choose a firmware image from the list")
            if not isinstance(line, str) or line not in {"disconnected", "quiet", "dial-tone", "ringing"}:
                raise ValueError("Invalid line state")
            path = self.root / image
            analog = path.suffix.lower() != ".nac"
            options, public, environment = self._connection_options(connection, analog)
            board_options = self._board_options(board, analog)
            needs_dsp = dsp or public["mode"] != "simulated" or (analog and line != "disconnected")
            command = [sys.executable, "-u", "-m", "courier_emu"]
            if not analog:
                command += ["isdn-run", str(path), "--terminal"]
            else:
                command += ["run", str(path), "--console", "--summary"]
                if public["mode"] == "simulated" and needs_dsp:
                    # Even --daa-line disconnected implies DSP in the CLI.
                    # Omit it when the user explicitly wants no DSP attached.
                    command += ["--daa-line", line]
                command += options + board_options
            if needs_dsp:
                command.append("--with-dsp")
            self.output = self.log = ""
            self.lamps = {led.name: None for led in FRONT_PANEL_LEDS}
            self.image = image
            self.connection = public
            lamps_read = lamps_write = None
            if path.suffix.lower() != ".nac":
                lamps_read, lamps_write = os.pipe()
                command += ["--lamps-fd", str(lamps_write)]
            try:
                self.process = subprocess.Popen(
                    command, cwd=self.root, env={**os.environ, **environment} if environment else None,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    pass_fds=() if lamps_write is None else (lamps_write,),
                    start_new_session=True, bufsize=0)
            except BaseException:
                if lamps_read is not None:
                    os.close(lamps_read)
                raise
            finally:
                if lamps_write is not None:
                    os.close(lamps_write)
            if lamps_read is not None:
                threading.Thread(target=self._read_lamps,
                                 args=(os.fdopen(lamps_read, "rb"), self.process),
                                 daemon=True).start()
            for stream, field in [(self.process.stdout, "output"), (self.process.stderr, "log")]:
                threading.Thread(target=self._read, args=(stream, field, self.process), daemon=True).start()

    def send(self, text):
        if not isinstance(text, str) or len(text) > 4096:
            raise ValueError("Command must be at most 4096 characters")
        try:
            data = (text + "\r").encode("latin-1")
        except UnicodeEncodeError:
            raise ValueError("The serial terminal supports Latin-1 characters only") from None
        self._send_bytes(data)

    def _send_bytes(self, data):
        if b"\x1d" in data:
            raise ValueError("Use Stop to detach")
        with self.lock:
            if self.stopping:
                raise ValueError("Session is stopping")
            if self.process is None or self.process.poll() is not None:
                raise ValueError("Start the modem first")
            self.process.stdin.write(data)
            self.process.stdin.flush()

    def call(self, action, number=""):
        with self.lock:
            if self.image.lower().endswith(".nac"):
                raise ValueError("Call controls currently support analog XMF/ROM sessions only")
            if action == "dial":
                if (not isinstance(number, str) or not re.fullmatch(r"[0-9*#+,Ww!@ -]{1,64}", number)
                        or not re.search(r"[0-9*#]", number)):
                    raise ValueError("Enter a phone number (up to 64 dial characters, no AT commands)")
                self.send("ATDT" + number.replace(" ", "").replace("-", ""))
            elif action == "answer":
                self.send("ATA")
            elif action == "hangup":
                self.send("ATH")
            elif action == "escape":
                # No CR: +++ is an escape sequence, not an AT command. The
                # browser provides idle guard time; firmware still owns S12.
                self._send_bytes(b"+++")
            else:
                raise ValueError("Invalid call action")

    def stop(self):
        with self.lock:
            process = self.process
            if process is None or self.stopping:
                return
            self.stopping = True
            analog = not self.image.lower().endswith(".nac")
            physical = self.connection["mode"] == "physical"
        # Never hold the reader lock while waiting: a final report larger
        # than a pipe buffer would deadlock the CLI and force a needless kill.
        try:
            graceful = False
            if analog and process.poll() is None:
                try:
                    # Normal detach lets EOF stop the worker, close the line,
                    # release hardware hook and print the final diagnostics.
                    process.stdin.write(b"\x1d")
                    process.stdin.flush()
                    process.wait(timeout=12)
                    graceful = True
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if not graceful:
                # Include descendants even if the CLI itself already exited.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=3)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass
                if physical:
                    # Allow the helper's hook-release handler time even if
                    # its parent exits first. SIGKILL cannot release hook.
                    time.sleep(3)
                    with self.lock:
                        self.log += "\nForced shutdown: verify the physical line is on-hook; unplug the modem if necessary.\n"
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        finally:
            try:
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
            except OSError:
                pass
            with self.lock:
                self.stopping = False

    def state(self):
        with self.lock:
            code = self.process.poll() if self.process else None
            return {"running": self.process is not None and code is None,
                    "exit_code": code, "image": self.image, "stopping": self.stopping,
                    "connection": dict(self.connection),
                    "output": self.output, "log": self.log,
                    "lamps": dict(self.lamps)}


def serve(root: Path, port=8765, open_browser=True):
    session = Session(root)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type="application/json"):
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            # Require a per-launch token; no CORS, cookies, or query-string auth.
            return secrets.compare_digest(self.headers.get("X-Courier-Token", ""), token)

        def do_GET(self):
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                return self.reply(403, {"error": "Invalid host"})
            if self.path == "/":
                html = Path(__file__).with_name("gui.html").read_text()
                return self.reply(200, html.replace("__TOKEN__", token), "text/html; charset=utf-8")
            if not self.authorized():
                return self.reply(403, {"error": "Unauthorized"})
            if self.path == "/api/state":
                return self.reply(200, session.state())
            if self.path == "/api/images":
                return self.reply(200, session.images())
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if not self.authorized():
                return self.reply(403, {"error": "Unauthorized"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
                if self.path == "/api/start":
                    session.start(body.get("image"), bool(body.get("dsp")), body.get("line", "disconnected"),
                                  body.get("connection"), body.get("board"))
                elif self.path == "/api/stop":
                    session.stop()
                elif self.path == "/api/send":
                    session.send(body.get("text"))
                elif self.path == "/api/call":
                    session.call(body.get("action"), body.get("number", ""))
                else:
                    return self.reply(404, {"error": "Not found"})
                self.reply(200, {"ok": True})
            except (ValueError, OSError) as exc:
                self.reply(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Courier GUI: {url}\nPress Ctrl-C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        session.stop()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--directory", type=Path, default=Path.cwd())
    args = parser.parse_args()
    serve(args.directory, args.port, not args.no_browser)
