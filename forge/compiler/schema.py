from dataclasses import dataclass
from enum import Enum
from pydantic import BaseModel, Field


class AssetType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    PROP = "prop"


class SceneType(str, Enum):
    DIALOGUE = "dialogue"      # 人物对话、特写
    ACTION = "action"          # 动作、追逐、复杂运动
    LANDSCAPE = "landscape"    # 风景、空镜、建立镜头
    PRODUCT = "product"        # 产品展示、需要物体一致性
    TRANSITION = "transition"  # 过渡、蒙太奇


class Asset(BaseModel):
    id: str
    type: AssetType
    description: str
    reference_image_path: str | None = None  # filled after generation


class Scene(BaseModel):
    id: str
    description: str
    complexity: int = Field(ge=1, le=10)
    scene_type: SceneType = SceneType.DIALOGUE  # semantic type for model routing
    estimated_duration_sec: float = Field(default=30.0)
    dependencies: list[str] = Field(default_factory=list)
    assets_required: list[str] = Field(default_factory=list)
    output_video_path: str | None = None  # filled after generation
    last_frame_path: str | None = None    # extracted after generation, used as i2v input for dependents
    status: str = "pending"  # pending | generating | done | failed


class ProductionPlan(BaseModel):
    title: str
    scenes: list[Scene]
    assets: list[Asset]
    dag: dict[str, list[str]]  # scene_id -> [downstream_scene_ids]


class ValidationResult(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    retry_count: int = 0


@dataclass
class GenerationResult:
    video_path: str
    last_frame_path: str            # pre-extracted last frame path
    resolution: tuple[int, int]     # actual output resolution (width, height)
    fps: int                        # actual output fps
    backend_used: str               # which backend generated this (kling/cogvideo/mock/...)
    duration_sec: float             # actual video duration
