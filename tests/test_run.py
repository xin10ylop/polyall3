"""Drawdown guard (audit #4 N1/N2): real losses stop the bot even with frequent fills; transient spikes/dips don't."""
from pmbot.run import DrawdownGuard


def test_real_loss_stops_even_with_fills_every_cycle():
    g = DrawdownGuard(3, 15.0)
    eqs = [100.0] * 5 + [100 - 2 * i for i in range(1, 30)]     # steady real loss, no quiet period needed
    stops = [i for i, e in enumerate(eqs) if g.add(e)]
    assert stops and eqs[stops[0]] < 85.0


def test_sell_fill_spike_does_not_inflate_peak():
    g = DrawdownGuard(3, 15.0)
    seq = [80.0, 80.0, 80.0, 100.8, 80.8, 80.8, 80.8, 80.8]      # spike: cash up before the position disappears
    assert not any(g.add(e) for e in seq)
    assert g.peak == 80.8


def test_buy_fill_dip_does_not_trip():
    g = DrawdownGuard(3, 15.0)
    seq = [100.0, 100.0, 100.0, 80.0, 99.5, 100.0, 79.0, 79.5, 100.0]   # 1-2 sample dips (position lag)
    assert not any(g.add(e) for e in seq)


def test_persistent_drop_trips_after_k_samples():
    g = DrawdownGuard(3, 15.0)
    res = [g.add(e) for e in [100.0, 100.0, 100.0, 80.0, 80.0, 80.0]]
    assert res == [False, False, False, False, False, True]
