from decimal import Decimal
from typing import List
import unittest
from colorama import Fore, Style
from engine import Options
from marketdata_clients.PolygonClient import PolygonClient
from config.ConfigLoader import ConfigLoader
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
debug_mode = os.getenv("DEBUG_MODE")
if (debug_mode and debug_mode.lower() == "true"):
    loglevel = logging.DEBUG
else:
    loglevel = logging.WARNING
logging.basicConfig(level=loglevel)
class ColorFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.WARNING:
            record.msg = f"{Fore.YELLOW}{record.msg}{Style.RESET_ALL}"
        elif record.levelno == logging.ERROR:
            record.msg = f"{Fore.RED}{record.msg}{Style.RESET_ALL}"
        return super().format(record)
handler = logging.StreamHandler()
handler.setFormatter(ColorFormatter())
logger.addHandler(handler)

class TestPolygonClient(unittest.TestCase):
    
    client = None
    expiration_date = None
    expiration_date_lte = None
    expiration_date_gte = None

    def __init__(self, methodName = "runTest"):
        super().__init__(methodName)

        if self.client is None:
            required_env_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION', 'MOUSOUTRADE_CONFIG_FILE', 'MOUSOUTRADE_STAGE']
            env_vars = {var: os.getenv(var) for var in required_env_vars}
            missing_env_vars = [var for var, value in env_vars.items() if not value]
            if missing_env_vars:
                raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_env_vars)}")

            self.client = PolygonClient('./config/SecurityKeys.json', env_vars['MOUSOUTRADE_STAGE'])

    def setUp(self):
        self.expiration_date = Options.Options.get_following_third_friday()
        self.expiration_date_lte = self.expiration_date.strftime('%Y-%m-%d')
        self.expiration_date_gte = (self.expiration_date - timedelta(days=7)).strftime('%Y-%m-%d')

    def test_get_previous_close(self):
        previous_close_data = self.client.get_previous_close('AAPL')
        self.assertIsNotNone(previous_close_data)
        self.assertTrue(len(previous_close_data) > 0)
        
        agg = previous_close_data[0]
        self.assertEqual(agg['ticker'], 'AAPL')
        self.assertIsNotNone(agg['close'])
        self.assertIsNotNone(agg['high'])
        self.assertIsNotNone(agg['low'])
        self.assertIsNotNone(agg['open'])
        self.assertIsNotNone(agg['volume'])
        self.assertIsNotNone(agg['vwap'])
        self.assertIsNotNone(agg['timestamp'])
        
        self.assertGreaterEqual(agg['high'], agg['low'])
        self.assertGreaterEqual(agg['close'], 0)
        self.assertGreaterEqual(agg['volume'], 0)
        self.assertGreaterEqual(agg['vwap'], 0)

    def test_get_grouped_daily_bars(self):
        previous_market_open_day = self.client.get_previous_market_open_day()
        daily_bars = self.client.get_grouped_daily_bars(previous_market_open_day)
        self.assertIsNotNone(daily_bars)
        
        sample_symbols = ['AAPL', 'MSFT', 'GOOGL']
        for symbol in sample_symbols:
            if symbol in daily_bars:
                agg = daily_bars[symbol]
                self.assertEqual(agg['ticker'], symbol)
                self.assertIsNotNone(agg['open'])
                self.assertIsNotNone(agg['high'])
                self.assertIsNotNone(agg['low'])
                self.assertIsNotNone(agg['close'])
                self.assertIsNotNone(agg['volume'])
                self.assertIsNotNone(agg['vwap'])
                self.assertIsNotNone(agg['timestamp'])
                
                self.assertGreater(agg['high'], agg['low'])
                self.assertGreaterEqual(agg['open'], agg['low'])
                self.assertGreaterEqual(agg['close'], agg['low'])
                self.assertLessEqual(agg['open'], agg['high'])
                self.assertLessEqual(agg['close'], agg['high'])
                self.assertGreater(agg['volume'], 0)
                self.assertGreater(agg['vwap'], 0)

    def test_get_option_contracts(self):
        option_contracts = self.client.get_option_contracts(
            'AAPL',
            expiration_date_gte=self.expiration_date_gte,
            expiration_date_lte=self.expiration_date_lte,
            contract_type='put',
            order='asc'
        )
        self.assertIsNotNone(option_contracts)
        self.assertTrue(len(option_contracts) > 0)
        for contract in option_contracts:
            self.assertTrue(contract['ticker'].startswith('O:AAPL'))

    def test_get_option_contracts_call(self):
        option_contracts = self.client.get_option_contracts(
            'AAPL',
            expiration_date_gte=self.expiration_date_gte,
            expiration_date_lte=self.expiration_date_lte,
            contract_type='call',
            order='asc'
        )
        self.assertIsNotNone(option_contracts)
        self.assertTrue(len(option_contracts) > 0)
        for contract in option_contracts:
            self.assertTrue(contract['ticker'].startswith('O:AAPL'))

    def test_get_option_snapshot(self):
        contracts = self.client.get_option_contracts(
            'AAPL',
            expiration_date_gte=self.expiration_date_gte,
            expiration_date_lte=self.expiration_date_lte,
            contract_type='put',
            order='asc'
        )
        self.assertTrue(len(contracts) > 0)
        response = self.client.get_option_snapshot(
            underlying_ticker='AAPL', 
            option_symbol=contracts[0]['ticker']
        )
        self.assertIsNotNone(response)

        # Verify day section
        self.assertIn('day', response)
        day = response['day']
        day_fields = ['change', 'change_percent', 'close', 'high', 'last_updated',
                     'low', 'open', 'previous_close', 'volume', 'vwap']
        for field in day_fields:
            self.assertIn(field, day)
            self.assertIsNotNone(day[field])

        # Verify details section
        self.assertIn('details', response)
        details = response['details']
        detail_fields = ['contract_type', 'exercise_style', 'expiration_date',
                        'shares_per_contract', 'strike_price', 'ticker']
        for field in detail_fields:
            self.assertIn(field, details)
            self.assertIsNotNone(details[field])
        self.assertEqual(details['ticker'], contracts[0]['ticker'])

        # Verify greeks section
        self.assertIn('greeks', response)
        greeks = response['greeks']
        greek_fields = ['delta', 'gamma', 'theta', 'vega']
        for field in greek_fields:
            self.assertIn(field, greeks)
            self.assertIsNotNone(greeks[field])

        # Verify implied volatility
        self.assertIn('implied_volatility', response)
        self.assertIsNotNone(response['implied_volatility'])

        # Verify open interest
        self.assertIn('open_interest', response)
        self.assertIsNotNone(response['open_interest'])

        # Verify underlying asset
        self.assertIn('underlying_asset', response)
        self.assertIn('ticker', response['underlying_asset'])
        self.assertEqual(response['underlying_asset']['ticker'], 'AAPL')

if __name__ == '__main__':
    unittest.main()
