from pydantic_settings import BaseSettings


class ForgeConfig(BaseSettings):
    openai_api_key: str = ""
    kling_api_key: str = ""
    kling_api_secret: str = ""
    forge_workers: int = 4
    forge_video_backend: str = "mock"  # mock | kling
    output_dir: str = "./output"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


config = ForgeConfig()
