from pydantic_settings import BaseSettings


class ForgeSettings(BaseSettings):
    openai_api_key: str = ""
    kling_api_key: str = ""
    kling_api_secret: str = ""
    forge_workers: int = 4
    forge_video_backend: str = "mock"
    output_dir: str = "./output"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = ForgeSettings()
