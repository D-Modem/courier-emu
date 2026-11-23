"""GUI backend wiring: validate real CLI arguments without making external calls."""
import http.client
import json
from pathlib import Path
import signal
import subprocess
import sys
import threading
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from courier_emu.cli import build_parser
from courier_emu.gui import Session, serve


@pytest.fixture
def launch():
    # pytest's macOS tmp_path exceeds the real UNIX-socket path limit.
    with tempfile.TemporaryDirectory(prefix='cgui-', dir='/tmp') as directory:
        root = Path(directory).resolve()
        for name in ['main.xmf', 'board.rom', 'isdn.nac']:
            (root / name).touch()
        session = Session(root)
        process = MagicMock()
        process.poll.return_value = None
        process.stdin.closed = False
        with patch('courier_emu.gui.subprocess.Popen', return_value=process) as spawn, \
             patch('courier_emu.gui.threading.Thread') as threads:
            yield session, spawn, process
            # Mocked reader threads never take ownership of their lamp descriptors.
            for call in threads.call_args_list:
                if call.kwargs['target'] == session._read_lamps:
                    call.kwargs['args'][0].close()


def cli_args(spawn):
    command = spawn.call_args.args[0]
    return command, build_parser().parse_args(command[4:])


@pytest.mark.parametrize('dsp,line,expected', [(False, 'disconnected', False),
                                               (True, 'disconnected', True),
                                               (False, 'dial-tone', True)])
def test_simulated_line_dsp_selection_is_honored(launch, dsp, line, expected):
    session, spawn, _ = launch
    session.start('main.xmf', dsp=dsp, line=line)
    _, args = cli_args(spawn)
    assert args.with_dsp is expected
    assert args.daa_line == (line if expected else None)


def test_sip_launch_uses_environment_not_password_argv(launch, monkeypatch):
    session, spawn, _ = launch
    monkeypatch.setenv('GUI_TEST_PASSWORD', 'never-in-argv-or-state')
    session.start('main.xmf', connection={
        'mode': 'sip', 'server': '127.0.0.1:5061', 'username': '6001',
        'password_env': 'GUI_TEST_PASSWORD', 'target': 'sip:{number}@{server}',
        'codec': 'pcma', 'sip_port': 5062, 'rtp_port': 4000,
    })
    command, args = cli_args(spawn)
    assert args.sip_server == '127.0.0.1:5061'
    assert args.sip_username == '6001'
    assert args.sip_password_env == 'GUI_TEST_PASSWORD'
    assert args.sip_target == 'sip:{number}@{server}'
    assert args.sip_codec == 'pcma'
    assert args.sip_local_port == 5062 and args.rtp_local_port == 4000
    assert args.with_dsp and args.daa_line is None
    assert not args.line_link and not args.apple_modem
    assert '--sip-password' not in command
    assert 'never-in-argv-or-state' not in json.dumps(session.state()) + repr(command)
    assert session.state()['connection'] == {'mode': 'sip', 'server': '127.0.0.1:5061'}


@pytest.mark.parametrize('password', ['secret', ' spaces and \"quotes\" $; ß ', ''])
def test_gui_password_is_child_only_and_never_in_argv_or_state(launch, monkeypatch, password):
    import os
    session, spawn, process = launch
    monkeypatch.setenv('COURIER_GUI_SIP_PASSWORD', 'unchanged-parent')
    monkeypatch.setenv('COURIER_SIP_PASSWORD', 'fallback-secret')
    session.start('main.xmf', connection={
        'mode': 'sip', 'server': '127.0.0.1:5060', 'password': password,
    })
    command, args = cli_args(spawn)
    assert '--sip-password' not in command
    assert args.sip_password_env == 'COURIER_GUI_SIP_PASSWORD'
    assert spawn.call_args.kwargs['env']['COURIER_GUI_SIP_PASSWORD'] == password
    assert os.environ['COURIER_GUI_SIP_PASSWORD'] == 'unchanged-parent'
    assert os.environ['COURIER_SIP_PASSWORD'] == 'fallback-secret'
    if password:
        assert password not in repr(command) + json.dumps(session.state())
    assert session.state()['connection'] == {'mode': 'sip', 'server': '127.0.0.1:5060'}
    # The next session must use its own input/fallback, not retain this secret.
    process.poll.return_value = 0
    session.start('main.xmf', connection={'mode': 'sip', 'server': '127.0.0.1:5060'})
    _, args = cli_args(spawn)
    assert args.sip_password_env == 'COURIER_SIP_PASSWORD'
    assert spawn.call_args.kwargs['env'] is None


