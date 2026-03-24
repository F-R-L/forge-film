from forge.compiler.schema import Asset, Scene
from forge.generation.base import BasePipeline


class PipelineRouter:
    def __init__(
        self,
        light: BasePipeline,
        heavy: BasePipeline,
        medium: BasePipeline | None = None,
    ):
        self.light = light
        self.heavy = heavy
        self.medium = medium

    def route(self, scene: Scene) -> BasePipeline:
        if scene.complexity <= 3:
            return self.light
        elif scene.complexity <= 6:
            return self.medium if self.medium is not None else self.light
        else:
            return self.heavy

    async def generate(
        self,
        scene: Scene,
        assets: dict[str, Asset],
        output_dir: str,
        prev_frame: str | None = None,
    ) -> str:
        pipeline = self.route(scene)
        return await pipeline.generate(scene, assets, output_dir, prev_frame=prev_frame)
