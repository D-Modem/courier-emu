"""Post-window AT diagnostics on a local analog DTE, without guest-memory edits."""
import re


class AnalogLinkDiagnostics:
    def __init__(self, frame, *, guard_frames=40, timeout_frames=50):
        if guard_frames < 10 or timeout_frames < 1:
            raise ValueError('diagnostic guard must be at least one second')
        self.stage = 'guard'
        self.deadline = frame + guard_frames
        self.timeout_frames = timeout_frames
        self.start_frame = frame
        self.text = ''
        self.cursor = 0
        self.commands = []
        self.error = None

    @property
    def done(self):
        return self.stage in ('done', 'failed')

    def poll(self, frame, incoming=''):
        if self.done:
            return b''
        self.text += incoming
        if len(self.text) > 16384:
            self.stage, self.error = 'failed', 'diagnostic output exceeded capture bound'
            return b''
        response = self.text[self.cursor:]
        command = None
        if self.stage == 'guard' and frame >= self.deadline:
            command, self.stage = '+++', 'escaping'
        elif self.stage in ('escaping', 'querying') and '\r\nOK\r\n' in response:
            command, self.stage = ('ATI6\r', 'querying') if self.stage == 'escaping' else ('ATO\r', 'returning')
        elif self.stage == 'returning' and re.search(r'(?:^|[\r\n])CONNECT[^\r\n]*\r\n', response):
            self.stage = 'done'
        elif self.stage != 'guard' and ('\r\nERROR\r\n' in response or '\r\nNO CARRIER\r\n' in response):
            self.stage, self.error = 'failed', 'modem rejected diagnostic command or lost carrier'
        elif self.stage != 'guard' and frame >= self.deadline:
            self.stage, self.error = 'failed', f'timeout while {self.stage}'
        if command is not None:
            self.commands.append({'frame': frame, 'text': command})
            self.cursor = len(self.text)
            self.deadline = frame + self.timeout_frames
            return command.encode('ascii')
        return b''

    def status(self):
        return {'stage': self.stage, 'error': self.error, 'start_frame': self.start_frame,
                'commands': list(self.commands), 'text': self.text}
