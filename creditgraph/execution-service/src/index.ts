/**
 * CreditGraph Execution Service (E10)
 *
 * Wraps the real @polkadot/api to sign and monitor CTC transfer extrinsics on
 * Creditcoin (native Substrate chain), so the Python backend can translate an
 * approved CreditDecision into an executable, on-chain transaction without
 * mockups.
 *
 * Endpoints:
 *   GET  /health             -> liveness
 *   GET  /account            -> lender Substrate address derived from E10 seed
 *   GET  /balance?address=   -> account balance (planck), unauthenticated
 *   POST /execute            -> sign + submit `balances.transferKeepAlive`
 *   POST /monitor            -> scan finalized blocks for txHash + dispatch result
 *
 * Per E10 safety, execution NEVER happens automatically: the Python backend
 * demands an explicit, human-approved CreditDecision (approval_status ==
 * "approved") before calling /execute. If no executor seed is configured, the
 * service returns 503 with a clear reason rather than silently doing nothing.
 */

import { ApiPromise, WsProvider } from '@polkadot/api';
import { Keyring } from '@polkadot/keyring';
import Fastify from 'fastify';

const app = Fastify({ logger: true });

const CREDITCOIN_WS =
  process.env.CREDITCOIN_WS_URL ?? 'wss://rpc.cc3-testnet.creditcoin.network';
const EXECUTOR_SEED = process.env.CREDITCOIN_EXECUTOR_SEED ?? '';
const SS58_FORMAT = Number(process.env.CREDITCOIN_SS58_FORMAT ?? 42);
const MONITOR_SCAN_BLOCKS = Number(process.env.CREDITCOIN_MONITOR_SCAN ?? 200);
const TRANSFER_TIMEOUT_MS = Number(process.env.CREDITCOIN_TRANSFER_TIMEOUT_MS ?? 60000);

const PLANCK_PER_CTC = 1_000_000_000_000_000_000n; // 1e18

/**
 * Convert a decimal CTC string (e.g. "12345.5") to a planck BigInt string,
 * preserving exactness (no float drift).
 */
function ctcToPlanck(amountCtc: string): string {
  const s = amountCtc.trim();
  if (!/^\d+(\.\d{1,18})?$/.test(s)) {
    throw new Error(`invalid CTC amount: ${amountCtc}`);
  }
  const [whole, frac = ''] = s.split('.');
  const fracPadded = (frac + '0'.repeat(18)).slice(0, 18);
  const planck = BigInt(whole) * PLANCK_PER_CTC + BigInt(fracPadded);
  return planck.toString();
}

/** Build a MultiAddress the api accepts: Account20 for EVM, else Id (SS58). */
function toMultiAddress(address: string) {
  if (address.startsWith('0x') && address.length === 42) {
    return { Account20: address };
  }
  return { Id: address };
}

interface ExecuteRequest {
  to: string; // recipient (substrate SS58 or EVM 0x address)
  amount?: string; // CTC units, decimal string
  amountPlanck?: string; // optional exact planck override
}

app.get('/health', async () => ({ status: 'ok', service: 'creditgraph-execution' }));

app.get('/account', async () => {
  if (!EXECUTOR_SEED) {
    return { configured: false, reason: 'executor_seed_not_configured' };
  }
  const keyring = new Keyring({ type: 'sr25519', ss58Format: SS58_FORMAT });
  const pair = keyring.addFromUri(EXECUTOR_SEED);
  return { configured: true, address: pair.address, ss58Format: SS58_FORMAT };
});

app.get('/balance', async (req) => {
  const { address } = req.query as { address?: string };
  if (!address) {
    return { error: 'address is required' };
  }
  const provider = new WsProvider(CREDITCOIN_WS);
  const api = await ApiPromise.create({ provider });
  try {
    const bal = await api.query.system.account(address);
    const data = bal.toJSON() as { data?: { free?: string } };
    return { address, freePlanck: data?.data?.free ?? '0' };
  } finally {
    await api.disconnect();
  }
});

