// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ClaimToken
 * @dev Minimal ERC-20 "fund share" claim token for the attested strategy fund (RWA).
 *
 * RWA STORY (P11 / BUIDL-CTC):
 *   An off-chain systematic trading book (Alpaca/Kraken paper) is the "real-world
 *   value" being bridged on-chain. Its NAV is anchored every cycle by NAVAnchor.sol
 *   (content-addressed digest) and attested on Creditcoin via Attestcoin. This token
 *   represents a claim on that fund's economics — a tokenized managed-account share.
 *
 * SCOPE CONTROL (deliberate for hackathon safety):
 *   - No OpenZeppelin dependency: standalone, compiles with plain solc.
 *   - operator-only mint/burn (the fund manager). No mint by anyone else.
 *   - No transfer restrictions (keeps the token simple); soulbound/whitelist is
 *     a post-hackathon hardening, NOT in scope.
 *   - Money legs stay on Creditcoin via CTC transfers (execution-service);
 *     this token is the visible, attestable claim layer on Sepolia (chainKey 1,
 *     which Attestcoin actually attests).
 */

contract ClaimToken {
    string  public name;
    string  public symbol;
    uint8   public decimals = 18;

    uint256 internal _totalSupply;
    mapping(address => uint256) internal _balanceOf;
    mapping(address => mapping(address => uint256)) internal _allowance;

    address public operator;          // fund manager — can mint/burn
    address public operatorPending;   // two-step ownership transfer

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event Mint(address indexed to, uint256 value);
    event Burn(address indexed from, uint256 value);
    event OperatorTransferred(address indexed oldOp, address indexed newOp);

    constructor(string memory _name, string memory _symbol, uint8 _decimals) {
        name = _name;
        symbol = _symbol;
        decimals = _decimals;
        operator = msg.sender;
    }

    modifier onlyOperator() {
        require(msg.sender == operator, "ClaimToken: not operator");
        _;
    }

    // ── ERC-20 view ────────────────────────────────────────────────────────
    function totalSupply() external view returns (uint256) { return _totalSupply; }
    function balanceOf(address who) external view returns (uint256) { return _balanceOf[who]; }
    function allowance(address owner, address spender) external view returns (uint256) {
        return _allowance[owner][spender];
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        _allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        require(_allowance[from][msg.sender] >= value, "ClaimToken: allowance exceeded");
        if (_allowance[from][msg.sender] != type(uint256).max) {
            _allowance[from][msg.sender] -= value;
        }
        _transfer(from, to, value);
        return true;
    }

    function _transfer(address from, address to, uint256 value) internal {
        require(_balanceOf[from] >= value, "ClaimToken: insufficient balance");
        _balanceOf[from] -= value;
        _balanceOf[to]   += value;
        emit Transfer(from, to, value);
    }

    // ── Fund-management ────────────────────────────────────────────────────
    function mint(address to, uint256 value) external onlyOperator {
        _totalSupply += value;
        _balanceOf[to] += value;
        emit Mint(to, value);
    }

    function burn(uint256 value) external onlyOperator {
        require(_balanceOf[msg.sender] >= value, "ClaimToken: insufficient burn balance");
        _balanceOf[msg.sender] -= value;
        _totalSupply -= value;
        emit Burn(msg.sender, value);
    }

    // ── Ownership (two-step, avoids permanent lockout) ─────────────────────
    function proposeOperator(address next) external onlyOperator {
        operatorPending = next;
    }

    function acceptOperator() external {
        require(msg.sender == operatorPending, "ClaimToken: not pending operator");
        address prev = operator;
        operator = msg.sender;
        operatorPending = address(0);
        emit OperatorTransferred(prev, msg.sender);
    }
}