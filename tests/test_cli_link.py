from types import SimpleNamespace

from courier_emu.cli import _link_side, _worker_command, build_parser


def _link_args(*extra: str):
    return build_parser().parse_args(["link", "firmware.rom", *extra])


def _at_commands(command: list[str]) -> list[str]:
    return [command[index + 1] for index, item in enumerate(command) if item == "--at"]


def test_link_defaults_to_leased_line_and_opposite_switch_5_roles():
    args = _link_args()

    answer = _link_side(args, args.a_at, listen=True)
    originate = _link_side(args, args.b_at, listen=False)

    assert _at_commands(answer) == ["AT&L1"]
    assert _at_commands(originate) == ["AT&L1"]
    assert answer[answer.index("--dip-preset") + 1] == "dedicated-line"
    assert originate[originate.index("--dip-preset") + 1] == "dedicated-line-originate"


def test_link_preserves_explicit_per_side_commands():
    args = _link_args("--a-at", "ATI4", "--b-at", "ATZ")

    assert _at_commands(_link_side(args, args.a_at, listen=True)) == ["ATI4"]
    assert _at_commands(_link_side(args, args.b_at, listen=False)) == ["ATZ"]


def test_link_terminal_delays_are_independent_and_reach_worker(monkeypatch):
    monkeypatch.setattr('courier_emu.cli.load_image',
                        lambda *a, **kw: SimpleNamespace(path='firmware.rom'))
    args = _link_args('--a-send-delay-ms', '1500', '--b-send-delay-ms', '250')
    for listen, delay in ((True, '1500'), (False, '250')):
        command = _link_side(args, [], listen=listen)
        assert command[command.index('--send-after-connect-delay-ms') + 1] == delay
    run = build_parser().parse_args(['run', 'firmware.rom',
                                    '--send-after-connect-delay-ms', '1500'])
    command = _worker_command(run)
    assert command[command.index('--serial-after-connect-delay-ms') + 1] == '1500'


def test_link_holds_answer_until_ring_for_a_dialed_pair():
    args = _link_args("--a-at", "ATDT5551234", "--b-at", "ATA")

    answer = _link_side(args, args.b_at, listen=False)

    assert "--serial-input-on-ring" in answer
