import datetime
import json
from decimal import Decimal

from marketdata_clients.PolygonStocksClient import PolygonStocksClient
from marketdata_clients.MarketDataClient import MarketDataException

class Stocks:
    def __init__(self, date=None):
        self.instance = PolygonStocksClient()
        self.date = date if date else self.get_previous_market_open_day(date)
        self.stocks_data = {}
        for _ in range(6):
            response = self.instance.client.get_grouped_daily_bars(self.date)
            if 'results' in response and response['results']:
                self.populate_daily_bars(response['results'])
                break
            else:
                self.date = self.get_previous_market_open_day(self.date)
        else:
            raise MarketDataException(f"No results found for the past 7 days up to date {self.date}")

    def get_previous_market_open_day(self, date=None):
        date = date if date else datetime.datetime.now()
        while True:
            date -= datetime.timedelta(days=1)
            if date.weekday() < 5:  # Monday to Friday are considered market open days
                return date

    def populate_daily_bars(self, grouped_daily_bars):
        for bar in grouped_daily_bars:
            ticker = bar['T']
            date = datetime.datetime.fromtimestamp(bar['t'] / 1000).strftime('%Y-%m-%d')
            daily_bar = {
                "date": date,
                "open": Decimal(bar['o']),
                "high": Decimal(bar['h']),
                "low": Decimal(bar['l']),
                "close": Decimal(bar['c']),
                "volume": Decimal(bar['v'])
            }
            if ticker not in self.stocks_data:
                self.stocks_data[ticker] = {}
            self.stocks_data[ticker] = daily_bar

    def get_daily_bars(self, ticker):
        return self.stocks_data.get(ticker, {})

    def to_dict(self):
        return {
            "date": self.date,
            "stocks_data": self.stocks_data
        }

    def to_json(self):
        return json.dumps(self.to_dict(), default=str)
