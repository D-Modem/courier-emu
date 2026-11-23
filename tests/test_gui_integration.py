"""Real GUI workers; only simulated lines and loopback/local sockets, never USB/PSTN."""
from hashlib import md5
import json
from pathlib import Path
import socket
import tempfile
import time

import pytest

from courier_emu.gui import Session

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def firmware_root():
    if not (ROOT / 'main211.xmf').is_file():
        pytest.skip('optional local main211 firmware is unavailable')
    return ROOT


def wait_for(session, predicate, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = session.state()
        if predicate(state):
            return state
        assert state['running'], state['log'][-2000:]
        time.sleep(.05)
    pytest.fail(f"Worker timed out: {session.state()['output'][-500:]!r}")


@pytest.mark.parametrize('framing,expected', [(None, 'PARITY=N  WORDLEN=8'),
                                               ('stored', 'PARITY=E  WORDLEN=7')])
def test_gui_sets_actual_firmware_framing_not_display_mask(firmware_root, framing, expected):
    session = Session(firmware_root)
    try:
        board = {} if framing is None else {'dte_framing': framing}
        session.start('main211.xmf', board=board)
        session.send('ATI4')
        state = wait_for(session, lambda s: 'OK\r\n' in s['output'])
        assert expected in state['output']
    finally:
        session.stop()
    assert session.state()['exit_code'] == 0


def test_gui_worker_completes_ati11_and_next_command(firmware_root):
    session = Session(firmware_root)
    try:
        session.start('main211.xmf', dsp=True)
        session.send('ATI11')
        state = wait_for(session, lambda s: 'V.90 Status' in s['output'] and 'OK\r\n' in s['output'])
        assert 'Link Diagnostics' in state['output']
        session.send('ATI3')
        state = wait_for(session, lambda s: s['output'].count('OK\r\n') >= 2)
        assert 'USRobotics Courier V.Everything EXT' in state['output']
        assert state['lamps']['MR'] is True
    finally:
        session.stop()
    assert session.state()['exit_code'] == 0


@pytest.mark.parametrize('password', [None, ' spaces and quotes \" $; ß '])
def test_gui_sip_dial_sends_invite_to_local_pbx(firmware_root, password):
    session = Session(firmware_root)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as pbx:
        pbx.bind(('127.0.0.1', 0))
        pbx.settimeout(20)
        server = f'127.0.0.1:{pbx.getsockname()[1]}'
        try:
            settings = {'mode': 'sip', 'server': server, 'username': 'gui-local-test',
                        'target': 'sip:{number}@{server}'}
            if password is not None:
                settings['password'] = password
            session.start('main211.xmf', connection=settings)
            session.send('ATI3')
            wait_for(session, lambda s: 'OK\r\n' in s['output'])
            session.call('dial', '5551234')
            request, address = pbx.recvfrom(65535)
            assert request.startswith(b'INVITE sip:5551234@127.0.0.1 SIP/2.0\r\n')
            if password is not None:
                # Challenge the real worker to prove the GUI-provided secret
                # traverses both child-process layers and is used unmodified.
                headers = request.decode().split('\r\n')
                challenge = ['SIP/2.0 401 Unauthorized'] + [
                    line for line in headers if line.startswith(('Via:', 'From:', 'To:', 'Call-ID:', 'CSeq:'))
                ] + ['WWW-Authenticate: Digest realm="gui-test", nonce="local-nonce", algorithm=MD5',
                     'Content-Length: 0', '', '']
                pbx.sendto('\r\n'.join(challenge).encode(), address)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    request, address = pbx.recvfrom(65535)
                    if request.startswith(b'INVITE ') and b'Authorization: Digest ' in request:
                        break
                else:
                    pytest.fail('No authenticated INVITE')
                uri = request.split(b' ', 2)[1].decode()
                ha1 = md5(f'gui-local-test:gui-test:{password}'.encode()).hexdigest()
                ha2 = md5(f'INVITE:{uri}'.encode()).hexdigest()
                expected = md5(f'{ha1}:local-nonce:{ha2}'.encode()).hexdigest()
                assert f'response="{expected}"'.encode() in request
            # Refuse locally: no actual destination, RTP or external call.
            headers = request.decode().split('\r\n')
            response = ['SIP/2.0 486 Busy Here'] + [
                line for line in headers if line.startswith(('Via:', 'From:', 'To:', 'Call-ID:', 'CSeq:'))
            ] + ['Content-Length: 0', '', '']
            pbx.sendto('\r\n'.join(response).encode(), address)
        finally:
            session.stop()
    assert session.state()['exit_code'] == 0
    if password is not None:
        state = session.state()
        assert password not in state['output'] + state['log']
        assert 'password' not in state['connection']
        assert password not in json.dumps(state, ensure_ascii=False)


def test_gui_peer_sessions_boot_over_pcm_socket(firmware_root):
    a, b = Session(firmware_root), Session(firmware_root)
    # Short paths are required by the actual macOS/Linux sockaddr_un ABI.
    with tempfile.TemporaryDirectory(prefix='cgui-', dir='/tmp') as directory:
        path = str(Path(directory) / 'pair.sock')
        try:
            a.start('main211.xmf', connection={'mode': 'peer', 'socket': path,
                                             'role': 'listen', 'audio_only': True})
            b.start('main211.xmf', connection={'mode': 'peer', 'socket': path,
                                             'role': 'connect', 'audio_only': True})
            for session in [a, b]:
                session.send('ATI3')
            for session in [a, b]:
                state = wait_for(session, lambda s: 'OK\r\n' in s['output'])
                assert 'USRobotics Courier V.Everything EXT' in state['output']
                assert state['connection']['audio_only'] is True
        finally:
            a.stop()
            b.stop()
    assert not a.state()['running'] and not b.state()['running']
