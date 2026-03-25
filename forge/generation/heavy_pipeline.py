import asyncio
import base64
import os

import httpx

from forge.compiler.schema import Asset, Scene
from forge.generation.base import BasePipeline
from forge.generation.kling_auth import build_kling_jwt


class HeavyPipeline(BasePipeline):
    """Kling text-to-video, 10s professional mode. Falls back to MockPipeline if no API key."""

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key or os.environ.get("KLING_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("KLING_API_SECRET", "")

    async def generate(
        self,
        scene: Scene,
        assets: dict[str, Asset],
        output_dir: str,
        prev_frame: str | None = None,
    ) -> str:
        if not self.api_key:
            from forge.generation.mock_pipeline import MockPipeline
            return await MockPipeline().generate(scene, assets, output_dir, prev_frame=prev_frame)

        os.makedirs(os.path.join(output_dir, "scenes"), exist_ok=True)
        out_path = os.path.join(output_dir, "scenes", f"{scene.id}.mp4")

        body: dict = {
            "model": "kling-v1-5",
            "prompt": scene.description,
            "duration": "10",
            "mode": "pro",
        }

        # Add reference image if available
        ref_img = None
        for aid in scene.assets_required:
            asset = assets.get(aid)
            if asset and asset.reference_image_path:
                ref_img = asset.reference_image_path
                break
        # i2v: prev_frame takes priority over reference_image
        if prev_frame and os.path.exists(prev_frame):
            with open(prev_frame, "rb") as f:
                body["image"] = base64.b64encode(f.read()).decode()
        elif ref_img and os.path.exists(ref_img):
            with open(ref_img, "rb") as f:
                body["reference_image"] = base64.b64encode(f.read()).decode()

        token = build_kling_jwt(self.api_key, self.api_secret)
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                "https://api.klingai.com/v1/videos/text2video",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            resp.raise_for_status()
            task_id = resp.json()["data"]["task_id"]
            video_url = await self._poll(client, task_id)

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.get(video_url)
            with open(out_path, "wb") as f:
                f.write(r.content)

        return out_path

    async def _poll(self, client: httpx.AsyncClient, task_id: str) -> str:
        for _ in range(180):
            await asyncio.sleep(5)
            resp = await client.get(
                f"https://api.klingai.com/v1/videos/text2video/{task_id}",
                headers={"Authorization": f"Bearer {build_kling_jwt(self.api_key, self.api_secret)}"},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            if data["task_status"] == "succeed":
                return data["task_result"]["videos"][0]["url"]
            elif data["task_status"] == "failed":
                raise RuntimeError(f"Kling task failed: status={data.get('task_status')}, id={data.get('task_id')}")
        raise TimeoutError("Kling task timed out after 15 minutes")
