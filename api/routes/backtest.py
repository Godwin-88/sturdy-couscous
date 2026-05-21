import os
import subprocess
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
import redis
import json

router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    start_date:  str = "2021-01-01"
    end_date:    str = "2023-12-31"
    initial_capital: float = 10000.0
    use_graph:   bool = True       # ablation: True=KG-grounded, False=ungrounded


def _redis():
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        decode_responses=True,
    )


@router.post("/run")
def run_backtest(req: BacktestRequest, background_tasks: BackgroundTasks):
    r = _redis()
    r.set("graphalpha:backtest_status", "running")
    r.set("graphalpha:backtest_params", req.model_dump_json())

    background_tasks.add_task(_run_backtest_task, req)
    return {"status": "started", "params": req.model_dump()}


def _run_backtest_task(req: BacktestRequest):
    r = _redis()
    try:
        result = subprocess.run(
            [
                "python", "engine.py",
                "--start",   req.start_date,
                "--end",     req.end_date,
                "--capital", str(req.initial_capital),
                "--use-graph" if req.use_graph else "--no-graph",
            ],
            capture_output=True, text=True, timeout=600,
            cwd="/app/backtest",
        )
        if result.returncode == 0:
            r.set("graphalpha:backtest_result", result.stdout)
            r.set("graphalpha:backtest_status", "done")
        else:
            r.set("graphalpha:backtest_status", f"error:{result.stderr[:200]}")
    except Exception as e:
        r.set("graphalpha:backtest_status", f"error:{e}")


@router.get("/status")
def backtest_status():
    r = _redis()
    return {
        "status": r.get("graphalpha:backtest_status") or "idle",
        "result": json.loads(r.get("graphalpha:backtest_result") or "null"),
    }
