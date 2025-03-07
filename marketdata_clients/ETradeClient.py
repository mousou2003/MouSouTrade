from datetime import datetime, timedelta
from decimal import Decimal
import logging
import asyncio
from rauth import OAuth1Service
from marketdata_clients.BaseMarketDataClient import BaseMarketDataClient
import re
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

ETRADE_CLIENT_NAME: str = "etrade"

class ETradeClient(BaseMarketDataClient):
    DEFAULT_THROTTLE_LIMIT = 0
    OPTION_THROTTLE_LIMIT = 0
    stocks_data = {}

    def __init__(self, json_content: dict, stage: str, throttle_limit=DEFAULT_THROTTLE_LIMIT):
        self.client_name = ETRADE_CLIENT_NAME
        self._load_key_secret(json_content, stage)
        self.THROTTLE_LIMIT = throttle_limit
        # Initialize ETrade API client here
        base_url = json_content["Clients"][self.client_name][stage]["BaseUrl"]
        self.etrade = OAuth1Service(
            name="etrade",
            consumer_key=self._my_key,
            consumer_secret=self._my_secret,
            request_token_url="https://api.etrade.com/oauth/request_token",
            access_token_url="https://api.etrade.com/oauth/access_token",
            authorize_url="https://us.etrade.com/e/t/etws/authorize?key={}&token={}",
            base_url=base_url
        )
        request_token, request_token_secret = self.etrade.get_request_token(
            params={"oauth_callback": "oob", "format": "json"}
        )
        authorize_url = self.etrade.authorize_url.format(self.etrade.consumer_key, request_token)
        print(f"Please go to the following URL and authorize the application: {authorize_url}")
        text_code = input("Please enter the verification code: ")
        self.session = self.etrade.get_auth_session(
            request_token,
            request_token_secret,
            params={"oauth_verifier": text_code}
        )
        logger.debug("ETradeClient created")

    def get_previous_close(self, ticker):
        return self.get_snapshot(ticker)["close"]

    def get_grouped_daily_bars(self, date):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        url = f"{self.etrade.base_url}/v1/market/quote/{date}"
        response = self.session.get(url)
        root = ET.fromstring(response.text)
        self._populate_daily_bars(root.findall('.//QuoteData'))
        return self.stocks_data

    def get_snapshot(self, symbol):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        url = f"{self.etrade.base_url}/v1/market/quote/{symbol}"
        response = self.session.get(url)
        root = ET.fromstring(response.text)
        return self._parse_snapshot(root.find('.//QuoteData'))

    def get_option_contracts(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        return None

    def get_option_snapshot(self, option_symbol: str, underlying_symbol:str=None):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        match = re.match(r'O:(\w+)(\d{2})(\d{2})(\d{2})(C|P)(\d+)', option_symbol)
        if not match:
            raise ValueError("Invalid option symbol format")
        underlying_symbol, year, month, day, option_type, strike_price = match.groups()
        strike_price = f"{int(strike_price) / 1000:.0f}"
        option_symbol = f"{underlying_symbol}:20{year}:{month}:{day}:{option_type}:{strike_price}"
        option_url = f"{self.etrade.base_url}/v1/market/quote/{option_symbol}"
        response = self.session.get(option_url)
        root = ET.fromstring(response.text)
        return self._parse_option_snapshot(root.find('.//QuoteData'))

    def get_option_previous_close(self, option_symbol: str):
        self._wait_for_no_throttle(self.OPTION_THROTTLE_LIMIT)
        option_url = f"{self.etrade.base_url}/v1/market/quote/{option_symbol}"
        response = self.session.get(option_url)
        root = ET.fromstring(response.text)
        return Decimal(root.find('.//previousClose').text)

    def _populate_daily_bars(self, grouped_daily_bars):
        for bar in grouped_daily_bars:
            ticker = bar.find('.//symbol').text
            date = datetime.fromtimestamp(int(bar.find('.//dateTimeUTC').text)).date()
            daily_bar = {
                "date": date,
                "open": Decimal(bar.find('.//open').text),
                "high": Decimal(bar.find('.//high').text),
                "low": Decimal(bar.find('.//low').text),
                "close": Decimal(bar.find('.//lastTrade').text),
                "volume": Decimal(bar.find('.//totalVolume').text)
            }
            if ticker not in self.stocks_data:
                self.stocks_data[ticker] = {}
            self.stocks_data[ticker] = daily_bar

    def _parse_snapshot(self, quote_data):
        snapshot = {
            "symbol": quote_data.find('.//symbol').text,
            "lastTrade": Decimal(quote_data.find('.//lastTrade').text),
            "open": Decimal(quote_data.find('.//open').text),
            "high": Decimal(quote_data.find('.//high').text),
            "low": Decimal(quote_data.find('.//low').text),
            "close": Decimal(quote_data.find('.//previousClose').text),
            "volume": Decimal(quote_data.find('.//totalVolume').text),
            "timestamp": datetime.fromtimestamp(int(quote_data.find('.//dateTimeUTC').text))
        }
        return snapshot

    def _parse_option_snapshot(self, quote_data):
        option_snapshot = {
            "symbol": quote_data.find('.//symbol').text,
            "lastTrade": Decimal(quote_data.find('.//lastTrade').text),
            "open": Decimal(quote_data.find('.//open').text),
            "high": Decimal(quote_data.find('.//high').text),
            "low": Decimal(quote_data.find('.//low').text),
            "close": Decimal(quote_data.find('.//previousClose').text),
            "volume": Decimal(quote_data.find('.//totalVolume').text),
            "timestamp": datetime.fromtimestamp(int(quote_data.find('.//dateTimeUTC').text)),
            "ask": Decimal(quote_data.find('.//ask').text),
            "bid": Decimal(quote_data.find('.//bid').text),
            "askSize": int(quote_data.find('.//askSize').text),
            "bidSize": int(quote_data.find('.//bidSize').text),
            "optionStyle": quote_data.find('.//optionStyle').text,
            "optionUnderlier": quote_data.find('.//optionUnderlier').text,
            "optionMultiplier": Decimal(quote_data.find('.//optionMultiplier').text),
            "expirationDate": datetime.fromtimestamp(int(quote_data.find('.//expirationDate').text)).date(),
            "quoteStatus": quote_data.find('.//quoteStatus').text,
            "ahFlag": quote_data.find('.//ahFlag').text == 'true',
            "changeClose": Decimal(quote_data.find('.//changeClose').text),
            "changeClosePercentage": Decimal(quote_data.find('.//changeClosePercentage').text),
            "companyName": quote_data.find('.//companyName').text,
            "daysToExpiration": int(quote_data.find('.//daysToExpiration').text),
            "high52": Decimal(quote_data.find('.//high52').text),
            "low52": Decimal(quote_data.find('.//low52').text),
            "openInterest": int(quote_data.find('.//openInterest').text),
            "symbolDescription": quote_data.find('.//symbolDescription').text,
            "intrinsicValue": Decimal(quote_data.find('.//intrinsicValue').text),
            "timePremium": Decimal(quote_data.find('.//timePremium').text),
            "contractSize": Decimal(quote_data.find('.//contractSize').text),
            "optionPreviousBidPrice": Decimal(quote_data.find('.//optionPreviousBidPrice').text),
            "optionPreviousAskPrice": Decimal(quote_data.find('.//optionPreviousAskPrice').text),
            "osiKey": quote_data.find('.//osiKey').text,
            "timeOfLastTrade": datetime.fromtimestamp(int(quote_data.find('.//timeOfLastTrade').text)),
            "averageVolume": int(quote_data.find('.//averageVolume').text)
        }
        return option_snapshot

    def _parse_option_contracts(self, option_pairs):
        contracts = []
        for option_pair in option_pairs:
            call_option = option_pair.find('.//Call')
            put_option = option_pair.find('.//Put')
            if call_option is not None:
                contracts.append(self._parse_option(call_option))
            if put_option is not None:
                contracts.append(self._parse_option(put_option))
        return contracts

    def _parse_option(self, option):
        return {
            "symbol": option.find('.//symbol').text,
            "strikePrice": Decimal(option.find('.//strikePrice').text),
            "expirationDate": datetime.strptime(option.find('.//expirationDate').text, '%Y-%m-%d').date(),
            "bid": Decimal(option.find('.//bid').text),
            "ask": Decimal(option.find('.//ask').text)
        }
