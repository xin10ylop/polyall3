"""Jev (TypeSafe System One, via OpenRouter Decisions API): fast calibrated classification of market toxicity.

Used as a filter: reward farming only works where resting quotes are rarely picked off. Jev scores each market on
whether its outcome tracks a live public number, whether decisive information is due soon, how fast news arrives,
and whether insiders could know the result early.
"""
import os, json, time, threading, datetime as dt
import requests

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "~typesafe/jev-latest"
SPENT = {"usd": 0.0, "calls": 0}
_LOCK = threading.Lock()

QUESTIONS = {
    "realtime": {"type": "noul",
                 "instructions": "Before this market resolves, is its outcome driven by a quantity that the public can watch update continuously or many times per day (e.g. live counts of posts/tweets/views/streams, asset or commodity prices, live vote counts, live sports scores, chart rankings updated daily)?",
                 "criteria": {"true": "Outcome tracks a live, frequently-updated public number or feed",
                              "false": "Outcome depends on a discrete future decision, announcement, or event with no live running tally"}},
    "reveal_soon": {"type": "noul",
                    "instructions": "Given `now` and `end_date`, is decisive information likely to be revealed within the next 72 hours (e.g. a scheduled announcement, ceremony, release, election, data release, meeting, or the deadline itself)?",
                    "criteria": {"true": "Decisive information is scheduled or very likely within 72 hours",
                                 "false": "No decisive information expected within 72 hours"}},
    "news_speed": {"type": "score",
                   "instructions": "How often does new information that could move this market's probability by 5+ percentage points typically arrive?",
                   "criteria": ["Rarely (weeks or more between relevant news)", "Occasionally (every few days)",
                                "Often (daily)", "Constantly (hourly or real-time)"]},
    "insider": {"type": "noul",
                "instructions": "Could some traders plausibly know the outcome well before the public (e.g. company/lab insiders, award committees, content creators, government officials, organizers)?",
                "criteria": {"true": "Plausible insider knowledge exists",
                             "false": "Outcome is not knowable in advance by any identifiable insiders"}},
}


def decide(state, questions, tries=3):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    for i in range(tries):
        try:
            r = requests.post(URL, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                            "X-Title": "pmbot"},
                              json={"model": MODEL, "state": state, "questions": questions}, timeout=30)
            d = r.json()
            if "answers" in d:
                with _LOCK:
                    SPENT["usd"] += float((d.get("usage") or {}).get("cost") or 0)
                    SPENT["calls"] += 1
                return d["answers"]
        except Exception:
            pass
        time.sleep(1 + i)
    return None


class ToxicityCache:
    """Persistent per-market Jev toxicity scores (re-scored when older than max_age_h)."""

    def __init__(self, path, max_age_h=24):
        self.path, self.max_age = path, max_age_h * 3600
        try:
            self.d = json.load(open(path))
        except Exception:
            self.d = {}

    def save(self):
        with _LOCK:
            snap = dict(self.d)
        tmp = self.path + ".tmp"
        json.dump(snap, open(tmp, "w"))
        os.replace(tmp, self.path)

    def get(self, cid, question, description, end_date):
        e = self.d.get(cid)
        if e and time.time() - e.get("ts", 0) < self.max_age:
            return e
        st = {"question": question, "rules": (description or "")[:900], "end_date": end_date,
              "now": dt.datetime.utcnow().isoformat(timespec="minutes") + "Z"}
        a = decide(st, QUESTIONS)
        try:
            e = {"realtime": float(a["realtime"]["noul"]), "reveal_soon": float(a["reveal_soon"]["noul"]),
                 "news_speed": float(a["news_speed"]["score"]), "insider": float(a["insider"]["noul"]),
                 "ts": time.time(), "q": question}
        except Exception:
            return e  # API unavailable or unexpected shape: keep the stale score (None -> treated as unsafe)
        with _LOCK:
            self.d[cid] = e
        return e


CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_PROMPT = """You screen Polymarket markets for a market-making bot that rests small two-sided quotes to earn liquidity
rewards. The bot loses money when informed traders hit its quotes right before the price moves. Read the market and
answer strictly as JSON with keys: realtime (probability 0-1 that the outcome tracks a live, frequently-updated public
number such as counts, prices, rankings, polls), reveal_soon (probability 0-1 that decisive information arrives within
72 hours of `now`), news_speed (0=rarely/weeks, 1=every few days, 2=daily, 3=hourly/real-time), insider (probability 0-1
that identifiable insiders could know the result early), reasoning (<=40 words). Market:
"""


def llm_review(question, description, end_date, model, tries=2):
    """Escalation step of the Jev cascade: a frontier LLM re-scores a market Jev found borderline."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key or not model:
        return None
    now = dt.datetime.utcnow().isoformat(timespec="minutes") + "Z"
    body = {"model": model, "max_tokens": 400, "temperature": 0,
            "messages": [{"role": "user", "content": LLM_PROMPT + json.dumps(
                {"question": question, "rules": (description or "")[:3000], "end_date": end_date, "now": now})}]}
    for i in range(tries):
        try:
            r = requests.post(CHAT_URL, headers={"Authorization": f"Bearer {key}", "X-Title": "pmbot"}, json=body,
                              timeout=90).json()
            txt = r["choices"][0]["message"]["content"]
            d = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
            with _LOCK:
                SPENT["usd"] += float((r.get("usage") or {}).get("cost") or 0)
                SPENT["calls"] += 1
            return {k: float(d[k]) for k in ("realtime", "reveal_soon", "news_speed", "insider")} | {
                "reasoning": str(d.get("reasoning", ""))[:300]}
        except Exception:
            time.sleep(2 + i)
    return None


def borderline(tox, cfg, margin=0.15):
    if tox is None:
        return False
    return (abs(tox["realtime"] - cfg["max_realtime"]) < margin or abs(tox["reveal_soon"] - cfg["max_reveal_soon"]) < margin
            or abs(tox["news_speed"] - cfg["max_news_speed"]) < 2 * margin)


def is_safe(tox, cfg):
    """Toxicity gate. Missing score => unsafe when a key is configured (fail closed), safe otherwise (no Jev)."""
    if tox is None:
        return not os.environ.get("OPENROUTER_API_KEY")
    if tox.get("llm"):  # the LLM's verdict overrides Jev on escalated (borderline) markets
        tox = tox["llm"]
    return (tox["realtime"] <= cfg["max_realtime"] and tox["reveal_soon"] <= cfg["max_reveal_soon"]
            and tox["news_speed"] <= cfg["max_news_speed"])
