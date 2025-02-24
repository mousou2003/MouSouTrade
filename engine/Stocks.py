import datetime
import json
import time
from decimal import Decimal

from marketdata_clients.PolygonStocksClient import PolygonStocksClient
from marketdata_clients.MarketDataClient import MarketDataException

class Stocks:
    def __init__(self, date=None):
        self.instance = PolygonStocksClient()
        self.date = date if date else self.instance.get_previous_market_open_day(date)
        self.stocks_data = {}
        # explore the past 7 days to find the most recent data
        for _ in range(6):
            response = self.get_grouped_daily_bars(self.date)
            if 'results' in response and response['results']:
                self.instance.populate_daily_bars(response['results'])
                break
            else:
                self.date = self.instance.get_previous_market_open_day(self.date)
        else:
            raise MarketDataException(f"No results found for the past 7 days up to date {self.date}")

    def get_daily_bars(self, ticker):
        return self.stocks_data.get(ticker, {})

    def to_dict(self):
        return {
            "date": self.date,
            "stocks_data": self.stocks_data
        }

    def to_json(self):
        return json.dumps(self.to_dict(), default=str)
