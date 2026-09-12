// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title NAVAnchor
 * @dev On-chain anchor for the strategy fund's NAV — written once per orchestrator cycle.
 *
 * RWA STORY (P11 / BUIDL-CTC):
 *   The off-chain trading book (Alpaca/Kraken paper) produces a realtime NAV. Each
 *   cycle the bot canonicalizes the book state into a content-addressed digest
 *   (sha256) and records it HERE in a known contract — not a raw 0-value tx. The
 *   transaction that carries this write is then attested on Creditcoin via Attestcoin
 *   (/verify), so the on-chain NAV ledger becomes cross-chain provable: "block X,
 *   NAV $95,431.52, digest 0x…, attested".
 *
 * DESIGN:
 *   - operator-only setNAV (fund manager / bot relay key). Nobody else can write.
 *   - Each write overwrites last snapshot and emits NAVAnchored(uint256 navUsd,
 *     bytes32 navHash, uint64 blockRef, uint64 updatedAt) — a clean audit trail.
 *   - getNAV() view returns the latest snapshot for the API/chat/KG to cite.
 */

contract NAVAnchor {
    address public operator;
    address public operatorPending;

    uint256 public lastNavUsd;
    bytes32 public lastNavHash;
    uint64  public lastBlockRef;
    uint64  public lastUpdatedAt;

    event NAVAnchored(
        uint256 indexed navUsd,
        bytes32 indexed navHash,
        uint64 indexed blockRef,
        uint64 updatedAt
    );
    event OperatorTransferred(address indexed oldOp, address indexed newOp);

    constructor() {
        operator = msg.sender;
    }

    modifier onlyOperator() {
        require(msg.sender == operator, "NAVAnchor: not operator");
        _;
    }

    /// @param navUsd     NAV in USD fixed-point (1e6 → $1.00 precision ok for a fund)
    /// @param navHash    sha256 of the canonical book-state JSON
    /// @param blockRef   block/height ref of the current cycle (for humans + attestation)
    function setNAV(uint256 navUsd, bytes32 navHash, uint64 blockRef) external onlyOperator {
        lastNavUsd    = navUsd;
        lastNavHash   = navHash;
        lastBlockRef  = blockRef;
        lastUpdatedAt = uint64(block.timestamp);
        emit NAVAnchored(navUsd, navHash, blockRef, lastUpdatedAt);
    }

    /// @notice Read the latest anchored NAV snapshot (used by API / chat / KG).
    function getNAV()
        external
        view
        returns (uint256 navUsd, bytes32 navHash, uint64 blockRef, uint64 updatedAt)
    {
        return (lastNavUsd, lastNavHash, lastBlockRef, lastUpdatedAt);
    }

    /// @notice Hash the canonical payload off-chain style (mirror of bot's digest logic).
    function digest(uint256 navUsd, uint64 blockRef) external pure returns (bytes32) {
        return keccak256(abi.encodePacked("graphalpha:nav", navUsd, blockRef));
    }

    function proposeOperator(address next) external onlyOperator {
        operatorPending = next;
    }

    function acceptOperator() external {
        require(msg.sender == operatorPending, "NAVAnchor: not pending operator");
        address prev = operator;
        operator = msg.sender;
        operatorPending = address(0);
        emit OperatorTransferred(prev, msg.sender);
    }
}