@pytest.mark.parametrize('role,audio_only', [('listen', True), ('connect', True), ('connect', False)])
def test_peer_roles_and_pcm_option(launch, role, audio_only):
    session, spawn, _ = launch
    session.start('board.rom', connection={'mode': 'peer', 'socket': 'pair.sock',
                                        'role': role, 'audio_only': audio_only})
    _, args = cli_args(spawn)
    assert args.line_link == str(session.root / 'pair.sock')
    assert args.line_listen is (role == 'listen')
    assert args.line_audio_only is audio_only
    assert args.with_dsp and args.daa_line is None
    assert not args.sip_server and not args.apple_modem
    assert session.state()['connection']['audio_only'] is audio_only


def test_physical_bridge_and_board_options(launch, tmp_path):
    session, spawn, _ = launch
    helper = tmp_path / 'helper with spaces'
    helper.touch()
    helper.chmod(0o700)
    with patch('courier_emu.gui.sys.platform', 'darwin'):
        session.start('board.rom', connection={
            'mode': 'physical', 'helper': str(helper), 'confirmed': True,
            'rate': 10286, 'gain': 1.0,
        }, board={'id': '7', 'nvram_fixture': 'idsdl403', 'tick_source': ''})
    command, args = cli_args(spawn)
    assert args.apple_modem == str(helper)
    assert args.apple_rate == 10286 and args.apple_tx_gain == 1
    assert args.board_id == '7' and args.nvram_fixture == 'idsdl403'
    assert args.tick_source is None
    assert args.with_dsp and args.daa_line is None
    assert not args.line_link and not args.sip_server and not args.force_online
    assert command.count(str(helper)) == 1  # no shell splitting/execution
    assert 'shell' not in spawn.call_args.kwargs


@pytest.mark.parametrize('connection', [
    [], {'mode': []}, {'mode': 'unknown'},
    {'mode': 'simulated', 'server': 'example.test'},
    {'mode': 'sip'}, {'mode': 'sip', 'server': 'example.test\r\nInjected: header'},
    {'mode': 'sip', 'server': 'example.test:65536'},
    {'mode': 'sip', 'server': 'example.test', 'codec': 'opus'},
    {'mode': 'sip', 'server': 'example.test', 'password': 123},
    {'mode': 'sip', 'server': 'example.test', 'password': 'bad\x00password'},
    {'mode': 'sip', 'server': 'example.test', 'password': 'x' * 1025},
    {'mode': 'sip', 'server': 'example.test', 'password_env': 'BAD=VALUE'},
    {'mode': 'sip', 'server': 'example.test', 'target': 'sip:{unexpected}@host'},
    {'mode': 'sip', 'server': 'example.test', 'sip_port': True},
    {'mode': 'sip', 'server': 'example.test', 'rtp_port': -1},
    {'mode': 'peer', 'socket': ''}, {'mode': 'peer', 'socket': 'x' * 105},
    {'mode': 'peer', 'socket': 'pair.sock', 'role': 'invalid'},
    {'mode': 'peer', 'socket': 'pair.sock', 'audio_only': 'false'},
    {'mode': 'peer', 'socket': 'pair.sock', 'server': 'example.test'},
    {'mode': 'physical'}, {'mode': 'physical', 'confirmed': 'true'},
])
def test_invalid_backend_never_spawns(launch, connection):
    session, spawn, _ = launch
    with pytest.raises(ValueError):
        session.start('main.xmf', connection=connection)
    spawn.assert_not_called()


def test_listener_never_unlinks_existing_path(launch):
    session, spawn, _ = launch
    path = session.root / 'existing.sock'
    path.write_text('must survive')
    with pytest.raises(ValueError, match='already exists'):
        session.start('main.xmf', connection={'mode': 'peer', 'role': 'listen', 'socket': str(path)})
    assert path.read_text() == 'must survive'
    spawn.assert_not_called()


