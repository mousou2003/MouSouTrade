import datetime
import json
from typing import List
from engine.data_model import Stock
from marketdata_clients.BaseMarketDataClient import MarketDataException

class Stocks:
    def __init__(self, market_data_client, date: datetime.date = None):
        self.market_data_client = market_data_client
        self.date = date if date else self.market_data_client.get_previous_market_open_day(date)
        self.stocks_data: List[Stock] = []

        if not date:
            date = datetime.date.today()
            
        for _ in range(6):
            raw_data = self.market_data_client.get_grouped_daily_bars(self.date)
            if raw_data:
                self.stocks_data = [
                    Stock.from_dict({
                        'ticker': ticker,
                        'date': date,
                        **data
                    })
                    for ticker, data in raw_data.items()
                ]
                return
            else:
                self.date = self.market_data_client.get_previous_market_open_day(self.date)
        else:
            raise MarketDataException(f"No results found for the past 7 days up to date {self.date}")

    def get_daily_bars(self, ticker: str) -> List[Stock]:
        """Return daily bars for a given ticker"""
        return [stock for stock in self.stocks_data if stock.ticker == ticker]

    def to_dict(self):
        return {
            "stocks": [stock.to_dict() for stock in self.stocks_data]
        }

    def to_json(self):
        return json.dumps(self.to_dict(), default=str)
