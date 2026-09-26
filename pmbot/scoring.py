"""Polymarket liquidity-reward scoring (docs.polymarket.com/developers/market-makers/liquidity-rewards).

S(v, s) = ((v - s) / v)^2 * size, with v = max spread (cents) and s = distance from the size-cutoff-adjusted
midpoint (cents). Side 1 = YES bids + NO asks, side 2 = YES asks + NO bids (all expressed in YES-price space); the API's YES book
already includes NO-token orders mirrored at 1-p, so only the YES book is read.
Q_min = max(min(Q1, Q2), max(Q1, Q2) / 3) if 0.10 <= mid <= 0.90 else min(Q1, Q2).
Rewards are sampled once a minute; a maker earns rate_per_day * (its Q_min / sum of all makers' Q_min).
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


def book_state(yes_book, no_book, min_size, v, exclude=None):
    """Summarise a binary market's two books in YES-price space.

    exclude: optional {"bids": [(p, size)], "asks": [(p, size)]} of our own resting orders (YES-space) to remove
    from competitor liquidity when running live.
    """
    if not yes_book or not no_book:
        return None
    # The CLOB serves one unified book: the NO token's book is an exact mirror of the YES book (verified 40/40
    # markets), so the YES book alone already contains every order placed on either token.
    bids, asks = levels(yes_book, "bids"), levels(yes_book, "asks")
    if exclude:
        bids = _subtract(bids, exclude.get("bids", []), descending=True)
        asks = _subtract(asks, exclude.get("asks", []), descending=False)
    if not bids or not asks:
        return None
    abb, aba = adjusted_best(bids, min_size), adjusted_best(asks, min_size)
    if abb is None or aba is None:
        return None
    mid = (abb + aba) / 2
    return {
        "bb": bids[0][0], "ba": asks[0][0], "mid": mid,
        "q1": side_q(bids, mid, v, True), "q2": side_q(asks, mid, v, False),
        "bids": bids[:10], "asks": asks[:10],
    }


def _subtract(lv, ours, descending):
    d = {}
    for p, s in lv:
        d[round(p, 6)] = d.get(round(p, 6), 0) + s
    for p, s in ours:
        k = round(p, 6)
        if k in d:
            d[k] = max(0.0, d[k] - s)
    out = [(p, s) for p, s in d.items() if s > 1e-9]
    return sorted(out, key=lambda x: x[0], reverse=descending)


def our_share(st, v, bid, ask, size_bid, size_ask):
    """Our Q_min and reward share (conservative: competitors credited with max(Q1, Q2); central: their Q_min)."""
    mid = st["mid"]
    sb = round((mid - bid) * 100, 6) if bid is not None else -1
    sa = round((ask - mid) * 100, 6) if ask is not None else -1
    o1 = s_score(v, sb) * size_bid if 0 <= sb < v and size_bid > 0 else 0.0
    o2 = s_score(v, sa) * size_ask if 0 <= sa < v and size_ask > 0 else 0.0
    ours = q_min(o1, o2, mid)
    if ours <= 0:
        return 0.0, 0.0, 0.0
    comp_cons = max(st["q1"], st["q2"])
    comp_cent = q_min(st["q1"], st["q2"], mid)
    return ours, ours / (ours + comp_cons), ours / (ours + comp_cent)
