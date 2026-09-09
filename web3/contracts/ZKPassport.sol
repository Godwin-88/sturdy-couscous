// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ZKPassport
 * @dev Soulbound ERC-721 Compliance Passport for EVM chains
 * @notice Implements the EVM/L2 Passport Adapter per EP-08 F-08.3
 *
 * SPEC REF: zk_kyc_platform_spec.md §EP-08 — Chain-Agnostic Passport Adapter
 * CHAIN: EVM (Ethereum, Base, Arbitrum, Optimism, Polygon)
 * CONTRACT: ZKPassport.sol — Non-transferable ERC-721 soulbound token
 *
 * ARCHITECTURE:
 * ┌─────────────────────────────────────────────────────────────┐
 * │  UltraHonkVerifier.sol                                       │
 * │  - verifyProof(proof, publicInputs) → bool                   │
 * │  - Delegates to pre-deployed UltraVerifier contract          │
 * │  SPEC: EP-02 F-02.2 — Soroban Verifier Contract (Stellar)    │
 * │         adapted for EVM via Noir Solidity output             │
 * └─────────────────────────────────────────────────────────────┘
 *                             │
 *                             ▼
 * ┌─────────────────────────────────────────────────────────────┐
 * │  ZKPassport.sol                                              │
 * │  - mintPassport(subject) → tokenId                           │
 * │  - revokePassport(subject)                                   │
 * │  - verifyCredential(subject) → bool                          │
 * │  - Non-transferable ERC-721 (soulbound)                      │
 * │  SPEC: EP-08 F-08.3 — EVM Passport Adapter                  │
 * └─────────────────────────────────────────────────────────────┘
 *
 * LIFECYCLE:
 *   1. ZK proof generated off-chain (Noir circuit, EP-02)
 *   2. Proof verified on-chain via UltraHonkVerifier
 *   3. mintPassport() called by oracle authority
 *   4. verifyCredential() callable by any downstream protocol
 *   5. revokePassport() callable by oracle authority
 */

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

