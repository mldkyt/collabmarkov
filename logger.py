import logging
import os

if not os.path.exists("logs"):
    os.mkdir("logs")

collabmarkov_logger = logging.getLogger("collabmarkov")
collabmarkov_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

collabmarkov_logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler(
    filename=f"logs/collabmarkov.log", mode="a", encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(collabmarkov_formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(collabmarkov_formatter)

collabmarkov_logger.addHandler(file_handler)
collabmarkov_logger.addHandler(console_handler)
