"""Direct-mode tests for TolerancePriceOracle (web + LLM mocked)."""

from tests.direct.conftest import to_hex

C = "contracts/tolerance_price_oracle.py"
URL = "https://supplier.example.com/oak-hybrid"
PAGE = {"status": 200, "body": "Oak Hybrid Plank - $49.90 per m2"}


def _feed(direct_vm, direct_deploy, who, tol=100):
    c = direct_deploy(C)
    direct_vm.sender = who
    fid = c.create_feed(URL, "price per square metre of Oak hybrid plank", "AUD", tol)
    return c, fid


def test_create_feed(direct_vm, direct_deploy, direct_alice):
    c, fid = _feed(direct_vm, direct_deploy, direct_alice)
    f = c.get_feed(fid)
    assert fid == "feed-1"
    assert f["owner"] == to_hex(direct_alice)
    assert f["has_value"] is False
    assert c.get_feed_count() == 1


def test_create_feed_validation(direct_vm, direct_deploy, direct_alice):
    c = direct_deploy(C)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("URL must be https"):
        c.create_feed("http://x.com", "price of thing", "AUD", 100)
    with direct_vm.expect_revert("Target description too short"):
        c.create_feed(URL, "p", "AUD", 100)
    with direct_vm.expect_revert("Tolerance must be 1-2000 bps"):
        c.create_feed(URL, "price of thing", "AUD", 5000)


def test_refresh_stores_value_and_history(direct_vm, direct_deploy, direct_alice):
    c, fid = _feed(direct_vm, direct_deploy, direct_alice)
    direct_vm.mock_web(r".*supplier\.example\.com.*", PAGE)
    direct_vm.mock_llm(r".*Extract ONE number.*", '{"value_minor": 4990}')
    assert c.refresh(fid) == 4990
    assert c.refresh(fid) == 4990
    f = c.get_feed(fid)
    assert f["latest_minor"] == 4990
    assert f["updates"] == 2
    assert f["history"] == [4990, 4990]
    assert c.get_average(fid, 5) == 4990


def test_value_not_found(direct_vm, direct_deploy, direct_alice):
    c, fid = _feed(direct_vm, direct_deploy, direct_alice)
    direct_vm.mock_web(r".*supplier\.example\.com.*", PAGE)
    direct_vm.mock_llm(r".*Extract ONE number.*", '{"value_minor": -1}')
    with direct_vm.expect_revert("Value not found on page"):
        c.refresh(fid)


def test_average_requires_data(direct_vm, direct_deploy, direct_alice):
    c, fid = _feed(direct_vm, direct_deploy, direct_alice)
    with direct_vm.expect_revert("No data yet"):
        c.get_average(fid, 3)


def test_only_owner_sets_tolerance(direct_vm, direct_deploy, direct_alice, direct_bob):
    c, fid = _feed(direct_vm, direct_deploy, direct_alice)
    c.set_tolerance(fid, 250)
    assert c.get_feed(fid)["tolerance_bps"] == 250
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Only the feed owner"):
        c.set_tolerance(fid, 10)