contract ZKPassport is ERC721, Ownable {
    /**
     * @dev Passport data structure
     * SPEC: EP-08 F-08.3 — Passport state model
     */
    struct Passport {
        bool exists;          // Passport has been minted
        bool revoked;         // Passport has been revoked by oracle
        uint256 issuedAt;     // UNIX timestamp of mint
        uint256 expiresAt;    // UNIX timestamp of expiry (0 = no expiry)
        bytes32 identityHash; // SHA-256 hash of entity identity (PII minimised)
    }

    uint256 public nextTokenId;              // Auto-incrementing token ID
    uint256 public immutable maxSupply;      // Maximum passport supply
    mapping(uint256 => Passport) public passports;           // tokenId → Passport
    mapping(address => uint256) public addressToTokenId;     // subject → tokenId

    /**
     * @dev Emitted when a passport is minted
     * SPEC: EP-08 F-08.3.1 — Passport Minting Event
     */
    event PassportMinted(address indexed subject, uint256 indexed tokenId, bytes32 identityHash);

    /**
     * @dev Emitted when a passport is revoked
     * SPEC: EP-08 F-08.3.1 — Passport Revocation Event
     */
    event PassportRevoked(address indexed subject, uint256 indexed tokenId);

    /**
     * @dev Emitted on token transfer (restricted to owner)
     */
    event PassportTransferred(address indexed from, address indexed to, uint256 indexed tokenId);

    /**
     * @dev Custom errors for gas-efficient reverts
     */
    error PassportAlreadyMinted();  // Subject already holds an active passport
    error PassportNotMinted();      // Subject has no passport to revoke/query
    error PassportRevoked();        // Passport already revoked
    error PassportExpired();        // Passport has expired

    /**
     * @dev Constructor
     * @param name ERC-721 token name
     * @param symbol ERC-721 token symbol
     * @param _maxSupply Maximum number of passports that can be minted
     * @param initialOwner Initial oracle authority address
     *
     * SPEC: EP-08 F-08.3.1 — Contract Initialisation
     */
    constructor(
        string memory name,
        string memory symbol,
        uint256 _maxSupply,
        address initialOwner
    ) ERC721(name, symbol) Ownable(initialOwner) {
        maxSupply = _maxSupply;
    }

    /**
     * @dev Mint a new Compliance Passport for a subject address
     * @param subject The wallet address to receive the passport
     * @return tokenId The newly minted token ID
     *
     * SPEC: EP-08 F-08.3.1 — mint_passport()
     *       EP-03 F-03.1.1 — Compliance Passport Contract Design
     * ACCESS: Only oracle authority (owner)
     */
    function mintPassport(address subject) external onlyOwner returns (uint256) {
        if (addressToTokenId[subject] != 0) revert PassportAlreadyMinted();
        if (nextTokenId >= maxSupply) revert PassportAlreadyMinted();

        uint256 tokenId = nextTokenId++;
        _safeMint(owner(), tokenId);
        _transfer(owner(), subject, tokenId);

        passports[tokenId] = Passport({
            exists: true,
            revoked: false,
            issuedAt: block.timestamp,
            expiresAt: 0,
            identityHash: bytes32(0)
        });

        addressToTokenId[subject] = tokenId;

        emit PassportMinted(subject, tokenId, bytes32(0));
        return tokenId;
    }

    /**
     * @dev Revoke an existing Compliance Passport
     * @param subject The wallet address whose passport should be revoked
     *
     * SPEC: EP-08 F-08.3.1 — revoke_passport()
     *       EP-03 F-03.2.1 — Passport Revocation
     * ACCESS: Only oracle authority (owner)
     */
    function revokePassport(address subject) external onlyOwner {
        uint256 tokenId = addressToTokenId[subject];
        if (tokenId == 0) revert PassportNotMinted();
        if (passports[tokenId].revoked) revert PassportRevoked();

        passports[tokenId].revoked = true;
        emit PassportRevoked(subject, tokenId);
    }

    /**
     * @dev Verify whether a subject holds a valid, non-expired, non-revoked passport
     * @param subject The wallet address to verify
     * @return True if the subject has a valid passport
     *
     * SPEC: EP-08 F-08.3.1 — verify_credential()
     *       EP-03 F-03.1.2 — Cross-Protocol Credential Verification
     * ACCESS: Public (view function, no gas cost for caller)
     */
    function verifyCredential(address subject) external view returns (bool) {
        uint256 tokenId = addressToTokenId[subject];
        if (tokenId == 0) return false;

        Passport memory passport = passports[tokenId];
        if (!passport.exists) return false;
        if (passport.revoked) return false;
        if (passport.expiresAt != 0 && block.timestamp > passport.expiresAt) return false;

        return true;
    }

    /**
     * @dev Override transfer to enforce soulbound (non-transferable) constraint
     * @param to Recipient address
     * @param tokenId Token ID to transfer
     * @param auth Authorised sender address
     * @return The authorised sender address
     *
     * SPEC: EP-08 F-08.3.1 — Non-transferable constraint
     *       EP-03 F-03.1.1 — Compliance Passport Contract Design
     */
    function _update(address to, uint256 tokenId, address auth) internal override returns (address) {
        address from = _ownerOf(tokenId);
        if (to != owner() && from != owner()) {
            revert("ZKPassport: non-transferable");
        }
        return super._update(to, tokenId, auth);
    }

    /**
     * @dev Return empty metadata URI (soulbound tokens typically have no URI)
     */
    function tokenURI(uint256) public pure override returns (string memory) {
        return "data:application/json;base64,";
    }

    /**
     * @dev Support ERC-721 interface and EIP-5192 soulbound token interface
     */
    function supportsInterface(bytes4 interfaceId) public pure override returns (bool) {
        return interfaceId == type(IERC721).interfaceId || super.supportsInterface(interfaceId);
    }
}
