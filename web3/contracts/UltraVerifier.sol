// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title UltraVerifier
 * @dev Interface for UltraHonk ZK proof verifier
 * @notice Pre-deployed verifier contract for Noir UltraHonk proofs
 *
 * SPEC REF: zk_kyc_platform_spec.md §EP-02 — Zero-Knowledge Compliance Oracle Circuit
 *           EP-08 F-08.3 — EVM Passport Adapter
 * CHAIN: EVM (Ethereum, Base, Arbitrum, Optimism, Polygon)
 * CONTRACT: UltraVerifier.sol — Interface for pre-deployed verifier
 *
 * ARCHITECTURE:
 *   The UltraHonk verifier is deployed once per chain (or shared via canonical address).
 *   ZKPassport.sol holds an immutable reference to this verifier.
 *   Proof verification is a view function — no gas cost for successful verification.
 */

interface IUltraVerifier {
    /**
     * @dev Verify a Noir UltraHonk proof against public inputs
     * @param proof Serialized UltraHonk proof bytes
     * @param publicInputs Serialized public inputs
     * @return True if proof is valid
     *
     * SPEC: EP-02 F-02.2.1 — Verifier Contract Deployment
     */
    function verify(bytes calldata proof, bytes calldata publicInputs) external view returns (bool);
}

/**
 * @title UltraVerifier
 * @dev Canonical UltraHonk verifier interface (EIP-165 compatible)
 */
interface UltraVerifier is IUltraVerifier {}
