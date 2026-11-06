import logging
from datetime import datetime
from config import RUNTIME_DIR


def create_logger():
    folder = RUNTIME_DIR / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("run_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".log")
    logger = logging.getLogger(str(path))
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger, path
