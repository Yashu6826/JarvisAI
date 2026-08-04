import asyncio
import base64
import logging
from io import BytesIO
from pathlib import Path
from time import sleep

import requests
from dotenv import dotenv_values
from PIL import Image
from Backend.Paths import DATA_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
env_vars = dotenv_values(ENV_PATH)
SD_WEBUI_BASE_URL = env_vars.get("SD_WEBUI_BASE_URL", "http://127.0.0.1:7860").rstrip("/")
SD_IMAGE_WIDTH = int(env_vars.get("SD_IMAGE_WIDTH", "512"))
SD_IMAGE_HEIGHT = int(env_vars.get("SD_IMAGE_HEIGHT", "512"))
SD_STEPS = int(env_vars.get("SD_STEPS", "15"))
SD_CFG_SCALE = float(env_vars.get("SD_CFG_SCALE", "7"))
SD_BATCH_SIZE = int(env_vars.get("SD_BATCH_SIZE", "1"))

def _safe_prompt_name(prompt: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in prompt)[:80]


def open_image(prompt: str, image_count: int) -> None:
    name = _safe_prompt_name(prompt)
    for index in range(1, image_count + 1):
        image_path = DATA_DIR / f"{name}{index}.jpg"
        try:
            Image.open(image_path).show()
            sleep(1)
        except IOError as exc:
            logger.error("Unable to open %s: %s", image_path, exc)


def save_image_bytes(prompt: str, index: int, image_bytes: bytes) -> None:
    output_path = DATA_DIR / f"{_safe_prompt_name(prompt)}{index}.jpg"
    output_path.write_bytes(image_bytes)
    logger.info("Saved image: %s", output_path)


async def generate_with_sd_webui(prompt: str) -> int:
    payload = {
        "prompt": f"{prompt}, high quality, sharp focus, detailed",
        "negative_prompt": "low quality, blurry, distorted, watermark, text",
        "steps": SD_STEPS,
        "cfg_scale": SD_CFG_SCALE,
        "width": SD_IMAGE_WIDTH,
        "height": SD_IMAGE_HEIGHT,
        "batch_size": SD_BATCH_SIZE,
        "n_iter": 1,
        "sampler_name": "DPM++ 2M Karras",
        "seed": -1,
    }
    try:
        response = await asyncio.to_thread(
            requests.post,
            f"{SD_WEBUI_BASE_URL}/sdapi/v1/txt2img",
            json=payload,
            timeout=600,
        )
        response.raise_for_status()
        images = response.json().get("images", [])
        if not images:
            logger.error("Stable Diffusion WebUI returned no images.")
            return 0

        for index, encoded_image in enumerate(images, start=1):
            image_bytes = base64.b64decode(encoded_image.split(",", 1)[-1])
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=95)
            save_image_bytes(prompt, index, output.getvalue())
        return len(images)
    except requests.RequestException as exc:
        logger.error("Local Stable Diffusion is not reachable at %s: %s", SD_WEBUI_BASE_URL, exc)
        return 0
    except Exception as exc:
        logger.error("Local Stable Diffusion generation failed: %s", exc)
        return 0


def GenerateImages(prompt: str) -> None:
    clean_prompt = prompt.removeprefix("generate image ").strip()
    image_count = asyncio.run(generate_with_sd_webui(clean_prompt))
    if image_count:
        open_image(clean_prompt, image_count)


def _read_generation_request(request_path: Path) -> tuple[str, bool]:
    if not request_path.exists():
        return "", False
    data = request_path.read_text(encoding="utf-8").strip()
    try:
        prompt, status = data.rsplit(",", 1)
    except ValueError:
        return "", False
    return prompt.strip(), status.strip().lower() == "true"


if __name__ == "__main__":
    request_path = Path("Frontend/Files/ImageGeneration.data")
    while True:
        prompt, requested = _read_generation_request(request_path)
        if requested and prompt:
            GenerateImages(prompt)
            request_path.write_text("default prompt,False", encoding="utf-8")
            break
        sleep(1)
