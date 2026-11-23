from types import SimpleNamespace

from courier_emu.cli import _worker_command, build_parser
from tools.probe_imodem_analog_pair import parser as pair_parser


def test_worker_forwards_selected_codec_grouping_and_fixed_override(monkeypatch):
    monkeypatch.setattr('courier_emu.cli.load_image',
                        lambda *a, **kw: SimpleNamespace(path='firmware.rom'))
    args = build_parser().parse_args(['run', 'firmware.rom',
                                     '--frame-codec-samples', '3', '--frame-hz', '2401',
                                     '--frame-source', 'dsp-xf', '--interrupt-poll-instructions', '64',
                                     '--frame-irq-poll-instructions', '16'])
    command = _worker_command(args)
    assert command[command.index('--frame-codec-samples') + 1] == '3'
    assert command[command.index('--frame-hz') + 1] == '2401'
    assert command[command.index('--frame-source') + 1] == 'dsp-xf'
    assert command[command.index('--interrupt-poll-instructions') + 1] == '64'
    assert command[command.index('--frame-irq-poll-instructions') + 1] == '16'


def test_default_command_keeps_legacy_cadence(monkeypatch):
    monkeypatch.setattr('courier_emu.cli.load_image',
                        lambda *a, **kw: SimpleNamespace(path='firmware.rom'))
    args = build_parser().parse_args(['run', 'firmware.rom'])
    assert args.frame_codec_samples == 0
    assert '--frame-codec-samples' not in _worker_command(args)
    assert '--frame-hz' not in _worker_command(args)


def test_pair_probe_exposes_cadence_without_environment_or_monkeypatches():
    args = pair_parser().parse_args(['--analog-frame-codec-samples', '3',
                                    '--analog-frame-hz', '3200', '--analog-frame-source', 'dsp-xf',
                                    '--analog-interrupt-poll-instructions', '64',
                                    '--analog-frame-irq-poll-instructions', '16', '--clock-mode', 'coupled'])
    assert args.analog_frame_codec_samples == 3
    assert args.analog_frame_hz == 3200
    assert args.analog_frame_source == 'dsp-xf'
    assert args.analog_interrupt_poll_instructions == 64
    assert args.analog_frame_irq_poll_instructions == 16
    assert args.clock_mode == 'coupled'
    assert pair_parser().parse_args([]).analog_frame_codec_samples == 0
