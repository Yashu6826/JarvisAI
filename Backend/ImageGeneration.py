import asyncio
from random import randint
from PIL import Image
import requests
from dotenv import load_dotenv
import os
from dotenv import dotenv_values
from time import sleep
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
env_vars = dotenv_values(".env")
HUGGINGFACE_API_KEY = env_vars.get("HUGGING_FACE_KEY")

API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}

os.makedirs("Data", exist_ok=True)

def open_image(prompt):
    folder_path = "./Data"
    prompt = prompt.replace(" ", "_")
    files = [f"{prompt}{i}.jpg" for i in range(1, 5)]
    for jpg_file in files:
        image_path = os.path.join(folder_path, jpg_file)
        try:
            img = Image.open(image_path)
            logger.info(f"Opening image: {image_path}")
            img.show()
            sleep(1)
        except IOError as e:
            logger.error(f"Unable to open {image_path}: {e}")

async def query(payload):
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(requests.post, API_URL, headers=headers, json=payload),
            timeout=30.0
        )
        if response.status_code != 200:
            logger.error(f"API error: {response.status_code} - {response.text}")
            return None
        return response.content
    except asyncio.TimeoutError:
        logger.error("API request timed out")
        return None
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return None

async def generate_images(prompt: str):
    logger.info(f"Generating images for prompt: {prompt}")
    image_bytes_list = []
    for i in range(4):
        payload = {
            "inputs": f"{prompt}, quality=4K, sharpness=maximum, Ultra High Details, high resolution, seed={randint(0,1000000)}",
        }
        logger.info(f"Sending API request {i+1}")
        image_bytes = await query(payload)
        if image_bytes:
            image_bytes_list.append(image_bytes)
        else:
            logger.error(f"Failed to generate image {i+1}")
        await asyncio.sleep(1)

    logger.info(f"Saving {len(image_bytes_list)} images")
    for i, image_bytes in enumerate(image_bytes_list):
        file_path = f"Data/{prompt.replace(' ','_')}{i+1}.jpg"
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        logger.info(f"Saved image: {file_path}")

def GenerateImages(prompt: str):
    asyncio.run(generate_images(prompt))
    open_image(prompt)

while True:
    try:
        file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Frontend", "Files", "ImageGeneration.data"))
        logger.info(f"Checking file: {file_path}")

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        if not os.path.exists(file_path):
            logger.warning(f"File not found, creating: {file_path}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("default prompt,False")

        with open(file_path, "r", encoding="utf-8") as f:
            data = f.read().strip()
            logger.info(f"File content: '{data}'")

        if not data:
            logger.error(f"File is empty, resetting: {file_path}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("default prompt,False")
            sleep(1)
            continue

        try:
            prompt, status = data.split(",")
            prompt = prompt.strip()
            status = status.strip()
        except ValueError:
            logger.error(f"Invalid data format in {file_path}, content: '{data}', resetting")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("default prompt,False")
            sleep(1)
            continue

        if not prompt:
            logger.error(f"Empty prompt in {file_path}, resetting")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("default prompt,False")
            sleep(1)
            continue

        if status == "True":
            logger.info("Generating images...")
            GenerateImages(prompt=prompt)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("default prompt,False")
            break
        else:
            sleep(1)

    except FileNotFoundError:
        logger.error(f"File not found: {file_path}, retrying...")
        sleep(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sleep(1)