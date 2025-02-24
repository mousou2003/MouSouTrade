import asyncio
import polygon
import logging
from marketdata_clients.PolygonClient import PolygonClient
from marketdata_clients.MarketDataClient import *

logger = logging.getLogger(__name__)

class PolygonOptionsClient(PolygonClient):
    client = None
    DEFAULT_THROTTLE_LIMIT = 0

    def __new__(cls, throttle_limit=DEFAULT_THROTTLE_LIMIT):
        if PolygonOptionsClient.instance is None:
            logger.debug("Creating PolygonOptionsClient Singleton")
            PolygonClient.instance = super(PolygonOptionsClient, cls).__new__(cls)
            try:
                PolygonOptionsClient.instance.THROTTLE_LIMIT = throttle_limit
                PolygonOptionsClient.instance.client = polygon.OptionsClient(PolygonOptionsClient.instance._my_key)
            except Exception as e:
                logger.error(f"Failed to create PolygonOptionsClient: {e}")
                raise
        return PolygonOptionsClient.instance

    def get_grouped_option_daily_bars(self, date):
        self.wait_for_no_throttle()
        try:
            response = self.client.get_grouped_daily_bars(date)
            if 'results' not in response or not response['results']:
                raise KeyError()
            return response['results']
        except KeyError as err:
            raise MarketDataStrikeNotFoundException(f"No results found for date {date}")
        except Exception as err:
            raise MarketDataException(f"Failed to get grouped option daily bars for {date}", err)

    def get_option_previous_close(self, ticker):
        self.wait_for_no_throttle()
        try:
            response = self.client.get_previous_close(ticker)
            if 'results' not in response or not response['results']:
                raise KeyError()
            return response['results'][0]['c']
        except KeyError as err:
            raise MarketDataStrikeNotFoundException(f"No results found for ticker {ticker}")
        except Exception as err:
            raise MarketDataException(f"Failed to get previous close price for Option {ticker}", err)

    async def async_get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self.wait_for_no_throttle()
        try:
            contracts = polygon.ReferenceClient(self._my_key).get_option_contracts(
                underlying_ticker=underlying_ticker,
                expiration_date_lte=expiration_date_lte,
                expiration_date_gte=expiration_date_gte,
                contract_type=contract_type,
                order=order,
                sort='strike_price',
                all_pages=True
            )
            #if 'results' not in contracts or not contracts['results']:
            if len(contracts) == 0:
                logger.warning(f"No option contracts found for {underlying_ticker}")
                return []
            return contracts
        except KeyError as err:
            logger.warning(f"No option contracts found for {underlying_ticker}: {err}")
            return []
        except Exception as err:
            raise MarketDataException(f"Failed to asynchronously get option contracts for {underlying_ticker}", err)

    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self.wait_for_no_throttle()
        try:
            return asyncio.run(self.async_get_option_contracts(underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order))
        except Exception as err:
            raise MarketDataException(f"Failed to get option contracts for {underlying_ticker}", err)
        
    def get_snapshot(
        self,
        underlying_symbol: str,
        option_symbol: str = None):

        all_pages: bool = False
        max_pages: int = None
        merge_all_pages: bool = True
        verbose: bool = False
        raw_page_responses: bool = False
        raw_response: bool = False
        self.wait_for_no_throttle()
        try:
            
            response = self.client.get_snapshot(
                underlying_symbol=underlying_symbol,
                option_symbol=option_symbol,
                all_pages=all_pages,
                max_pages=max_pages,
                merge_all_pages=merge_all_pages,
                verbose=verbose,
                raw_page_responses=raw_page_responses,
                raw_response=raw_response,
            )
            if 'results' not in response or not response['results']:
                raise KeyError()
            return response['results']
        except Exception as err:
            raise MarketDataException(f"Failed to get snapshot for {option_symbol}", err)
