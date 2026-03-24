import asyncio
from collections.abc import Callable, Awaitable

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from forge.compiler.schema import Asset
from forge.assets.cache import AssetCache


class AssetFoundry:
    def __init__(self, image_gen_fn: Callable[[str], Awaitable[str]], cache: AssetCache):
        self.image_gen_fn = image_gen_fn
        self.cache = cache

    async def build(self, assets: list[Asset]) -> dict[str, Asset]:
        result: dict[str, Asset] = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            task = progress.add_task("Building assets…", total=len(assets))

            async def process(asset: Asset) -> None:
                cached = self.cache.get(asset.id)
                if cached:
                    asset.reference_image_path = cached
                else:
                    path = await self.image_gen_fn(asset.description)
                    asset.reference_image_path = path
                    self.cache.put(asset.id, path)
                result[asset.id] = asset
                progress.advance(task)

            await asyncio.gather(*[process(a) for a in assets])

        return result
