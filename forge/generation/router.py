"""Multi-model semantic router.

Routes each scene to the appropriate video backend based on scene_type
(dialogue / action / landscape / product / transition) rather than a
numeric complexity score.

Routing table is driven by forge.yaml [routing] section via ForgeConfig.
"""
from __future__ import annotations

from forge.compiler.schema import Asset, Scene, SceneType
from forge.generation.base import BasePipeline


class PipelineRouter:
    """Routes scenes to video backends by scene_type.

    Parameters
    ----------
    backends:
        Mapping of backend name -> BasePipeline instance.
        Expected keys: mock, kling_light, kling_heavy, cogvideo, seedance, wan
        (at minimum: mock must always be present as ultimate fallback).
    routing:
        Mapping of scene_type value -> backend name.
        Sourced from ForgeConfig.routing.
    """

    def __init__(
        self,
        backends: dict[str, BasePipeline],
        routing: dict[str, str] | None = None,
    ):
        self.backends = backends
        self.routing = routing or {
            "dialogue": "kling_light",
            "action": "kling_heavy",
            "landscape": "cogvideo",
            "product": "kling_heavy",
            "transition": "cogvideo",
            "default": "mock",
        }

    def route(self, scene: Scene) -> BasePipeline:
        """Select the backend pipeline for a scene."""
        scene_type_val = scene.scene_type.value if hasattr(scene.scene_type, "value") else str(scene.scene_type)
        backend_name = self.routing.get(scene_type_val, self.routing.get("default", "mock"))
        pipeline = self.backends.get(backend_name)
        if pipeline is None:
            # Graceful fallback chain: kling_light -> mock
            for fallback in ("kling_light", "mock"):
                pipeline = self.backends.get(fallback)
                if pipeline is not None:
                    break
        if pipeline is None:
            raise RuntimeError(
                f"No backend available for scene {scene.id!r} "
                f"(type={scene_type_val}, requested={backend_name}). "
                f"Available backends: {list(self.backends)}"
            )
        return pipeline

    async def generate(
        self,
        scene: Scene,
        assets: dict[str, Asset],
        output_dir: str,
        prev_frame: str | None = None,
    ) -> str:
        pipeline = self.route(scene)
        return await pipeline.generate(scene, assets, output_dir, prev_frame=prev_frame)

    def describe_routing(self) -> str:
        """Human-readable summary of current routing table."""
        lines = []
        for scene_type in SceneType:
            backend = self.routing.get(scene_type.value, self.routing.get("default", "mock"))
            available = "OK" if backend in self.backends else "MISSING (will fallback)"
            lines.append(f"  {scene_type.value:<12} -> {backend:<14} [{available}]")
        return "\n".join(lines)
