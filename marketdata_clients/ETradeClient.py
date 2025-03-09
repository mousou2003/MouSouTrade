from datetime import datetime, timedelta
from decimal import Decimal
import logging
import asyncio
from xml.dom.minidom import Element
from rauth import OAuth1Service
from marketdata_clients.BaseMarketDataClient import BaseMarketDataClient
import re
import xml.etree.ElementTree as ET
import os
import time
import threading

logger = logging.getLogger(__name__)

ETRADE_CLIENT_NAME: str = "etrade"

class ETradeClient(BaseMarketDataClient):
    DEFAULT_THROTTLE_LIMIT = 0
    OPTION_THROTTLE_LIMIT = 0
    WAIT_TIME = 20
    stocks_data = {}

    def __init__(self, config_file: str, stage: str, throttle_limit=DEFAULT_THROTTLE_LIMIT):
        super().__init__(client_name = ETRADE_CLIENT_NAME, config_file = config_file, stage= stage)
        self.THROTTLE_LIMIT = throttle_limit
        # Initialize ETrade API client here
        self.etrade = OAuth1Service(
            name="etrade",
            consumer_key=self._my_key,
            consumer_secret=self._my_secret,
            request_token_url="https://api.etrade.com/oauth/request_token",
            access_token_url="https://api.etrade.com/oauth/access_token",
            authorize_url="https://us.etrade.com/e/t/etws/authorize?key={}&token={}",
            base_url=self._BaseUrl
        )
        request_token, request_token_secret = self.etrade.get_request_token(
            params={"oauth_callback": "oob", "format": "json"}
        )
        authorize_url = self.etrade.authorize_url.format(self.etrade.consumer_key, request_token)
        self.authorization_url = authorize_url
        
        # Start a separate thread to wait for the verification code
        print(f"Please go to the following URL and authorize the application: {authorize_url}")
        self.verification_code = None
        verification_thread = threading.Thread(target=self._wait_for_verification_code)
        verification_thread.start()
        verification_thread.join()
        
        self.session = self.etrade.get_auth_session(
            request_token,
            request_token_secret,
            params={"oauth_verifier": self.verification_code}
        )
        logger.debug("ETradeClient created")

    def _wait_for_verification_code(self):
        try:
            self.verification_code = input("Please enter the verification code: ")
        except Exception as e:
            logger.warning(f"Failed to read input: {e}")
        while not self.verification_code or len(self.verification_code) < 5:
            self.reload_config()
            self.verification_code = self._mycode
            time.sleep(self.WAIT_TIME)

    def get_previous_close(self, ticker):
        return self.get_snapshot(ticker)["close"]

    def get_grouped_daily_bars(self, date):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        url = f"{self.etrade.base_url}/v1/market/quote/{date}"
        response = self.session.get(url)
        if not response.text.strip():
            logger.error("Empty or whitespace-only response for grouped daily bars")
            raise ValueError("Empty or whitespace-only response")
        root = ET.fromstring(response.text)
        if root is None or not root.findall('.//QuoteData'):
            logger.error("Empty or invalid XML response for grouped daily bars")
            raise ValueError("Empty or invalid XML response")
        self._populate_daily_bars(root.findall('.//QuoteData'))
        return self.stocks_data

    def get_snapshot(self, symbol):
        self._wait_for_no_throttle(self.DEFAULT_THROTTLE_LIMIT)
        url = f"{self.etrade.BaseUrl}/v1/market/quote/{symbol}"
        response = self.session.get(url)
        if not response.text.strip():
            logger.error("Empty or whitespace-only response for snapshot")
            raise ValueError("Empty or whitespace-only response")
        root = ET.fromstring(response.text)
        if root is None or root.find('.//QuoteData') is None or not root.find('.//QuoteData').text.strip():
            logger.error("Empty or invalid XML response for snapshot")
            raise ValueError("Empty or invalid XML response")
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
        if not response.text.strip():
            logger.error("Empty or whitespace-only response for option snapshot")
            raise ValueError("Empty or whitespace-only response")
        root: Element = ET.fromstring(response.text)
        if root is None or root.find('.//QuoteData') is None :
            logger.error("Empty or invalid XML response for option snapshot")
            raise ValueError("Empty or invalid XML response")
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

    def _parse_option_snapshot(self, quote_data: Element):
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
