from decimal import Decimal
import unittest
from unittest.mock import MagicMock

from colorama import Fore, Style
from marketdata_clients.PolygonClient import PolygonClient
from config.ConfigLoader import ConfigLoader
import os
import logging
import json

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
debug_mode = os.getenv("DEBUG_MODE")
if debug_mode and debug_mode.lower() == "true":
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

    def __init__(self, methodName = "runTest"):
        super().__init__(methodName)

        if self.client is None:
            self.mock_session = MagicMock()

            required_env_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION', 'MOUSOUTRADE_CONFIG_FILE', 'MOUSOUTRADE_STAGE']
            env_vars = {var: os.getenv(var) for var in required_env_vars}
            missing_env_vars = [var for var, value in env_vars.items() if not value]
            if missing_env_vars:
                raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_env_vars)}")

            config_loader = ConfigLoader('./config/SecurityKeys.json')

            self.client = PolygonClient(config_loader.config, env_vars['MOUSOUTRADE_STAGE'])

    def setUp(self):
        pass

    def load_response(self, filename):
        with open(os.path.join(os.path.dirname(__file__), 'data', filename), 'r') as file:
            return file.read()

    @unittest.skip("Not implemented")
    def test_get_previous_close(self):
        self.mock_session.get.return_value.json.return_value = json.loads(self.load_response('samplePolygonPreviousClose.json'))
        previous_close = self.client.get_previous_close('AAPL')
        self.assertAlmostEqual(previous_close, Decimal('235.74'), places=2)

    def test_get_grouped_daily_bars(self):
        self.mock_session.get.return_value.json.return_value = json.loads(self.load_response('samplePolygonGroupedDailyBars.json'))
        previous_market_open_day = self.client.get_previous_market_open_day()
        daily_bars = self.client.get_grouped_daily_bars(previous_market_open_day)
        self.assertIn('FENY', daily_bars)
        self.assertAlmostEqual(daily_bars['FENY']['close'], Decimal('23.46'), places=2)

    @unittest.skip("Not implemented")
    def test_get_option_previous_close(self):
        pass

    @unittest.skip("Not implemented in the client")
    def test_get_option_contracts(self):
        pass

    @unittest.skip("Not paying for that data")
    def test_get_snapshot(self):
        pass

    def test_get_option_snapshot(self):
        self.mock_session.get.return_value.json.return_value = json.loads(self.load_response('samplePolygonOptionResponse.json'))
        option_snapshot = self.client.get_option_snapshot(underlying_symbol='AAPL', option_symbol='O:AAPL250307P00150000')
        self.assertEqual(option_snapshot['details']['ticker'], 'O:AAPL250307P00150000')
        self.assertAlmostEqual(Decimal(option_snapshot['day']['close']), Decimal('0.01'), places=2)

if __name__ == '__main__':
    unittest.main()
