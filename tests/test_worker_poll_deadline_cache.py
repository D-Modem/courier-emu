import random
import pytest
from courier_emu.worker_poll import first_instruction_at_tick


@pytest.mark.parametrize('ratio', [1 / 4, 1 / 3, 1 / 2, 0.2964705882352941, 1.0, 1.5])
def test_cached_inverse_is_earliest_exact_float_tick(ratio):
    rng = random.Random(21186)
    for tick in [0, 1, 2, 3, 100, 2**32, 2**40, *[rng.randrange(10**12) for _ in range(300)]]:
        at = first_instruction_at_tick(tick, ratio)
        assert int(at * ratio) >= tick
        assert at == 0 or int((at - 1) * ratio) < tick
        assert first_instruction_at_tick(tick, ratio) == at


def test_clock_discovery_does_not_reuse_old_ratio():
    first_instruction_at_tick.cache_clear()
    assert first_instruction_at_tick(100, .25) == 400
    assert first_instruction_at_tick(100, .5) == 200
    assert first_instruction_at_tick(100, .25) == 400
    assert first_instruction_at_tick.cache_info().hits == 1
    for n in range(1000):
        first_instruction_at_tick(n, .25)
    assert first_instruction_at_tick.cache_info().currsize == 64
