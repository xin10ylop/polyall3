"""Polymarket liquidity-reward scoring (docs.polymarket.com/developers/market-makers/liquidity-rewards).

S(v, s) = ((v - s) / v)^2 * size, with v = max spread (cents) and s = distance from the size-cutoff-adjusted
midpoint (cents). Only orders of at least `rewards_min_size` shares count. Side 1 = YES bids + NO asks, side 2 = YES
asks + NO bids, all in YES-price space; the API's YES book already contains NO-token orders mirrored at 1-p (the
NO book is an exact mirror, verified on 70/70 markets), so only the YES book is read.
Q_min = max(min(Q1, Q2), max(Q1, Q2) / 3) if 0.10 <= mid <= 0.90 else min(Q1, Q2).
A maker earns rate_per_day * (its Q_min / sum of all makers' Q_min), sampled once a minute, paid daily.
"""


def levels(book, side):
    lv = [(float(x["price"]), float(x["size"])) for x in (book.get(side) or [])]
    lv.sort(key=lambda x: x[0], reverse=(side == "bids"))
    return lv


def adjusted_best(lv, min_size):
    """Price at which cumulative depth from the top of book first reaches min_size."""
    c = 0.0
    for p, s in lv:
        c += s
        if c >= min_size:
            return p
    return None


def s_score(v, s_cents):
    return max(0.0, (v - s_cents) / v) ** 2 if s_cents >= 0 else 0.0


def side_q(orders, mid, v, is_bid):
    q = 0.0
    for p, sz in orders:
        s = round(((mid - p) if is_bid else (p - mid)) * 100, 6)
        if 0 <= s < v:
            q += s_score(v, s) * sz
    return q


def q_min(q1, q2, mid):
    if 0.10 <= mid <= 0.90:
        return max(min(q1, q2), max(q1, q2) / 3.0)
    return min(q1, q2)


def _subtract(lv, ours, descending):
    d = {}
    for p, s in lv:
        k = round(p, 6)
        d[k] = d.get(k, 0.0) + s
    for p, s in ours:
        k = round(p, 6)
        if k in d:
            d[k] = max(0.0, d[k] - s)
    return sorted([(p, s) for p, s in d.items() if s > 1e-9], key=lambda x: x[0], reverse=descending)


def book_state(yes_book, min_size, v, exclude=None):
    """Summarise a binary market in YES-price space from the (unified) YES book.

    exclude: {"bids": [(p, size)], "asks": [(p, size)]} of our own resting orders (live mode) so we never compete
    with, or step inside, ourselves.
    """
    if not yes_book:
        return None
    bids, asks = levels(yes_book, "bids"), levels(yes_book, "asks")
    if exclude:
        bids = _subtract(bids, exclude.get("bids", []), descending=True)
        asks = _subtract(asks, exclude.get("asks", []), descending=False)
    if not bids or not asks:
        return None
    abb, aba = adjusted_best(bids, min_size), adjusted_best(asks, min_size)
    if abb is None or aba is None or aba <= abb:
        return None
    mid = (abb + aba) / 2
    try:
        tick = float(yes_book.get("tick_size") or 0.01)
    except Exception:
        tick = 0.01
    return {
        "bb": bids[0][0], "ba": asks[0][0], "mid": mid, "tick": tick,
        "q1": side_q(bids, mid, v, True), "q2": side_q(asks, mid, v, False),
        "bids": bids[:15], "asks": asks[:15],
    }


def order_q(orders, mid, v, min_size):
    """Our (Q1, Q2) from concrete YES-space orders [(ys_side, price, size)]; orders below min_size do not count."""
    q1 = q2 = 0.0
    for side, p, sz in orders:
        if sz < min_size:
            continue
        if side == "bid":
            q1 += side_q([(p, sz)], mid, v, True)
        else:
            q2 += side_q([(p, sz)], mid, v, False)
    return q1, q2


def our_share(st, v, min_size, orders):
    """(our Q_min, conservative share, central share). Conservative credits competitors with max(Q1, Q2), an upper
    bound on their total Q_min; central credits them with Q_min of the aggregate book."""
    o1, o2 = order_q(orders, st["mid"], v, min_size)
    ours = q_min(o1, o2, st["mid"])
    if ours <= 0:
        return 0.0, 0.0, 0.0
    comp_cons = max(st["q1"], st["q2"])
    comp_cent = q_min(st["q1"], st["q2"], st["mid"])
    return ours, ours / (ours + comp_cons), ours / (ours + comp_cent)