app.post('/execute', async (req, reply) => {
  const { to, amount, amountPlanck } = req.body as ExecuteRequest;

  if (!to || typeof to !== 'string') {
    return reply.code(400).send({ error: 'to is required' });
  }
  if (!amount && !amountPlanck) {
    return reply.code(400).send({ error: 'amount or amountPlanck is required' });
  }
  if (!EXECUTOR_SEED) {
    return reply.code(503).send({ error: 'executor_not_configured' });
  }

  let planckStr: string;
  try {
    planckStr = amountPlanck ?? ctcToPlanck(amount!);
  } catch (err) {
    return reply.code(400).send({
      error: 'invalid_amount',
      detail: err instanceof Error ? err.message : String(err),
    });
  }

  const provider = new WsProvider(CREDITCOIN_WS);
  const api = await ApiPromise.create({ provider });
  const keyring = new Keyring({ type: 'sr25519', ss58Format: SS58_FORMAT });
  const sender = keyring.addFromUri(EXECUTOR_SEED);

  try {
    const balanceCfg = api.createType('Balance', planckStr);
    const tx = api.tx.balances.transferKeepAlive(
      toMultiAddress(to) as never,
      balanceCfg,
    );
    const txHash = tx.hash.toHex();
    app.log.info(`Submitting transfer ${txHash} to ${to}`);

    let confirmation: 'InBlock' | 'Finalized' | null = null;
    let blockNum: string | null = null;
    let success: boolean | null = null;
    let dispatchError: string | null = null;

    const done = await new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => resolve(false), TRANSFER_TIMEOUT_MS);
      tx.signAndSend(sender, (result) => {
        if (result.status.isInBlock) {
          confirmation = 'InBlock';
          blockNum = result.status.hash.toHex();
        }
        if (result.status.isFinalized) {
          confirmation = 'Finalized';
          blockNum = result.status.asFinalized.toString();
        }
        if (result.dispatchError) {
          success = false;
          dispatchError = result.dispatchError.toString();
        } else if (
          result.events.some(
            (e) =>
              e.event.section === 'system' &&
              e.event.method === 'ExtrinsicSuccess',
          )
        ) {
          success = true;
        }
        if (confirmation && success !== null) {
          clearTimeout(timer);
          resolve(true);
        }
      }).catch((err) => {
        clearTimeout(timer);
        app.log.error(err);
        resolve(false);
      });
    });

    if (!done) {
      return {
        txHash,
        status: 'pending',
        submitted: true,
        reason: 'timeout_awaiting_confirmation',
      };
    }

    return {
      txHash,
      status: confirmation ?? 'unknown',
      block: blockNum,
      success,
      dispatchError,
      from: sender.address,
      to,
    };
  } catch (err) {
    app.log.error(err);
    return reply.code(500).send({
      error: 'execution_failed',
      detail: err instanceof Error ? err.message : String(err),
    });
  } finally {
    await api.disconnect();
  }
});

app.post('/monitor', async (req, reply) => {
  const { txHash } = req.body as { txHash?: string };
  if (!txHash || typeof txHash !== 'string') {
    return reply.code(400).send({ error: 'txHash is required' });
  }

  const provider = new WsProvider(CREDITCOIN_WS);
  const api = await ApiPromise.create({ provider });
  try {
    const finalHead = await api.rpc.chain.getFinalizedHead();
    const finalBlock = await api.rpc.chain.getBlock(finalHead);
    const finalNum = finalBlock.block.header.number.toNumber();

    const startNum = Math.max(1, finalNum - MONITOR_SCAN_BLOCKS);
    for (let n = startNum; n <= finalNum; n++) {
      const blockHash = await api.rpc.chain.getBlockHash(n);
      const blk = await api.rpc.chain.getBlock(blockHash);
      const extrinsics = blk.block.extrinsics;
      for (let i = 0; i < extrinsics.length; i++) {
        if (extrinsics[i].hash.toHex() !== txHash) continue;

        // Determine dispatch success/failure from system events in that block.
        const events = await api.query.system.events.at(blockHash);
        const eventRecords = events as unknown as Array<{
          phase: { isApplyExtrinsic: boolean; asApplyExtrinsic: { toNumber(): number } };
          event: { section: string; method: string; data: { toHuman(): unknown } };
        }>;
        let success: boolean | null = null;
        let failure: string | null = null;
        for (const ev of eventRecords) {
          const phase = ev.phase;
          const phaseIdx = phase.isApplyExtrinsic
            ? phase.asApplyExtrinsic.toNumber()
            : -1;
          if (phaseIdx !== i) continue;
          if (
            ev.event.section === 'system' &&
            ev.event.method === 'ExtrinsicSuccess'
          ) {
            success = true;
          } else if (
            ev.event.section === 'system' &&
            ev.event.method === 'ExtrinsicFailed'
          ) {
            success = false;
            const data = ev.event.data.toHuman() as
              | {
                  dispatchError?: {
                    module?: { error?: string; index?: string };
                  };
                }
              | undefined;
            failure =
              data && data.dispatchError
                ? JSON.stringify(data.dispatchError)
                : 'extrinsic_failed';
          }
        }
        return {
          found: true,
          block: n,
          blockHash: blockHash.toHex(),
          extrinsicIndex: i,
          success,
          failure,
        };
      }
    }
    return { found: false, scannedBlockRange: [startNum, finalNum] };
  } catch (err) {
    app.log.error(err);
    return reply.code(500).send({
      error: 'monitor_failed',
      detail: err instanceof Error ? err.message : String(err),
    });
  } finally {
    await api.disconnect();
  }
});

const PORT = Number(process.env.PORT ?? 8081);
const HOST = process.env.HOST ?? '0.0.0.0';

app.listen({ port: PORT, host: HOST }, (err) => {
  if (err) {
    app.log.error(err);
    process.exit(1);
  }
});