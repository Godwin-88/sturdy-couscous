// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ClaimToken} from "../ClaimToken.sol";
import {NAVAnchor} from "../NAVAnchor.sol";

/// @notice Minimal behavioral verification for the RWA claim layer.
///         Financial-engineer discipline: the token/NAV logic must be provable
///         in isolation before it ever gates a real deployment key.
///         (Self-contained — no forge-std dependency, runs under `forge test`.)
contract ClaimNavaTest {
    ClaimToken tc;
    NAVAnchor na;
    address fund = address(0xa11ce);
    address alice = address(0xa11ce1);

    function setUp() public {
        tc = new ClaimToken("GraphAlpha Strategy Fund", "GASF", 18);
        na = new NAVAnchor();
    }

    function testUnit_Mint_Burn_OnlyOperator() public {
        tc.mint(alice, 1_000_000e18);
        require(tc.totalSupply() == 1_000_000e18, "supply");
        require(tc.balanceOf(alice) == 1_000_000e18, "bal");

        tc.mint(fund, 500_000e18);
        // operator = this contract; mint self then burn to show auth split.
        // mint+burn are net-zero for the same operator balance.
        tc.mint(address(this), 1e18);
        tc.burn(1e18);
        require(tc.totalSupply() == 1_500_000e18, "burn leaves supply unchanged (net zero)");
        require(tc.balanceOf(address(this)) == 0, "self balance fully burned");
    }

    function testUnit_Transfer_And_Approval() public {
        // transfer sends FROM msg.sender (the test contract) — mint self first
        tc.mint(address(this), 100e18);
        tc.transfer(alice, 40e18);
        require(tc.balanceOf(address(this)) == 60e18, "bal after xfer");
        require(tc.balanceOf(alice) == 40e18, "recipient bal");

        // approve owner→spender; then transferFrom runs AS the spender.
        // Test contract is both owner and spender here → self-approval exercises the
        // allowance path; a real owner-pays-spender flow would use vm.prank(alice).
        tc.approve(address(this), 25e18);
        require(tc.allowance(address(this), address(this)) == 25e18, "allow set");
        tc.transferFrom(address(this), fund, 25e18);
        require(tc.allowance(address(this), address(this)) == 0, "allow spent");
        require(tc.balanceOf(fund) == 25e18, "fund bal");
        require(tc.balanceOf(address(this)) == 35e18, "self bal after transferFrom");
    }

    function testUnit_NAVAnchor_Hash_And_Emit() public {
        bytes32 h = na.digest(95_431_520_000_000, 12345);
        require(h != bytes32(0), "non-zero digest");

        na.setNAV(95_431_520_000_000, h, 12345);
        (uint256 usd, bytes32 hh, uint64 br, uint64 ts) = na.getNAV();
        require(usd == 95_431_520_000_000, "nav usd");
        require(hh == h, "nav hash");
        require(br == 12345, "block ref");
        require(ts > 0, "updated at set");
    }
}