import logging
import json
logger = logging.getLogger(__name__)

class Database(object):
    def __init__(self) -> None:
        logger.info("Init Database")    