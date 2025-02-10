import logging
import json
import time
logger = logging.getLogger(__name__)

class MarketDataClient(object):
    
    client_name = None

    def __new__(cls, client_name):
        logger.debug("create MarketDataClient")        
        instance = super(MarketDataClient, cls).__new__(cls)
        instance.client_name = client_name
        instance.load_key_secret(jsonfile="./config/SecurityKeys.json", stage="Sandbox")  
        return instance
     
    def load_key_secret(self, jsonfile, stage):
        with open(jsonfile) as file:
            clients = json.load(file)
            logger.debug("loaded json")        
            self._my_key= clients["Clients"][self.client_name][stage]["Key"]
            self._my_secret = clients["Clients"][self.client_name][stage]["Secret"]

    def wait_for_no_throttle(self):
        time.sleep(self.THROTTLE_LIMIT)


class MarketDataException(Exception):
    def __init__(self, message, inner_exception=None):
        super().__init__(message)
        self.inner_exception = inner_exception

class MarketDataStrikeNotFoundException(MarketDataException):
    def __init__(self, message, inner_exception=None):
        super().__init__(message, inner_exception)
        self.inner_exception = inner_exception

class MarketDataStorageFailedException(MarketDataException):
    def __init__(self, message, inner_exception=None):
        super().__init__(message, inner_exception)
        self.inner_exception = inner_exception