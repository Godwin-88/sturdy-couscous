import os, subprocess, json, sys
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
import redis

router = APIRouter(prefix="/backtest", tags=["backtest"])

# Path to the backtest engine — works both inside Docker (/app/backtest) and on host
BACKTEST_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "backtest")
BACKTEST_DIR = os.path.abspath(BACKTEST_DIR)
PYTHON = sys.executable


class BacktestRequest(BaseModel):
    start_date:      str   = "2021-01-01"
    end_date:        str   = "2023-12-31"
    initial_capital: float = 10000.0
    use_graph:       bool  = True
    rebal_freq:      int   = 5
    fee_pct:         float = 0.0010
    slip_pct:        float = 0.0005
    run_both:        bool  = False
    tickers:         str   = "SPY,QQQ,TLT,GLD,BTC-USD"
    trade_threshold: float = 0.05
    benchmark:       str   = "SPY"     # NEW
    rf_rate:         float = 0.05      # NEW



class ApprovalRequest(BaseModel):
    suggestion_id: str
    action: str   # "approve" | "reject"
    notes: str = ""


def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


def _run_engine(req: BacktestRequest, use_graph: bool, r) -> dict | None:
    label = "grounded" if use_graph else "ungrounded"
    r.set("graphalpha:backtest_status", f"running:{label}")
    r.set("graphalpha:backtest_progress", json.dumps({"pct": 0, "msg": f"Starting {label} run…"}))
    
    try:
        # Clear cancel flag at start
        r.set("graphalpha:backtest_cancel", "0")
        result = subprocess.run(
            [PYTHON, "engine.py",
             "--start",        req.start_date,
             "--end",          req.end_date,
             "--capital",      str(req.initial_capital),
             "--rebal-freq",   str(req.rebal_freq),
             "--fee-pct",      str(req.fee_pct),
             "--slip-pct",     str(req.slip_pct),
             "--tickers",      req.tickers,
             "--trade-threshold", str(req.trade_threshold),
             "--benchmark", req.benchmark,
             "--rf-rate", str(req.rf_rate),
             "--use-graph" if use_graph else "--no-graph"],
            capture_output=True, text=True, timeout=900,
            cwd=BACKTEST_DIR,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            r.set("graphalpha:backtest_status", f"error:{result.stderr[:300]}")
            return None
    except Exception as e:
        r.set("graphalpha:backtest_status", f"error:{e}")
        return None


def _run_backtest_task(req: BacktestRequest):
    r = _redis()
    results = {}

    grounded = _run_engine(req, use_graph=True, r=r)
    if grounded:
        results["grounded"] = grounded
        r.set("graphalpha:backtest_result_grounded", json.dumps(grounded))

    if req.run_both:
        ungrounded = _run_engine(req, use_graph=False, r=r)
        if ungrounded:
            results["ungrounded"] = ungrounded
            r.set("graphalpha:backtest_result_ungrounded", json.dumps(ungrounded))

    r.set("graphalpha:backtest_status", "done")
    r.set("graphalpha:backtest_progress", json.dumps({"pct": 100, "msg": "Complete"}))


@router.post("/run")
def run_backtest(req: BacktestRequest, background_tasks: BackgroundTasks):
    r = _redis()
    r.set("graphalpha:backtest_status", "starting")
    r.delete("graphalpha:backtest_result_grounded")
    r.delete("graphalpha:backtest_result_ungrounded")
    background_tasks.add_task(_run_backtest_task, req)
    return {"status": "started"}


@router.get("/status")
def backtest_status():
    r = _redis()
    status   = r.get("graphalpha:backtest_status") or "idle"
    progress = json.loads(r.get("graphalpha:backtest_progress") or '{"pct":0,"msg":""}')
    grounded   = json.loads(r.get("graphalpha:backtest_result_grounded")   or "null")
    ungrounded = json.loads(r.get("graphalpha:backtest_result_ungrounded") or "null")

    # Back-compat: also expose as single `result` for old callers
    result = grounded or ungrounded
    return {
        "status":     status,
        "progress":   progress,
        "result":     result,
        "grounded":   grounded,
        "ungrounded": ungrounded,
    }


@router.get("/suggestions")
def get_suggestions():
    r = _redis()
    raw = r.get("graphalpha:trade_suggestions")
    return json.loads(raw) if raw else []


@router.post("/suggestions/action")
def action_suggestion(req: ApprovalRequest):
    r = _redis()
    raw = r.get("graphalpha:trade_suggestions")
    suggestions = json.loads(raw) if raw else []

    updated = []
    acted   = None
    for s in suggestions:
        if s["id"] == req.suggestion_id:
            s["status"] = req.action   # "approve" | "reject"
            s["notes"]  = req.notes
            acted = s
        updated.append(s)

    r.set("graphalpha:trade_suggestions", json.dumps(updated))

    # If approved, push to the agent's pending orders queue
    if req.action == "approve" and acted:
        queue_raw = r.get("graphalpha:approved_suggestions") or "[]"
        queue     = json.loads(queue_raw)
        queue.append(acted)
        r.set("graphalpha:approved_suggestions", json.dumps(queue))
        # Publish event so the agent loop picks it up
        r.publish("graphalpha:events", json.dumps({
            "event":    "suggestion_approved",
            "strategy": acted["strategy"],
            "ticker":   acted["ticker"],
            "regime":   acted["regime"],
        }))

    return {"ok": True, "suggestion": acted}

@router.post("/cancel")
def cancel_backtest():
    r = _redis()
    r.set("graphalpha:backtest_cancel", "1")
    r.set("graphalpha:backtest_status", "error:Cancelled by user")
    return {"ok": True}