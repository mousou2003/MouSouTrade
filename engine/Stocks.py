import datetime
import json

from marketdata_clients.BaseMarketDataClient import MarketDataException

class Stocks:
    def __init__(self, market_data_client, date: datetime.date = None):
        self.market_data_client = market_data_client
        self.date = date if date else self.market_data_client.get_previous_market_open_day(date)
        self.stocks_data = {}
        # explore the past 7 days to find the latest data (latest day market was open)
        for _ in range(6):
            self.stocks_data = self.market_data_client.get_grouped_daily_bars(self.date)
            if self.stocks_data != {}:
               return
            else:
                self.date = self.market_data_client.get_previous_market_open_day(self.date)
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
