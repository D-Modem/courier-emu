"""Captured CPU firmware with a synthetic idle DSP and local-only SIP port."""
from pathlib import Path
import struct
import pytest
from courier_emu.exchange import LineExchange
from courier_emu.images import load_image
from courier_emu.machine import CourierMachine


class LocalPort:
    state='idle'
    realtime=False
    closed=False
    def poll(self):pass
    def receive_audio(self):return []
    def send_audio(self,samples):pass
    def status(self):return {'state':self.state}
    def hangup(self):self.state='idle'
    def close(self):self.state='closed';self.closed=True


def test_native_sip_arm_matches_cooperative_service_at_boot(monkeypatch):
    path=Path(__file__).resolve().parents[1]/'dumps/courier-board-21210-capture-403/courier-board.rom'
    if not path.exists():pytest.skip('optional captured original firmware unavailable')
    machines=[]
    results=[]
    for mode in ['0','auto']:
        monkeypatch.setenv('COURIER_WORKER_POLL',mode)
        machine=CourierMachine(load_image(path),with_dsp=True,sip=LocalPort(),exchange=LineExchange(),board_id=7)
        # A synthetic idle DSP loop makes quiet-SIP polling eligible without
        # a real call. CPU firmware and all its I/O hooks remain untouched.
        bridge=machine.dsp_bridge
        bridge.core.load_program(struct.pack('<3H',0x5500,0x7980,0x6000),0x6000)
        bridge.core.set_pc(0x6000)
        bridge.active=bridge.launched=True
        results.append(machine.run(3_000_000))
        machines.append(machine)
    slow,fast=machines
    assert slow.instructions==fast.instructions==3_000_000
    assert slow.uc.regs==fast.uc.regs
    assert slow.uc.memory==fast.uc.memory
    assert slow.timer_interrupts==fast.timer_interrupts
    assert slow.serial_interrupts==fast.serial_interrupts
    assert slow._interrupt_stack==fast._interrupt_stack
    assert slow.serial==fast.serial
    assert fast._worker_poll.state.instruction_base==0
    assert fast._worker_poll.state.polls>0
    assert results[0].dsp_bridge['dsp']==results[1].dsp_bridge['dsp']
    for field in ['_instructions','_x86_ticks','_exchange_instructions',
                  '_codec_instructions','_dsp_cycle_debt']:
        assert getattr(slow.dsp_bridge,field)==getattr(fast.dsp_bridge,field)
