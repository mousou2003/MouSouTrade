import logging
from datetime import datetime, timedelta
import time

from marketdata_clients.BaseMarketDataClient import BaseMarketDataClient, IMarketDataClient, MarketDataException, MarketDataStrikeNotFoundException
from marketdata_clients.PolygonClient import *
from marketdata_clients.ETradeClient import *  # Added correct import
from engine.data_model import Contract, Snapshot  # Added Snapshot import
from config import ConfigLoader  # type: ignore # Added ConfigLoader import

logger = logging.getLogger(__name__)

class MarketDataClient(BaseMarketDataClient):

    client: IMarketDataClient = None
    etrade_client = None
    polygon_client = None

    def __init__(self, config_file: str, stage: str = "Sandbox", client_name: str = None):
        super().__init__()
        logger.debug("create MarketDataClient")

        if client_name is None:
            raise MarketDataException("Client name is required")
        else:
            _name = client_name
        if POLYGON_CLIENT_NAME in _name:
            self.polygon_client = PolygonClient(config_file=config_file, stage=stage)
            self.client = self.polygon_client
        if ETRADE_CLIENT_NAME in _name:
            self.etrade_client = ETradeClient(config_file=config_file, stage=stage)
            self.client = self.etrade_client
        if ETRADE_CLIENT_NAME in _name and POLYGON_CLIENT_NAME in _name:
            self.client = None
            
    def get_previous_close(self, ticker):
        try:
            client = self.client
            if  client is None:
                client = self.etrade_client
            return self._exponential_backoff(client.get_previous_close, ticker)
        except Exception as err:
            raise MarketDataException(f"Failed to get previous close for {ticker}", err)

    def get_grouped_daily_bars(self, date):
        try:
            client = self.client
            if client is None:
                client = self.polygon_client
            return self._exponential_backoff(client.get_grouped_daily_bars, date=date)
        except Exception as err:
            raise MarketDataException(f"Failed to get grouped daily bars for {date}", err)
    
    def get_snapshot(self, symbol):
        try:
            client = self.client
            if client is None:
                client = self.etrade_client  
            return self._exponential_backoff(client.get_snapshot, symbol)
        except Exception as err:
            raise MarketDataException(f"Failed to get snapshot for {symbol}", err)

    def get_option_previous_close(self, ticker):
        try:
            client = self.client
            if client is None:
                client = self.etrade_client  
            return self._exponential_backoff(client.get_option_previous_close, ticker)
        except Exception as err:
            raise MarketDataException(f"Failed to get option previous close for {ticker}", err)

    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        try:
            client = self.client
            if client is None:
                client = self.polygon_client.options_client  
            contracts = self._exponential_backoff(client.get_option_contracts,
                underlying_ticker=underlying_ticker,
                expiration_date_gte=expiration_date_gte,
                expiration_date_lte=expiration_date_lte,
                contract_type=contract_type,
                order=order
            )
            return [Contract.from_dict(contract) for contract in contracts]
        except Exception as err:
            raise MarketDataException(f"Failed to get option contracts for {underlying_ticker}", err)

    def get_option_snapshot(self, underlying_ticker, option_symbol=None) -> Snapshot:
        try:
            client = self.client
            if client is None:
                client = self.etrade_client  

            snapshot= self._exponential_backoff(client.get_option_snapshot,
                underlying_ticker=underlying_ticker,
                option_symbol=option_symbol
            )
            return Snapshot.from_dict(snapshot)
        except Exception as err:
            raise MarketDataException(f"Failed to get option snapshot for {underlying_ticker}", err)

    def get_previous_market_open_day(self, date=None):
        date = date if date else datetime.now().date()
        try:
            while True:
                date -= timedelta(days=1)
                if date.weekday() < 5:  # Monday to Friday are considered market open days
                    return date
        except Exception as err:
            raise MarketDataException(f"Failed to get previous market open day", err)
        
    def _exponential_backoff(self, func, *args, retries=3, **kwargs):
        for attempt in range(retries):
            try:
                return func(*args, **kwargs)
            except Exception as err:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise err