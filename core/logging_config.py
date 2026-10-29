import sys
from loguru import logger

logger.remove()


logger.add(sys.stdout,level="INFO",format="{time:YYYY-MM-DD HH:mm:ss} | {level}| {message}")



logger.add(
    "logs/app.log",
    level="INFO",
    rotation="10 MB",
    retention=5,
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)