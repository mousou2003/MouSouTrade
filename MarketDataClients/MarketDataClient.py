import logging
import json

class MarketDataClient(object):
    
    instance = None
    client_name = None

    def __new__(cls):
        if MarketDataClient.instance == None :
            logging.info("Creating MarketDataClient Singleton")
            MarketDataClient.instance = super(MarketDataClient, cls).__new__(cls)
            logging.info("MarketDataClient Singleton created")
        return MarketDataClient.instance
    
    def __init__(self, client_name) -> None:
        logging.info("Init MarketDataClient")

    def release():
        MarketDataClient.instance = None

    def get_previous_stock_close(self,ticker):
        pass

    def get_option_previous_close(self, ticker):
        pass

    async def async_get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte,  contract_type, order):
        pass

    def get_option_contracts(self,underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        pass

    def convert_option_symbol_formats(self, ticker):
        pass

    def load_key_secret(jsonfile, stage, client_name):
        MarketDataClient.client_name = client_name
        with open(jsonfile) as file:
            clients = json.load(file)
            logging.info("loaded json")        
            MarketDataClient._my_key= clients["Clients"][MarketDataClient.client_name][stage]["Key"]
            MarketDataClient._my_secret = clients["Clients"][MarketDataClient.client_name][stage]["Secret"]

class MarketDataException(Exception):
    __innerException = None
    def __init__(self, message, source):
        super().__init__(message,source)

class MarketDataStrikeNotFoundException(Exception):
    __innerException = None
    def __init__(self, message, source):
        super().__init__(message,source)
