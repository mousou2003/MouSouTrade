import datetime
import json

from marketdata_clients.PolygonStocksClient import PolygonStocksClient
from marketdata_clients.MarketDataClient import MarketDataException

class Stocks:
    def __init__(self, date=None):
        self.date = date if date else self.get_previous_market_open_day()
        self.stocks_data = {}
        self.instance = PolygonStocksClient()
        response = self.instance.client.get_grouped_daily_bars(self.date)
        if 'results' in response and response['results']:
            self.populate_daily_bars(response['results'])
        else:
            raise MarketDataException(f"No results found for date {self.date}")

    def get_previous_market_open_day(self):
        today = datetime.datetime.now()
        while True:
            today -= datetime.timedelta(days=1)
            if today.weekday() < 5:  # Monday to Friday are considered market open days
                return today.strftime('%Y-%m-%d')

    def populate_daily_bars(self, grouped_daily_bars):
        for bar in grouped_daily_bars:
            ticker = bar['T']
            date = datetime.datetime.fromtimestamp(bar['t'] / 1000).strftime('%Y-%m-%d')
            daily_bar = {
                "date": date,
                "open": bar['o'],
                "high": bar['h'],
                "low": bar['l'],
                "close": bar['c'],
                "volume": bar['v']
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
