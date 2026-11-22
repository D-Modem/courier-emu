"""Optional sibling interop driver's bounded-load source construction."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def chunks():
    path = Path(__file__).resolve().parents[2] / 'v90modem/tools/probe_x2_host_courier.py'
    if not path.exists():
        pytest.skip('sibling interop driver unavailable')
    spec = importlib.util.spec_from_file_location('courier_dte_chunks', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.native_payload_chunks


@pytest.mark.parametrize('size', [0, 1, 64, 600, 10000])
def test_chunking_preserves_exact_source(chunks, size):
    message = ''.join(f'V90-{i:05d}-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n' for i in range(100))
    parts = chunks(message, size)
    assert ''.join(parts) == message
    assert all(parts)
    if size:
        assert all(len(part) <= size for part in parts)
    else:
        assert parts == [message]


def test_empty_source_and_invalid_size(chunks):
    assert chunks('', 0) == chunks('', 64) == []
    with pytest.raises(ValueError, match='nonnegative'):
        chunks('abc', -1)
