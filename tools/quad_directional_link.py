"""Read directional rates from original x2 DSP reports, not CONNECT text.

QF060003 tag 6A is parsed at D575F: low five bits are the V.34
receive index, high five bits the PCM transmit index on the server path.
The analog 403 report builder E19C..E1AC packs the reciprocal ordering.
See docs/x2-courier-mp-fields.md for the original-instruction rate audit.
"""
import hashlib
import struct


V34_RX = 0xA44D
V34_RX_END = 0xA580
PCM_TX = 0xC395
# QF060003 common datapump, source 53E02 + 2*(A44D-A180).
V34_RX_SHA256 = '8f9a8c7bbcba884d94fa969bd20636f39580f12b8a2d3ac027a56a55795e81e5'


def receive_code_sha256(words):
    return hashlib.sha256(struct.pack(f'<{len(words)}H', *words)).hexdigest()


def pcm_nominal_bps(index):
    if not 1 <= index <= 15:
        raise AssertionError('PCM rate index is outside the asymmetric x2 ladder')
    return (33333, 37333)[index - 1] if index <= 2 else (index + 28) * 8000 // 6


def inspect_directional_link(analog, quad):
    """Require reciprocal DSP reports and the stock common V.34 receiver.

    The PCM result is a nominal firmware rate label, not measured throughput.
    Earlier CONNECT lines can precede later DSP rate renegotiation.
    """
    if quad['x2_status_inputs']['8954'] != 1:
        raise AssertionError('Quad must select asymmetric x2 server mode')
    if quad.get('dsp_cells', {}).get('039b') != V34_RX:
        raise AssertionError('Quad is not running the common V.34 receive callback')
    if quad.get('dsp_cells', {}).get('039a') != PCM_TX:
        raise AssertionError('Quad is not running the asymmetric PCM transmit callback')
    if quad.get('v34_receive_code_sha256') != V34_RX_SHA256:
        raise AssertionError('active V.34 receive code does not match stock QF060003')
    server = [e for e in quad['endpoint']['exchanges']
              if e['direction'] == 'dsp-to-cpu' and e['command'] == 0x6A]
    client = [e for e in analog['dsp_bridge']['dsp_mailbox_log']
              if e.get('tag') == '006a' and len(e.get('words', [])) == 2]
    if not server or not client:
        raise AssertionError('both original DSP directional rate reports are required')
    server_word = server[-1]['argument']
    client_word = int(client[-1]['words'][1], 16)
    upstream_index, downstream_index = server_word & 31, (server_word >> 8) & 31
    if not 1 <= upstream_index <= 14:
        raise AssertionError('upstream rate index is not a V.34 rate')
    downstream = pcm_nominal_bps(downstream_index)
    if (client_word & 31, (client_word >> 8) & 31) != (downstream_index, upstream_index):
        raise AssertionError('latest directional DSP rates disagree between the peers')
    return {
        'downstream': {'modulation': 'x2 PCM', 'nominal_bps': downstream,
                       'rate_index': downstream_index},
        'upstream': {'modulation': 'V.34', 'bps': upstream_index * 2400,
                     'rate_index': upstream_index},
        'quad_rate_word': f'{server_word:04x}',
        'analog_rate_word': f'{client_word:04x}',
        'quad_receive_callback': f'{V34_RX:04x}',
        'quad_transmit_callback': f'{PCM_TX:04x}',
        'quad_receive_code_sha256': quad['v34_receive_code_sha256'],
        'scope': 'Latest DSP rate reports and active receiver; not measured throughput.',
    }


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analog', type=Path)
    parser.add_argument('quad', type=Path)
    parser.add_argument('--program', type=Path,
                        help='saved full DSP program for older reports without a receive-code hash')
    args = parser.parse_args()
    analog = json.loads(args.analog.read_text())
    quad = json.loads(args.quad.read_text())
    if args.program:
        program = args.program.read_bytes()
        if len(program) != 2 * 65536:
            raise ValueError('expected a complete 65536-word DSP program capture')
        quad['v34_receive_code_sha256'] = hashlib.sha256(
            program[2 * V34_RX:2 * V34_RX_END]).hexdigest()
    print(json.dumps(inspect_directional_link(analog, quad), indent=2))
