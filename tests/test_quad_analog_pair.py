import pytest

from tools.probe_quad_analog_pair import check_asymmetric


def reports():
    summary = {"analog_connect": "CONNECT 53333/ARQ/x2/LAPM",
               "quad_connect": "CONNECT 33333/ARQ/x2/LAPM",
               "analog_terminal": "CONNECT 53333/ARQ/x2/LAPM\r\nPAYLOAD",
               "payload_checks": {"analog_to_quad": True, "quad_to_analog": True}}
    analog = {"error": None, "dsp_bridge": {"error": None, "line": {"frames": 3000},
              "line_service": {"rx_empty_connected": 0}}, "online_mode": True}
    quad = {"error": None, "x2_status_inputs": {"8954": 1}, "peek": {"8311": "04"},
            "endpoint": {"pcm_rx_underruns": 0, "media_peer": {"frames": 3000}}, "host_serial": {"overruns": 0},
            "terminal": "CONNECT 33333/ARQ/x2/LAPM\r\nPAYLOAD"}
    return summary, analog, quad


def test_asymmetric_rates_need_not_be_equal():
    check_asymmetric(*reports())


@pytest.mark.parametrize("role", ["quad", "analog"])
@pytest.mark.parametrize("result", [None, "CONNECT 64000/DIGITAL", "CONNECT 33600/ARQ/V34/LAPM"])
def test_fallback_and_transparent_digital_are_not_x2(role, result):
    pair = reports()
    pair[0][role + "_connect"] = result
    with pytest.raises(AssertionError):
        check_asymmetric(*pair)


@pytest.mark.parametrize("side", ["analog", "quad"])
def test_requested_media_boundary_must_be_reached(side):
    summary, analog, quad = reports()
    summary["line_frames_requested"] = 3001
    (analog["dsp_bridge"]["line"] if side == "analog"
     else quad["endpoint"]["media_peer"])["frames"] = 3001
    with pytest.raises(AssertionError, match="duration"):
        check_asymmetric(summary, analog, quad)


def test_connected_analog_underruns_are_not_ignored():
    summary, analog, quad = reports()
    analog["dsp_bridge"]["line_service"]["rx_empty_connected"] = 1
    with pytest.raises(AssertionError, match="underrun"):
        check_asymmetric(summary, analog, quad)


def test_symmetric_x2_does_not_satisfy_asymmetric_test():
    pair = reports()
    pair[2]["x2_status_inputs"]["8954"] = 4
    with pytest.raises(AssertionError, match="symmetric"):
        check_asymmetric(*pair)


@pytest.mark.parametrize("kind", ["missing_payload", "quad_carrier", "analog_carrier",
                                  "uart", "pcm", "cpu", "dsp", "no_carrier"])
def test_data_integrity_and_health_are_required(kind):
    summary, analog, quad = reports()
    if kind == "missing_payload":
        summary["payload_checks"]["quad_to_analog"] = False
    elif kind == "quad_carrier":
        quad["peek"]["8311"] = "00"
    elif kind == "analog_carrier":
        analog["online_mode"] = False
    elif kind == "uart":
        quad["host_serial"]["overruns"] = 1
    elif kind == "pcm":
        quad["endpoint"]["pcm_rx_underruns"] = 1
    elif kind == "cpu":
        quad["error"] = "failed"
    elif kind == "dsp":
        analog["dsp_bridge"]["error"] = "failed"
    else:
        quad["terminal"] += "\r\nNO CARRIER\r\n"
    with pytest.raises(AssertionError):
        check_asymmetric(summary, analog, quad)
