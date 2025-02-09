import polygon
from polygon import ReferenceClient
import time
import logging
import asyncio
from marketdata_clients.MarketDataClient import MarketDataStrikeNotFoundException, MarketDataException, MarketDataClient

logger = logging.getLogger(__name__)

class PolygonClient(MarketDataClient):
    CLIENT_NAME = "polygon"
    instance = None
       
    def __new__(cls):
        logger.info("create PolygonClient")        
        instance = super(PolygonClient, cls).__new__(cls, PolygonClient.CLIENT_NAME)
        return instance