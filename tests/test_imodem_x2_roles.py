from tools.decompile_imodem_roles import (asymmetric_setup_matrix, asymmetric_wait_matrix,
                                         capability_matrix, info0_gate_matrix)


def test_original_s58_builder_selects_advertised_server_and_symmetric_roles():
    rows = capability_matrix()
    assert {r['s58']: r['tag70'] for r in rows if r['s58'] in (42, 48, 50, 56, 58)} == {
        42: '21ff', 48: '3dff', 50: '2dff', 56: '35ff', 58: '25ff',
    }
    # Neither unnamed upper bit reveals a further role in this builder.
    for s58 in range(64):
        assert all(rows[s58]['tag70'] == rows[s58 | upper]['tag70']
                   for upper in (64, 128, 192))


def test_original_dsp_gate_treats_both_asymmetric_orientations_identically():
    rows = info0_gate_matrix()
    for row in rows:
        if row['context'] in ('client/server', 'server/client'):
            assert (row['pc'], row['ffde']) == ('95ca', '003f')
        elif row['context'] == 'server/server':
            assert row['pc'] == '965c'
        else:
            assert row['pc'] == '958f'


def test_original_asymmetric_setup_yields_to_receiver_in_both_orientations():
    rows = asymmetric_setup_matrix()
    assert len(rows) == 4
    for row in rows:
        assert row['initial_callback'] == '95dd'
        assert row['initial_delay'] == (0 if row['answer_role'] else 96)
        assert row['wait_callback'] == '95ed'
        assert row['receiver_bits'] == 7
        assert row['receiver_buffer'] == 'f6a8'
        assert row['tone_callback'] == '9e9e'
        assert row['transmit_script_after'] == row['transmit_script_before']
        # Scheduler yields before timeout recovery at 95ef/92ef.
        assert row['classifier'] == '8462'


def test_original_marker_wait_skips_fallback_until_its_counter_expires():
    rows = asymmetric_wait_matrix()
    assert [(row['counter'], row['pc']) for row in rows] == [
        (0, '95f1'), (0x11c0, '95f1'), (0xbb80, '95f1'),
        (0xbb81, '95ef'), (0xffff, '95ef'),
    ]
