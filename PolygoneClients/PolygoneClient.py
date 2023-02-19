import polygon
from polygon import ReferenceClient
import time
import logging
import asyncio
from MarketDataClients.MarketDataClient import MarketDataStrikeNotFoundException, MarketDataException, MarketDataClient

class PolygoneClient(MarketDataClient):
    THROTTLE_LIMIT = 60/5  # we are currently limited to 5 requests per minutes
    CLIENT_NAME = "polygone"
    options_client = None
    stocks_client = None

    def __new__(cls):
        if PolygoneClient.instance == None:
            logging.info("Creating PolygoneClient Singleton")
            PolygoneClient.instance = super(PolygoneClient, cls).__new__(cls)
            PolygoneClient.create_polygone_clients()
            logging.info("PolygoneClient Singleton created")
        return PolygoneClient.instance

    def __init__(self) -> None:
        if PolygoneClient.instance == None:
            logging.info("Init PolygoneClient")
            super().__init__()
            logging.info("Clients successfully created")

    def create_polygone_clients():
        PolygoneClient.load_key_secret(
            jsonfile="./config/SecurityKeys.json", stage="Sandbox", client_name=PolygoneClient.CLIENT_NAME)
        PolygoneClient.options_client = polygon.OptionsClient(PolygoneClient._my_key)
        PolygoneClient.stocks_client = polygon.StocksClient(PolygoneClient._my_key)

    def get_previous_stock_close(self, ticker):
        self.wait_for_no_Throttle()
        try:
            return self.stocks_client.get_previous_close(ticker)['results'][0]['c']
        except Exception as err:
            raise MarketDataException(
                "Failed to get previous close price for stock %s may not be accessible." % ticker, err)

    def get_option_previous_close(self, ticker):
        self.wait_for_no_Throttle()
        try:
            response = self.options_client.get_previous_close(ticker)
            logging.debug(response)
            return response['results'][0]['c']
        except KeyError as err:
            raise MarketDataStrikeNotFoundException(
                "Failed to get previous close price for Option %s, this strike may not be accessible." % ticker, err)

    async def async_get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte,  contract_type, order):
        self.wait_for_no_Throttle()
        contracts = polygon.ReferenceClient(PolygoneClient._my_key).get_option_contracts(underlying_ticker=underlying_ticker,
                                                                             expiration_date_lte=expiration_date_lte, expiration_date_gte=expiration_date_gte, contract_type=contract_type,
                                                                             order=order, sort='strike_price')
        return contracts['results']

    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self.wait_for_no_Throttle()
        return asyncio.run(self.async_get_option_contracts(underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order))

    def convert_option_symbol_formats(self, ticker):
        return polygon.convert_option_symbol_formats(ticker, from_format=PolygoneClient.CLIENT_NAME, to_format='tos')

    def wait_for_no_Throttle(self):
        time.sleep(self.THROTTLE_LIMIT)