@pytest.mark.parametrize('field,value', [('rate', 9999), ('gain', -0.1), ('gain', float('nan'))])
def test_physical_settings_rejected_before_launch(launch, tmp_path, field, value):
    session, spawn, _ = launch
    helper = tmp_path / 'helper'
    helper.touch()
    helper.chmod(0o700)
    connection = {'mode': 'physical', 'helper': str(helper), 'confirmed': True, field: value}
    with patch('courier_emu.gui.sys.platform', 'darwin'), pytest.raises(ValueError):
        session.start('board.rom', connection=connection)
    spawn.assert_not_called()


def test_physical_requires_platform_and_executable(launch):
    session, spawn, _ = launch
    connection = {'mode': 'physical', 'helper': 'missing-helper', 'confirmed': True}
    with patch('courier_emu.gui.sys.platform', 'linux'), pytest.raises(ValueError, match='macOS'):
        session.start('board.rom', connection=connection)
    with patch('courier_emu.gui.sys.platform', 'darwin'), pytest.raises(ValueError, match='not executable'):
        session.start('board.rom', connection=connection)
    spawn.assert_not_called()


@pytest.mark.parametrize('board', [[], {'id': '16'}, {'nvram_fixture': []},
                                  {'tick_source': {}}, {'unrecognized': True}])
def test_invalid_board_options_never_spawn(launch, board):
    session, spawn, _ = launch
    with pytest.raises(ValueError):
        session.start('main.xmf', board=board)
    spawn.assert_not_called()


@pytest.mark.parametrize('mode', ['sip', 'peer', 'physical'])
def test_nac_rejects_analog_backends(launch, mode):
    session, spawn, _ = launch
    with pytest.raises(ValueError, match='not NAC'):
        session.start('isdn.nac', connection={'mode': mode})
    spawn.assert_not_called()


def test_call_buttons_send_real_serial_bytes(launch):
    session, _, process = launch
    session.start('main.xmf')
    session.call('dial', '+1 555-1234,2')
    session.call('answer')
    session.call('escape')
    session.call('hangup')
    assert [call.args[0] for call in process.stdin.write.call_args_list] == [
        b'ATDT+15551234,2\r', b'ATA\r', b'+++', b'ATH\r']
    assert process.stdin.flush.call_count == 4
    for bad in ['123\rATH', '123;ATH', '', '++', 'x' * 65]:
        with pytest.raises(ValueError):
            session.call('dial', bad)
    with pytest.raises(ValueError):
        session.call('invalid')
    assert process.stdin.write.call_count == 4


def test_call_requires_running_analog_session(launch):
    session, _, _ = launch
    with pytest.raises(ValueError, match='Start'):
        session.call('dial', '123')
    session.start('isdn.nac')
    with pytest.raises(ValueError, match='analog'):
        session.call('answer')


def test_stop_detaches_before_signalling_group(launch):
    session, _, process = launch
    session.start('main.xmf')
    with patch('courier_emu.gui.os.killpg') as kill:
        session.stop()
    process.stdin.write.assert_called_once_with(b'\x1d')
    process.wait.assert_called_once_with(timeout=12)
    process.stdin.close.assert_called_once()
    kill.assert_not_called()


def test_stop_drains_large_final_report_without_forced_kill(tmp_path):
    # A real child blocks on stderr unless the session reader can keep its
    # lock while Stop waits. No emulator or external connection is needed.
    worker = "import os; os.read(0,1); os.write(2,b'x'*500000)"
    session = Session(tmp_path)
    session.image = 'main.xmf'
    process = subprocess.Popen([sys.executable, '-c', worker], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True, bufsize=0)
    session.process = process
    readers = []
    for stream, field in [(process.stdout, 'output'), (process.stderr, 'log')]:
        reader = threading.Thread(target=session._read, args=(stream, field, process))
        readers.append(reader)
        reader.start()
    try:
        session.stop()
        for reader in readers:
            reader.join(5)
            assert not reader.is_alive()
        assert process.returncode == 0
        assert len(session.log) == 200000
        assert not session.stopping
    finally:
        session.stop()


