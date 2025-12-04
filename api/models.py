# api/models.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, List, Union, Any

Num = Union[float, int]

class Operation(BaseModel):
    op: str
    name: Optional[str] = None
    setup: Optional[str] = None
    selector: Optional[str] = None                # CadQuery selector (e.g. ">Z", "<X", "|Y")
    workplane: Optional[Literal["XY", "YZ", "ZX"]] = None
    csys: Optional[Dict[str, List[float]]] = None # 予約（STEP2で回転・平行移動対応）
    params: Dict[str, Any] = Field(default_factory=dict)

class Stock(BaseModel):
    type: Literal["block", "cylinder", "mesh"]
    params: Dict[str, Num | str]

class PipelineRequest(BaseModel):
    units: Literal["mm","inch"] = "mm"
    origin: Literal["world","center","stock_min"] = "world"
    stock: Stock
    setups: List[Dict[str, Any]] = Field(default_factory=list)
    operations: List[Operation]
    output_mode: Literal["stl","step","show","none"] = "stl"
    file_template_solid: str = "case_{step:02d}_{name}_solid.stl"
    file_template_removed: str = "case_{step:02d}_{name}_removed.stl"
    dry_run: bool = False

class StepResult(BaseModel):
    step: int
    name: str
    solid: Optional[str] = None
    removed: Optional[str] = None

class PipelineResponse(BaseModel):
    status: Literal["ok","error"]
    message: Optional[str] = None
    steps: List[StepResult] = Field(default_factory=list)


# ============================================================
# --- Natural Language Models (NL-only request/response) ---
# These types are added for NL frontend integration and do not
# change existing models or APIs that use the core Pipeline types.
# ============================================================


class NLStockRequest(BaseModel):
    """
    Natural-language → Stock extraction
    """
    text: str = Field(..., description="User input describing the raw stock in Japanese or other language.")
    language: Optional[str] = Field("ja", description="Language code. Default: ja")


class NLStockResponse(BaseModel):
    """
    Output of Stock Extractor LLM: { stock: {...} }
    """
    stock: Stock


class NLFeatureRequest(BaseModel):
    """
    Natural-language → Feature extraction
    A single user utterance should describe exactly one feature.
    """
    text: str = Field(..., description="User input describing a single machining feature.")
    language: Optional[str] = Field("ja", description="Language code. Default: ja")


class NLFeatureResponse(BaseModel):
    """
    Output of Feature Extractor LLM: Operation-shaped object
    """
    op: Operation

