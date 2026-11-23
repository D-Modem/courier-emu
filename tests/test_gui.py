"""The browser GUI must launch the real CLI without interpreting shell input."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from courier_emu.gui import Session, parse_lamps
from courier_emu.cli import build_parser


def test_gui_options():
    args = build_parser().parse_args(['gui', '--no-browser', '--port', '0'])
    assert args.no_browser and args.port == 0


def test_images_and_validation(tmp_path):
    for name in ['main.xmf', 'boot.ROM', 'isdn.nac', 'notes.txt']:
        (tmp_path / name).touch()
    session = Session(tmp_path)
    assert session.images() == ['boot.ROM', 'isdn.nac', 'main.xmf']
    with pytest.raises(ValueError):
        session.start('../main.xmf')
    with pytest.raises(ValueError):
        session.start('main.xmf', line='not-a-line')
    with pytest.raises(ValueError):
        session.send('AT')


@pytest.mark.parametrize('image,mode,console', [('main.xmf', 'run', '--console'),
                                               ('isdn.nac', 'isdn-run', '--terminal')])
def test_launch_and_send(tmp_path, image, mode, console):
    (tmp_path / image).touch()
    session = Session(tmp_path)
    process = MagicMock()
    process.poll.return_value = None
    with patch('courier_emu.gui.subprocess.Popen', return_value=process) as spawn, \
         patch('courier_emu.gui.threading.Thread') as thread:
        session.start(image, dsp=True)
        command = spawn.call_args.args[0]
        assert command[5] == str(tmp_path / image)
        assert command[4] == mode
        assert console in command and '--with-dsp' in command
        assert spawn.call_args.kwargs['start_new_session']
        session.send('ATI3')
        process.stdin.write.assert_called_once_with(b'ATI3\r')
        with pytest.raises(ValueError):
            session.start(image)
        with pytest.raises(ValueError):
            session.send('\x1d')
        assert session.state()['running']
        if image.endswith('.xmf'):
            assert '--lamps-fd' in command
            assert spawn.call_args.kwargs['pass_fds']
            # The mocked reader thread never takes ownership of this stream.
            thread.call_args_list[0].kwargs['args'][0].close()
        else:
            assert '--lamps-fd' not in command
            assert not spawn.call_args.kwargs['pass_fds']


def test_output_is_bounded_and_old_readers_are_ignored(tmp_path):
    session = Session(tmp_path)
    stream = MagicMock()
    old = object()
    session.process = object()
    with patch('courier_emu.gui.os.read', side_effect=[b'old output', b'']):
        session._read(stream, 'output', old)
    assert session.output == ''
    with patch('courier_emu.gui.os.read', side_effect=[b'x' * 210000, b'']):
        session._read(stream, 'output', session.process)
    assert len(session.output) == 200000


def test_lamp_format():
    assert parse_lamps('AA .. OH ?? CS ... ARQ') == {
        'AA': True, 'CD': False, 'OH': True, 'MR': None,
        'CS': True, 'SYN': False, 'ARQ': True}
    assert parse_lamps('AA CD') is None
    assert parse_lamps('AA CD OH MR CS SYN BAD') is None


def test_lamp_reader_handles_split_records_and_old_sessions(tmp_path):
    import os
    session = Session(tmp_path)
    process = object()
    session.process = process
    read, write = os.pipe()
    os.write(write, b'AA .')
    os.write(write, b'. OH ?? CS ... ARQ\ninvalid\n')
    os.close(write)
    session._read_lamps(os.fdopen(read, 'rb'), process)
    assert session.lamps['OH'] is True
    assert session.lamps['CD'] is False
    assert session.lamps['MR'] is None
    read, write = os.pipe()
    os.write(write, b'.. CD .. MR .. SYN ...\n')
    os.close(write)
    session._read_lamps(os.fdopen(read, 'rb'), object())
    assert session.lamps['OH'] is True


def test_console_forwards_lamps_without_polluting_serial():
    import os
    import subprocess
    import sys
    read, write = os.pipe()
    # Run the real console bridge with a tiny worker speaking its fd protocol.
    worker = '''import os,sys,time
fd=int(sys.argv[sys.argv.index('--lamps-fd')+1])
os.write(fd,b'AA .. OH ?? CS ... ARQ\\n')
serial=int(sys.argv[sys.argv.index('--serial-fd')+1])
os.write(serial,b'OK\\r\\n')
time.sleep(0.2)
'''
    bridge = '''import argparse,os,sys
from courier_emu.terminal import run_console
args=argparse.Namespace(console=True,serial_pty=False,summary=False,lamps_fd=int(sys.argv[1]))
raise SystemExit(run_console(args,[sys.executable,'-c',sys.argv[2]],os.environ.copy()))
'''
    try:
        result = subprocess.run([sys.executable, '-c', bridge, str(write), worker],
                                pass_fds=(write,), input=b'', capture_output=True, timeout=10)
    finally:
        os.close(write)
    try:
        assert os.read(read, 4096) == b'AA .. OH ?? CS ... ARQ\n'
    finally:
        os.close(read)
    assert result.returncode == 0, result.stderr
    assert result.stdout == b'OK\r\n'
