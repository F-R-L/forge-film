import json
import os


class AssetCache:
    def __init__(self, cache_dir: str = "./output/assets"):
        self.cache_dir = cache_dir
        self._index_path = os.path.join(cache_dir, "index.json")
        self._index: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if os.path.exists(self._index_path):
            with open(self._index_path) as f:
                return json.load(f)
        return {}

    def _save(self) -> None:
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(self._index_path, "w") as f:
            json.dump(self._index, f, indent=2)

    def get(self, asset_id: str) -> str | None:
        path = self._index.get(asset_id)
        if path and os.path.exists(path):
            return path
        return None

    def put(self, asset_id: str, image_path: str) -> None:
        self._index[asset_id] = image_path
        self._save()

    def exists(self, asset_id: str) -> bool:
        return self.get(asset_id) is not None
