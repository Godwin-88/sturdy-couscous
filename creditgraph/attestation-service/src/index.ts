/**
 * CreditGraph Attestation Service
 *
 * Wraps the real Attestcoin Protocol SDK (@gluwa/usc-sdk) behind a small HTTP
 * API so the Python backend can verify cross-chain transaction evidence
 * without re-implementing Merkle/continuity proving.
 *
 * Endpoints:
 *   GET  /health   -> liveness
 *   GET  /chains   -> supported source chains (PrecompileChainInfoProvider)
 *   POST /verify   -> generate + verify a transaction inclusion proof
 *
 * Per E1-US2, unverifiable attestations are returned as `verified: false`
 * (never conflated with verified evidence).
 */

import { JsonRpcApiProvider, JsonRpcProvider } from 'ethers';
import Fastify from 'fastify';
import { chainInfo, blockProver, proofProvider } from '@gluwa/usc-sdk';

const app = Fastify({ logger: true });

const SOURCE_RPC = process.env.SOURCE_RPC_URL ?? 'https://sepolia.infura.io/v3/';
const CREDITCOIN_RPC =
  process.env.CREDITCOIN_RPC_URL ?? 'https://rpc.cc3-testnet.creditcoin.network';
const PROVER_URL =
  process.env.ATTESTCOIN_PROVER_URL ?? 'https://prover.cc3-testnet.creditcoin.network';
const PROVER_TIMEOUT_MS = Number(process.env.ATTESTCOIN_PROVER_TIMEOUT_MS ?? 5000);
const ATTEST_WAIT_TIMEOUT_MS = Number(process.env.ATTESTCOIN_WAIT_TIMEOUT_MS ?? 900000);

const sourceProvider: JsonRpcApiProvider = new JsonRpcProvider(SOURCE_RPC);
const creditcoinProvider: JsonRpcApiProvider = new JsonRpcProvider(CREDITCOIN_RPC);

const chainInfoProvider = new chainInfo.PrecompileChainInfoProvider(creditcoinProvider);
const prover = new blockProver.PrecompileBlockProver(creditcoinProvider);

interface VerifyRequest {
  txHash: string;
  chainKey?: number;
}

app.get('/health', async () => ({ status: 'ok', service: 'creditgraph-attestation' }));

app.get('/chains', async () => {
  const chains = await chainInfoProvider.getSupportedChains();
  return { chains };
});

app.post('/verify', async (req, reply) => {
  const { txHash, chainKey } = req.body as VerifyRequest;

  if (!txHash || typeof txHash !== 'string') {
    return reply.code(400).send({ error: 'txHash is required' });
  }

  try {
    // Resolve chain key if not provided (E1-US1: resolve supported chain).
    let resolvedChainKey = chainKey;
    if (resolvedChainKey === undefined) {
      const chains = await chainInfoProvider.getSupportedChains();
      if (chains.length === 0) {
        return reply.code(422).send({
          verified: false,
          status: 'unverified',
          reason: 'no_supported_chains',
        });
      }
      resolvedChainKey = chains[0].chainKey;
    }

    // Find the block containing the transaction on the source chain.
    const tx = await sourceProvider.getTransaction(txHash);
    if (!tx || tx.blockNumber === null) {
      return reply.code(422).send({
        verified: false,
        status: 'unverified',
        reason: 'transaction_not_found',
        txHash,
      });
    }
    const blockNumber = tx.blockNumber;

    // Wait until Creditcoin has attested that block (E1-US2: attestation-backed).
    const proofBuilder = new proofProvider.service.ProofBuilder(
      resolvedChainKey,
      PROVER_URL,
      PROVER_TIMEOUT_MS,
    );
    await proofBuilder.waitUntilHeightAttested(
      resolvedChainKey,
      blockNumber,
      15000, // pollIntervalMs
      ATTEST_WAIT_TIMEOUT_MS, // waitTimeoutMs
    );

    // Generate the inclusion proof (Merkle + continuity).
    const result = await proofBuilder.getProof(txHash);
    if (!result.success || !result.data) {
      return reply.code(422).send({
        verified: false,
        status: 'unverified',
        reason: 'proof_generation_failed',
        error: result.error,
        txHash,
      });
    }

    const proofData = result.data;

    // Verify on-chain via Creditcoin's verifier precompile.
    const verified = await prover.verifySingle(
      proofData.chainKey,
      proofData.headerNumber,
      proofData.txBytes,
      proofData.merkleProof,
      proofData.continuityProof,
    );

    return {
      verified,
      status: verified ? 'verified' : 'unverified',
      txHash,
      chainKey: proofData.chainKey,
      headerNumber: proofData.headerNumber,
      sourceChain: 'ethereum-sepolia',
      verifiedAt: new Date().toISOString(),
      proof: {
        merkleProof: proofData.merkleProof,
        continuityProof: proofData.continuityProof,
        cached: proofData.cached,
      },
    };
  } catch (err) {
    app.log.error(err);
    return reply.code(500).send({
      verified: false,
      status: 'unverified',
      reason: 'verification_error',
      error: err instanceof Error ? err.message : String(err),
      txHash,
    });
  }
});

const PORT = Number(process.env.PORT ?? 8080);
const HOST = process.env.HOST ?? '0.0.0.0';

app.listen({ port: PORT, host: HOST }, (err) => {
  if (err) {
    app.log.error(err);
    process.exit(1);
  }
});