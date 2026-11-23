"""Captured capability tables, modeled straps, and literal SKU inventory."""
from pathlib import Path

import pytest

from courier_emu.cli import build_parser, _worker_command
from courier_emu.images import load_image
from courier_emu.machine import CourierMachine
from tools.audit_3453_product_ids import CAPABILITY, audit, product_type

CAPTURES = (
    Path('dumps/3453bc-firmware-read-2.2.09/firmware.bin'),
    Path('dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin'),
    Path('dumps/3453c-5MBRZ16P0186-firmware-read-20261014/firmware.bin'),
    Path('dumps/3453c-5MBRZ16P0186-bootmodem-read-20261014/bootmodem.bin'),
)


@pytest.mark.parametrize('path', CAPTURES)
def test_captured_identity_tables_and_bootstrap_ranges(path):
    result = audit(path)
    assert len(result['straps']) == 16
    countries = result['country_profiles']
    assert len(countries) == 28
    assert [row['index'] for row in countries] == list(range(28))
    assert countries[0]['name'] == 'US/Canada'
    assert countries[8]['name'] == 'CTR21'
    assert countries[27]['name'] == 'Turkey'
    assert countries[0]['si3034_reg16'] == '28'
    assert countries[0]['si3034_reg17_sent'] == 'a0'
    assert countries[8]['si3034_reg16'] == '2c'
    assert countries[8]['si3034_reg17_table'] == 'bc'
    assert countries[8]['si3034_reg17_sent'] == 'b8'
    assert [row['code'] for row in result['straps'] if row['usable']] == [2, 5, 7, 9, 12, 13]
    assert set(result['identity_literals']) == {'00345303', 'XX345303', '345303', '345403'}
    assert set(result['ati0_literals']) == {'3368', '3368A', '5608', '5608A'}
    assert all(int(row['end_exclusive_words'], 16) <= 0x8000
               for row in result['bootstrap_segments'])
    assert product_type(CAPABILITY[7]) == product_type(CAPABILITY[13]) == 'External'
    assert product_type(CAPABILITY[2]) == 'Internal'
    assert product_type(CAPABILITY[5]) == 'Rackmount'


@pytest.mark.parametrize('path', CAPTURES)
def test_3453_auto_straps_model_external_without_overriding_explicit_code(path):
    image = load_image(path)
    assert CourierMachine(image).panel.board_id == 7
    assert CourierMachine(image, board_id=2).panel.board_id == 2
    assert CourierMachine(image, board_id=None).panel.board_id is None


def test_cli_preserves_auto_and_explicit_straps():
    for code in ('auto', '2', '7', '13', 'none'):
        args = build_parser().parse_args(['run', str(CAPTURES[0]), '--board-id', code])
        command = _worker_command(args)
        assert command[command.index('--board-id') + 1] == code


def test_existing_country_selection_capture_keeps_manufacturing_id():
    transcript = Path('artifacts/3453c-board-identity-20261003/country-set-us.txt').read_text()
    assert 'Product type           US/Canada External' in transcript
    assert 'Product ID             99345303' in transcript


def test_probe_uses_final_snapshot_after_machine_closes_core(monkeypatch, capsys):
    import json
    import sys
    from tools.probe_3453_calibration import main

    monkeypatch.setattr(sys, 'argv', ['probe', str(CAPTURES[0]), '--instructions', '10000'])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result['error'] is None
    assert result['instructions'] == 10000
    assert len(result['codec_final']['registers']) == 32
    assert result['exchange']['calls'] == 0
    assert result['overlay_downloads'] == 0
