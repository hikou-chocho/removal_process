
from __future__ import annotations
import os
from pathlib import Path
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import cadquery as cq
from .models import PipelineRequest, PipelineResponse, StepResult
from .cad_ops import build_stock, apply_op, OpError

# -----------------------------
# Logging setup
# -----------------------------
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"

# basicConfig affects root logger; keep it idempotent
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8")
        ],
    )

logger = logging.getLogger("pipeline")

app = FastAPI(title="Removal Process API", version="0.1.0")

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "data" / "output"
OUTDIR.mkdir(parents=True, exist_ok=True)

def _export_stl(solid: cq.Workplane, path: Path):
    from cadquery import exporters
    path.parent.mkdir(parents=True, exist_ok=True)
    exporters.export(solid, str(path))

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f">>> {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        logger.info(f"<<< {request.method} {request.url.path} {response.status_code}")
        return response
    except Exception as ex:
        logger.exception(f"Unhandled exception during {request.method} {request.url.path}")
        raise

@app.post("/pipeline/run", response_model=PipelineResponse)
def run_pipeline(req: PipelineRequest):
    # Top-level summary
    logger.info(
        ">>> POST /pipeline/run units=%s origin=%s ops=%d out=%s",
        req.units,
        req.origin,
        len(req.operations),
        req.output_mode,
    )

    # --- Stock build ---
    try:
        work = build_stock(req.stock)
    except OpError as e:
        logger.exception("STOCK build input error")
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "message": str(e),
            "step": 0,
            "op": "stock",
        })
    except Exception as e:
        logger.exception("STOCK build internal error")
        raise HTTPException(status_code=500, detail={
            "status": "error",
            "message": f"stock build internal error: {e}",
            "step": 0,
            "op": "stock",
        })

    before = work
    steps_result: list[StepResult] = []

    # export dir
    output_dir = OUTDIR

    do_export = req.output_mode == "stl" and not req.dry_run

    for idx, op in enumerate(req.operations, start=1):
        logger.info(
            "STEP %02d START op=%s name=%s selector=%s params=%s",
            idx,
            op.op,
            op.name,
            op.selector,
            op.params,
        )

        try:
            after, removed = apply_op(before, op)
        except OpError as e:
            logger.exception("STEP %02d input error", idx)
            raise HTTPException(status_code=400, detail={
                "status": "error",
                "message": str(e),
                "step": idx,
                "op": op.op,
                "name": op.name,
            })
        except Exception as e:
            logger.exception("STEP %02d internal error", idx)
            raise HTTPException(status_code=500, detail={
                "status": "error",
                "message": f"internal error: {e}",
                "step": idx,
                "op": op.op,
                "name": op.name,
            })

        logger.info("STEP %02d OK op=%s", idx, op.op)

        solid_path = None
        removed_path = None

        if do_export:
            solid_name = req.file_template_solid.format(
                step=idx, name=op.name or op.op.replace(":", "_")
            )
            removed_name = req.file_template_removed.format(
                step=idx, name=op.name or op.op.replace(":", "_")
            )

            solid_path = output_dir / solid_name
            removed_path = output_dir / removed_name

            cq.exporters.export(after, str(solid_path))
            if removed is not None:
                cq.exporters.export(removed, str(removed_path))

            logger.info(
                "STEP %02d EXPORTED: solid=%s removed=%s",
                idx,
                solid_path,
                removed_path,
            )

        steps_result.append(
            StepResult(
                step=idx,
                name=op.name or op.op,
                solid=str(solid_path).replace("\\", "/") if solid_path else None,
                removed=str(removed_path).replace("\\", "/") if removed_path else None,
            )
        )

        before = after

    return PipelineResponse(status="ok", steps=steps_result)
