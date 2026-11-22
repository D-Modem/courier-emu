"""Explicit, volatile AT presets for one-shot Apple/SIP modulation tests.

No CONNECT/result injection; these are ordinary commands to both firmwares.
Fixed V.22/V.22bis controls disable V.8, V.34/V.FC and PCM, and pin both rate
limits. Normal controls exclude ARQ/compression; v32-lapm explicitly requires
error correction and fixed DTE speed, with compression still disabled.
"""
PROFILES = {
    'bell103': 'S54=192B1&M0&B0&N1S56=192&K0',
    'v22': 'S54=192S56=192S58=33B0&M0&B0&U2&N2&K0',
    'v22bis': 'S54=192S56=192S58=33B0&M0&B0&U3&N3&K0',
    'v32': 'S54=192S56=192S58=33B0&M0&B0&U6&N6&K0',
    'v32-lapm': 'S54=192S56=192S58=33B0&M5&B1&U6&N6&K0',
    'v34': 'S54=0S56=0S58=33B0&M0&B0&U0&N0&K0',
}


def settings(protocol, *, caller=False):
    value = PROFILES[protocol]
    return ('S27=1' if caller else '') + value
