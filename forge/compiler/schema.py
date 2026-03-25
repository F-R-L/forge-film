from enum import Enum
from pydantic import BaseModel, Field


class AssetType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    PROP = "prop"


class Asset(BaseModel):
    id: str
    type: AssetType
    description: str
    reference_image_path: str | None = None  # filled after generation


class Scene(BaseModel):
    id: str
    description: str
    complexity: int = Field(ge=1, le=10)
    estimated_duration_sec: float = Field(default=30.0)
    dependencies: list[str] = Field(default_factory=list)
    assets_required: list[str] = Field(default_factory=list)
    output_video_path: str | None = None  # filled after generation
    last_frame_path: str | None = None      # extracted after generation, used as i2v input for dependents
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
