"""Bounded post-NO-CARRIER AT queries through the normal analog DTE.

This retains the modem's own diagnostic responses without changing guest memory.
An explicit escape_online control allows guarded +++ after a host-side failure
while carrier is still up; it does not drop DTR or send ATH.
"""
from __future__ import annotations


class AnalogDisconnectDiagnostics:
    def __init__(self, now: float, *, guard_seconds=1.0, timeout_seconds=10.0,
                 commands=('ATI6', 'ATI11', 'ATI4'), max_bytes=32768,
                 escape_online=False):
        if guard_seconds < 0 or timeout_seconds <= 0 or max_bytes < 1:
            raise ValueError('invalid diagnostic bounds')
        if not commands or any(not c.startswith('ATI') or not c[3:].isdigit() for c in commands):
            raise ValueError('only ATI information queries are permitted')
        if escape_online and guard_seconds < 1.0:
            raise ValueError('online escape needs at least a one-second guard')
        self.escape_pending = escape_online
        self.commands = tuple(commands)
        self.guard_seconds, self.timeout_seconds = guard_seconds, timeout_seconds
        self.max_bytes = max_bytes
        self.started, self.deadline = now, now + guard_seconds
        self.stage = 'guard'
        self.index, self.cursor = 0, 0
        self.text = bytearray()
        self.sent = []
        self.error = None

    @property
    def done(self):
        return self.stage in ('done', 'failed')

    def feed(self, data: bytes):
        if self.done:
            return
        if len(self.text) + len(data) > self.max_bytes:
            self.stage, self.error = 'failed', 'diagnostic capture bound exceeded'
            return
        self.text.extend(data)

    def poll(self, now: float, *, dte_idle=True) -> bytes:
        if self.done:
            return b''
        if self.stage in ('query', 'escape'):
            response = bytes(self.text[self.cursor:])
            if b'\r\nERROR\r\n' in response or b'\r\nNO CARRIER\r\n' in response:
                self.stage, self.error = 'failed', 'diagnostic command rejected'
                return b''
            if b'\r\nOK\r\n' in response:
                if self.stage == 'query':
                    self.index += 1
                if self.index == len(self.commands):
                    self.stage = 'done'
                    return b''
                self.stage, self.deadline = 'guard', now + self.guard_seconds
            elif now >= self.deadline:
                command = 'escape OK' if self.stage == 'escape' else self.commands[self.index]
                self.stage, self.error = 'failed', 'timeout waiting for ' + command
                return b''
        if self.stage == 'guard' and now >= self.deadline:
            if not dte_idle:
                if now >= self.deadline + self.timeout_seconds:
                    self.stage, self.error = 'failed', 'DTE did not drain before query'
                return b''
            command = '+++' if self.escape_pending else self.commands[self.index]
            self.sent.append({'elapsed_seconds': now - self.started, 'command': command})
            self.cursor = len(self.text)
            self.stage = 'escape' if self.escape_pending else 'query'
            self.escape_pending = False
            self.deadline = now + self.timeout_seconds
            return (command if self.stage == 'escape' else command + '\r').encode('ascii')
        return b''

    def status(self):
        return {'stage': self.stage, 'error': self.error, 'queries': list(self.sent),
                'text': self.text.decode('ascii', 'backslashreplace')}
