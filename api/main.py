
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
    # Log top-level request summary (avoid huge dumps)
    try:
        logger.info("PIPELINE start: units=%s origin=%s ops=%d out=%s",
                    getattr(req, "units", None), getattr(req, "origin", None),
                    len(req.operations or []), getattr(req, "output_mode", None))
    except Exception:
        pass

    # --- Build stock ---
    try:
        work = build_stock(req.stock)
        logger.info("STOCK built: type=%s params=%s", req.stock.type, req.stock.params)
    except Exception as ex:
        logger.exception("build_stock failed")
        raise HTTPException(status_code=400, detail={
            "phase": "stock",
            "message": str(ex),
        }) from ex

    steps: list[StepResult] = []
    step_no = 0

    # --- Apply operations ---
    for op in req.operations:
        step_no += 1
        name = op.name or op.op.replace(":", "_")
        logger.info("STEP %02d START op=%s name=%s selector=%s params=%s",
                    step_no, op.op, name, op.selector, op.params)

        try:
            after, removed = apply_op(work, op)
            logger.info("STEP %02d OK op=%s", step_no, op.op)
        except OpError as ex:
            logger.exception("STEP %02d FAILED (OpError) op=%s", step_no, op.op)
            raise HTTPException(status_code=400, detail={
                "phase": "op",
                "step": step_no,
                "op": op.op,
                "selector": op.selector,
                "params": op.params,
                "message": str(ex),
            }) from ex
        except Exception as ex:
            logger.exception("STEP %02d FAILED (Unexpected) op=%s", step_no, op.op)
            raise HTTPException(status_code=500, detail={
                "phase": "op",
                "step": step_no,
                "op": op.op,
                "selector": op.selector,
                "params": op.params,
                "message": str(ex),
            }) from ex

        solid_path = None
        removed_path = None

        # --- Export (optional) ---
        if req.output_mode == "stl" and not req.dry_run:
            try:
                solid_name = req.file_template_solid.format(step=step_no, name=name)
                removed_name = req.file_template_removed.format(step=step_no, name=name)
                solid_path = OUTDIR / solid_name
                removed_path = OUTDIR / removed_name

                _export_stl(after, solid_path)
                if removed is not None:
                    _export_stl(removed, removed_path)

                logger.info("STEP %02d EXPORTED: solid=%s removed=%s",
                            step_no, solid_path, removed_path)
            except Exception as ex:
                logger.exception("STEP %02d EXPORT failed", step_no)
                raise HTTPException(status_code=400, detail={
                    "phase": "export",
                    "step": step_no,
                    "op": op.op,
                    "message": str(ex),
                }) from ex

        steps.append(StepResult(
            step=step_no,
            name=name,
            solid=str(solid_path).replace("\\","/") if solid_path else None,
            removed=str(removed_path).replace("\\","/") if removed_path else None
        ))

        # Next step
        work = after

    # Optional show mode (best-effort)
    if req.output_mode == "show" and not req.dry_run:
        try:
            from cadquery import show_object
            show_object(work)
        except Exception:
            logger.info("show_object skipped (headless or unavailable)")

    logger.info("PIPELINE done: steps=%d", len(steps))
    return PipelineResponse(status="ok", steps=steps)
