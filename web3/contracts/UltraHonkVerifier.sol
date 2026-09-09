// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title UltraHonkVerifier
 * @dev Wrapper around a pre-deployed UltraHonk verifier contract
 * @notice Delegates proof verification to canonical verifier address
 *
 * SPEC REF: zk_kyc_platform_spec.md §EP-02 — Zero-Knowledge Compliance Oracle Circuit
 *           EP-08 F-08.3 — EVM Passport Adapter
 * CHAIN: EVM (Ethereum, Base, Arbitrum, Optimism, Polygon)
 * CONTRACT: UltraHonkVerifier.sol — Verifier proxy contract
 *
 * DEPLOYMENT:
 *   1. Deploy canonical UltraVerifier (pre-deployed Noir Solidity output)
 *   2. Deploy this wrapper with verifier address as constructor arg
 *   3. ZKPassport.sol holds immutable reference to this wrapper
 *
 * SPEC REF: EP-02 F-02.2.1 — Verifier Contract Deployment
 */

import {UltraVerifier} from "./UltraVerifier.sol";

contract UltraHonkVerifier {
    /**
     * @dev Immutable reference to the pre-deployed UltraVerifier
     */
    UltraVerifier public immutable verifier;

    /**
     * @dev Constructor
     * @param verifierAddress Address of pre-deployed UltraVerifier contract
     *
     * SPEC: EP-02 F-02.2.1 — Verifier deployment with canonical address
     */
    constructor(address verifierAddress) {
        verifier = UltraVerifier(verifierAddress);
    }

    /**
     * @dev Verify a Noir UltraHonk proof
     * @param proof Serialized UltraHonk proof bytes
     * @param publicInputs Serialized public inputs
     * @return True if proof verification succeeds
     *
     * SPEC: EP-02 F-02.2.2 — On-Chain Compliance Attestation
     */
    function verifyProof(
        bytes calldata proof,
        bytes calldata publicInputs
    ) external view returns (bool) {
        return verifier.verify(proof, publicInputs);
    }
}
