from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterator, List
from polygon import rest as polygon_rest
import polygon
import logging
import asyncio

import polygon.rest
from marketdata_clients.BaseMarketDataClient import BaseMarketDataClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

POLYGON_CLIENT_NAME: str = "polygon"

class PolygonClient(BaseMarketDataClient):
    DEFAULT_THROTTLE_LIMIT = 12
    OPTION_THROTTLE_LIMIT = 0
    stocks_data = {}

    def __init__(self, config_file: str, stage: str, throttle_limit=DEFAULT_THROTTLE_LIMIT):
        super().__init__(config_file=config_file, client_name=POLYGON_CLIENT_NAME, stage=stage)
        self.THROTTLE_LIMIT = throttle_limit
        self.client = polygon_rest.RESTClient(api_key=self._my_key)
        self.options_client = self.client
        logger.debug("PolygonClient created")

    def get_previous_close(self, ticker):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        response = self.client.get_previous_close_agg(ticker, adjusted="true")
        logger.debug(f"get_previous_close response: {response}")
        return [{'ticker': agg.ticker, 'close': agg.close, 'high': agg.high, 
                'low': agg.low, 'open': agg.open, 'volume': agg.volume, 
                'vwap': agg.vwap, 'timestamp': agg.timestamp} 
                for agg in response]

    def get_grouped_daily_bars(self, date=None):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        if date is None:
            date = self.get_previous_market_open_day()
        response = self.client.get_grouped_daily_aggs(date=date)
        logger.debug(f"get_grouped_daily_bars response: {response}")
        result = {}
        for bar in response:
            result[bar.ticker] = {
                'ticker': bar.ticker,
                'close': bar.close,
                'high': bar.high,
                'low': bar.low,
                'open': bar.open,
                'volume': bar.volume,
                'vwap': bar.vwap,
                'timestamp': bar.timestamp
            }
        return result

    def get_snapshot(self, symbol):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        response = self.client.get_snapshot_ticker(ticker=symbol)
        logger.debug(f"get_snapshot response: {response}")
        return response['results']

    def get_option_previous_close(self, ticker):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        response = self.options_client.get_previous_close_agg(ticker=ticker, adjusted="true")
        logger.debug(f"get_option_previous_close response: {response}")
        return [{'ticker': agg.ticker, 'close': agg.close, 'high': agg.high, 
                'low': agg.low, 'open': agg.open, 'volume': agg.volume, 
                'vwap': agg.vwap, 'timestamp': agg.timestamp} 
                for agg in response]

    def get_option_contracts(self, underlying_ticker, expiration_date_gte=None, expiration_date_lte=None, contract_type=None, order=None):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        response: Iterator[polygon.reference.OptionsContract] = self.options_client.list_options_contracts( underlying_ticker=underlying_ticker,
                expiration_date_gte=expiration_date_gte,
                expiration_date_lte=expiration_date_lte,
                contract_type=contract_type,
                order=order,
                limit=20,
                sort="expiration_date"
            )
        contracts = []
        for c in response:
            contracts.append({
                'ticker': c.ticker,
                'expiration_date': c.expiration_date,
                'strike_price': c.strike_price,
                'contract_type': c.contract_type
            })
        logger.debug(f"get_option_contracts response: {contracts}")
        return contracts

    def get_option_snapshot(self,  underlying_asset:str, option_symbol: str):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        response: polygon.snapshot.OptionContractSnapshot = self.options_client.get_snapshot_option(underlying_asset=underlying_asset, option_contract=option_symbol)
        return {
            'details': {
                'ticker': response.details.ticker,
                'strike_price': response.details.strike_price,
                'expiration_date': response.details.expiration_date
            },
            'day': {
                'high': response.day.high,
                'low': response.day.low,
                'close': response.day.close,
                'volume': response.day.volume
            }
        }
        
    def _populate_daily_bars(self, grouped_daily_bars: list[polygon_rest.aggs.GroupedDailyAgg]):
        for bar in grouped_daily_bars:
            if bar.ticker not in self.stocks_data:
                self.stocks_data[bar.ticker] = {}
            self.stocks_data[bar.ticker] = bar