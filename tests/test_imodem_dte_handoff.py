from pathlib import Path
from types import SimpleNamespace

import pytest

from courier_emu.nac import NacImage
from tools.probe_imodem_pair import dte_data_ready, dte_receive_state


@pytest.mark.parametrize('receiver,callback,ready', [(0xec8d, 0x0e0e, False),
                                                   (0xec8d, 0x8b3e, False),
                                                   (0xf596, 0x0e0e, False),
                                                   (0xec8d, 0x46ba, True),
                                                   (0xf296, 0x46cc, True),
                                                   (0xf050, 0x0e0e, True)])
def test_waits_for_real_data_receiver_not_connect_or_keypress_abort(receiver, callback, ready):
    assert dte_data_ready({'receiver': receiver, 'callback': callback, 'mode': 5}) is ready


def test_ready_callbacks_are_original_firmware_data_queue_entries():
    base, program = NacImage.load(Path(__file__).resolve().parents[1] / 'Ie030002.nac').flatten()
    assert program[0xa86ba - base:0xa86be - base] == bytes.fromhex('ff06b2ca')
    assert program[0xa86cc - base:0xa86d0 - base] == bytes.fromhex('8b3e94ca')
    assert program[0xb3050 - base:0xb3055 - base] == bytes.fromhex('0fb60e50e8')


def test_handoff_reads_firmware_owned_cells_without_writes():
    values = {0x34834: (0xec8d).to_bytes(2, 'little'),
              0x32922: (0x0e0e).to_bytes(2, 'little'), 0x331ea: b'\x05'}
    def read(address, size):
        value = values[address]
        assert len(value) == size
        return value
    current = SimpleNamespace(machine=SimpleNamespace(mem_read=read))
    assert dte_receive_state(current) == {'receiver': 0xec8d, 'callback': 0x0e0e, 'mode': 5}
