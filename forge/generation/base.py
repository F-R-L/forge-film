from abc import ABC, abstractmethod

from forge.compiler.schema import Asset, Scene


class BasePipeline(ABC):
    @abstractmethod
    async def generate(
        self,
        scene: Scene,
        assets: dict[str, Asset],
        output_dir: str,
        prev_frame: str | None = None,  # last frame of predecessor scene (i2v input)
    ) -> str:  # returns path to generated video file
        ...
