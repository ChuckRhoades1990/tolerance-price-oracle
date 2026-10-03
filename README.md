# TolerancePriceOracle

A GenLayer Intelligent Contract that turns **any public web page into an on-chain numeric feed**, using a **tolerance-based equivalence check** so validators can agree on scraped numbers without demanding exact matches.

## Why
Real-world prices (building materials, freight, rates) live on ordinary web pages, not on Chainlink. Scraped numbers vary in format (`$49.90`, `49.9 AUD/m²`) and LLMs sometimes round:
- **strict equality** breaks consensus on harmless differences;
- **LLM "are these similar?" comparison** is too loose for money.

This contract sits in between: every validator extracts the value itself and accepts the leader's value only if it is within the feed's tolerance, measured in basis points.

## How it works
1. `create_feed(url, target, unit, tolerance_bps)` registers a feed, e.g. *"price per square metre of Oak hybrid plank"*, `AUD`, `100` (1%).
2. `refresh(feed_id)`: the leader renders the page (`gl.nondet.web.render`), the LLM extracts the value in **minor units** (cents), and validators re-run the extraction and run the tolerance check.
3. Values are stored as integers, so state is deterministic. A bounded history (last 20) feeds `get_average`.
4. If the value isn't on the page, everyone must agree on `-1` and the refresh reverts, so nothing is recorded.

### Consensus design (`gl.vm.run_nondet_unsafe`)
```
accept if |leader - mine| * 10000 <= tolerance_bps * mine
```
It has explicit handling for "not found" (`-1`) and zero values. The tolerance is capped at 20% and only the feed owner can change it.

## Methods
| Method | Type |
|---|---|
| `create_feed(url, target, unit, tolerance_bps) -> str` | write |
| `refresh(feed_id) -> int` | write (non-deterministic, consensus) |
| `set_tolerance(feed_id, tolerance_bps)` | write, owner only |
| `get_feed(feed_id) -> dict` | view |
| `get_average(feed_id, last_n) -> int` | view |
| `get_feed_count() -> int` | view |

## Use cases
- Trade quoting tools that need current material prices
- Escrow or insurance contracts that settle against a published rate
- Simple price indexes for goods with no crypto oracle

## Deployment
GenLayer Studio (studionet): see the explorer link in the submission.

## Tests
```bash
pip install -r requirements.txt
genvm-lint check contracts/tolerance_price_oracle.py
python -m pytest tests/direct -v
```
The tests mock the web page and the LLM. They cover feed creation, input validation, refresh and history, the value-not-found revert, averaging, and owner-only tolerance changes.

## License
MIT
