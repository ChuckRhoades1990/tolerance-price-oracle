# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
TolerancePriceOracle — web-grounded numeric feeds with tolerance consensus.

Anyone can register a feed: a public web page plus a plain-English description
of the number to extract (e.g. "price per square metre of Oak hybrid plank
in AUD"). Calling `refresh(feed_id)` makes validators fetch the page, have
their LLM extract the number, and agree on it.

Why a custom equivalence check: numbers scraped from live pages differ in
format ("$49.90", "49.9 AUD/m²") and LLMs occasionally round. Strict equality
would fail consensus; plain LLM comparison is too loose for money. Here each
validator independently extracts its own value and accepts the leader's only
if it is within the feed's tolerance (basis points). Values are stored as
integers in minor units (cents) so on-chain state stays deterministic.

Each feed keeps a bounded history and an update counter, so consumers
(quoting tools, escrow contracts, index trackers) can average recent values.
"""
import json
from dataclasses import dataclass
from genlayer import *

MAX_HISTORY = 20
MAX_TOLERANCE_BPS = 2000  # 20 %


@allow_storage
@dataclass
class Feed:
    id: str
    owner: Address
    url: str
    target: str
    unit: str
    tolerance_bps: u256
    latest_minor: u256
    has_value: bool
    updates: u256
    history: str  # JSON list of ints (minor units), newest last


class TolerancePriceOracle(gl.Contract):
    feeds: TreeMap[str, Feed]
    feed_count: u256

    def __init__(self):
        self.feed_count = u256(0)

    # ── helpers ───────────────────────────────────────────────────────────

    def _get(self, feed_id: str) -> Feed:
        if feed_id not in self.feeds:
            raise gl.vm.UserError("Feed not found")
        return self.feeds[feed_id]

    def _extract(self, url: str, target: str, unit: str, tolerance_bps: int) -> int:
        def leader_fn() -> int:
            page = gl.nondet.web.render(url, mode="text")[:12000]
            prompt = f"""Extract ONE number from the web page below.

WHAT TO EXTRACT: {target}
UNIT: {unit}

Rules:
- Return the value in MINOR units (e.g. cents): 49.90 dollars -> 4990.
- If the value is not clearly present, return -1.

Respond ONLY with JSON: {{"value_minor": int}}

PAGE:
{page}"""
            res = gl.nondet.exec_prompt(prompt, response_format="json")
            return int(res.get("value_minor", -1))

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            theirs = int(leader_result.calldata)
            mine = leader_fn()
            if theirs < 0 or mine < 0:
                return theirs == mine
            if mine == 0:
                return theirs == 0
            diff = abs(theirs - mine) * 10000
            return diff <= tolerance_bps * mine

        return gl.vm.run_nondet_unsafe(leader_fn, validator_fn)

    # ── writes ────────────────────────────────────────────────────────────

    @gl.public.write
    def create_feed(self, url: str, target: str, unit: str, tolerance_bps: int) -> str:
        if not url.startswith("https://"):
            raise gl.vm.UserError("URL must be https")
        if len(target.strip()) < 5:
            raise gl.vm.UserError("Target description too short")
        if tolerance_bps < 1 or tolerance_bps > MAX_TOLERANCE_BPS:
            raise gl.vm.UserError("Tolerance must be 1-2000 bps")
        self.feed_count = u256(int(self.feed_count) + 1)
        feed_id = f"feed-{int(self.feed_count)}"
        self.feeds[feed_id] = Feed(
            id=feed_id,
            owner=gl.message.sender_address,
            url=url,
            target=target,
            unit=unit,
            tolerance_bps=u256(tolerance_bps),
            latest_minor=u256(0),
            has_value=False,
            updates=u256(0),
            history="[]",
        )
        return feed_id

    @gl.public.write
    def refresh(self, feed_id: str) -> int:
        feed = self._get(feed_id)
        value = self._extract(feed.url, feed.target, feed.unit, int(feed.tolerance_bps))
        if value < 0:
            raise gl.vm.UserError("Value not found on page")
        hist = json.loads(feed.history)
        hist.append(value)
        feed.history = json.dumps(hist[-MAX_HISTORY:])
        feed.latest_minor = u256(value)
        feed.has_value = True
        feed.updates = u256(int(feed.updates) + 1)
        return value

    @gl.public.write
    def set_tolerance(self, feed_id: str, tolerance_bps: int) -> None:
        feed = self._get(feed_id)
        if gl.message.sender_address != feed.owner:
            raise gl.vm.UserError("Only the feed owner")
        if tolerance_bps < 1 or tolerance_bps > MAX_TOLERANCE_BPS:
            raise gl.vm.UserError("Tolerance must be 1-2000 bps")
        feed.tolerance_bps = u256(tolerance_bps)

    # ── views ─────────────────────────────────────────────────────────────

    @gl.public.view
    def get_feed(self, feed_id: str) -> dict:
        f = self._get(feed_id)
        return {
            "id": f.id,
            "owner": f.owner.as_hex,
            "url": f.url,
            "target": f.target,
            "unit": f.unit,
            "tolerance_bps": int(f.tolerance_bps),
            "latest_minor": int(f.latest_minor),
            "has_value": f.has_value,
            "updates": int(f.updates),
            "history": json.loads(f.history),
        }

    @gl.public.view
    def get_average(self, feed_id: str, last_n: int) -> int:
        hist = json.loads(self._get(feed_id).history)
        if len(hist) == 0:
            raise gl.vm.UserError("No data yet")
        n = max(1, min(last_n, len(hist)))
        window = hist[-n:]
        return sum(window) // len(window)

    @gl.public.view
    def get_feed_count(self) -> int:
        return int(self.feed_count)