def test_stopping_session_rejects_input_and_restart(launch):
    session, _, process = launch
    session.start('main.xmf')
    session.stopping = True
    assert session.state()['stopping']
    with pytest.raises(ValueError, match='stopping'):
        session.send('AT')
    with pytest.raises(ValueError, match='Wait'):
        session.start('main.xmf')
    process.stdin.write.assert_not_called()


def test_physical_stop_timeout_warns_and_kills_descendants(launch):
    session, _, process = launch
    session.start('main.xmf')
    session.connection = {'mode': 'physical'}
    process.wait.side_effect = [subprocess.TimeoutExpired('worker', 12), None, None]
    with patch('courier_emu.gui.os.killpg') as kill, patch('courier_emu.gui.time.sleep') as sleep:
        session.stop()
    assert [call.args for call in kill.call_args_list] == [
        (process.pid, signal.SIGTERM), (process.pid, signal.SIGKILL)]
    sleep.assert_called_once_with(3)
    assert 'verify the physical line is on-hook' in session.log


def test_physical_helper_diagnostics_are_forwarded_live():
    # Tiny local worker, not a hardware helper: no USB access or calls.
    worker = '''import os,sys,time
fd=int(sys.argv[sys.argv.index('--serial-fd')+1])
os.write(fd,b'OK\\r\\n')
print('helper: on-hook readback confirmed',file=sys.stderr,flush=True)
print('{"status":"test"}',flush=True)
time.sleep(.1)
'''
    bridge = '''import argparse,os,sys
from courier_emu.terminal import run_console
args=argparse.Namespace(console=True,serial_pty=False,summary=False,apple_modem='fake-helper')
raise SystemExit(run_console(args,[sys.executable,'-c',sys.argv[1]],os.environ.copy()))
'''
    result = subprocess.run([sys.executable, '-c', bridge, worker], input=b'', capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == b'OK\r\n'
    assert b'helper: on-hook readback confirmed' in result.stderr
    assert b'"status": "test"' in result.stderr


def test_http_forwards_connection_board_and_call_actions(tmp_path):
    # Exercise the real loopback HTTP/token boundary, with no worker spawned.
    from http.server import ThreadingHTTPServer
    ready = threading.Event()
    servers = []

    def make_server(*args):
        server = ThreadingHTTPServer(*args)
        servers.append(server)
        ready.set()
        return server

    with patch('courier_emu.gui.Session') as session_type, \
         patch('courier_emu.gui.ThreadingHTTPServer', side_effect=make_server), \
         patch('courier_emu.gui.secrets.token_urlsafe', return_value='test-token'):
        thread = threading.Thread(target=serve, args=(tmp_path, 0, False))
        thread.start()
        assert ready.wait(5)
        connection = http.client.HTTPConnection('127.0.0.1', servers[0].server_port, timeout=5)
        try:
            connection.request('POST', '/api/call', body='{"action":"answer"}',
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            assert response.status == 403
            response.read()
            body = {'image': 'main.xmf', 'dsp': True, 'connection': {'mode': 'peer', 'socket': '/tmp/pair'},
                    'board': {'id': '7', 'nvram_fixture': 'idsdl403'}}
            headers = {'Content-Type': 'application/json', 'X-Courier-Token': 'test-token'}
            connection.request('POST', '/api/start', body=json.dumps(body), headers=headers)
            response = connection.getresponse()
            assert response.status == 200, response.read()
            response.read()
            session_type.return_value.start.assert_called_once_with(
                'main.xmf', True, 'disconnected', body['connection'], body['board'])
            connection.request('POST', '/api/call', body='{"action":"dial","number":"5551234"}', headers=headers)
            response = connection.getresponse()
            assert response.status == 200, response.read()
            response.read()
            session_type.return_value.call.assert_called_once_with('dial', '5551234')
        finally:
            connection.close()
            servers[0].shutdown()
            thread.join(5)
        assert not thread.is_alive()
        session_type.return_value.stop.assert_called_once()
