"""Pre-charge le cache FootyStats tot le matin."""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("preload")

from footystats import get_todays_matches, CACHE_FILE

async def main():
    matches = await get_todays_matches()
    logger.info("Pre-loaded %d matches into cache", len(matches))
    if CACHE_FILE.exists():
        data = json.load(open(CACHE_FILE))
        logger.info("Cache file: %d matches saved", len(data.get("matches_by_id", {})))

asyncio.run(main())
