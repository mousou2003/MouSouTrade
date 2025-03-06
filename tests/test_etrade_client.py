from decimal import Decimal
import unittest
from unittest.mock import patch, MagicMock

from colorama import Fore, Style
from marketdata_clients.ETradeClient import ETradeClient
from config.ConfigLoader import ConfigLoader
import os
import logging

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

class TestETradeClient(unittest.TestCase):

    @patch('marketdata_clients.ETradeClient.OAuth1Service')
    def setUp(self, MockOAuth1Service):
        self.mock_oauth_service = MockOAuth1Service.return_value
        self.mock_session = MagicMock()
        self.mock_oauth_service.get_request_token.return_value = ('request_token', 'request_token_secret')
        self.mock_oauth_service.get_auth_session.return_value = self.mock_session

        required_env_vars = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_DEFAULT_REGION', 'MOUSOUTRADE_CONFIG_FILE', 'MOUSOUTRADE_STAGE']
        env_vars = {var: os.getenv(var) for var in required_env_vars}
        missing_env_vars = [var for var, value in env_vars.items() if not value]
        if missing_env_vars:
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_env_vars)}")

        config_loader = ConfigLoader('./config/SecurityKeys.json')
        self.client = ETradeClient(config_loader.config, env_vars['MOUSOUTRADE_STAGE'])

    def load_response(self, filename):
        with open(os.path.join(os.path.dirname(__file__), 'data', filename), 'r') as file:
            return file.read()

    def test_get_previous_close(self):
        self.mock_session.get.return_value.text = self.load_response('sampleEtradeResponse.xml')
        previous_close = self.client.get_previous_close('NKE')
        self.assertEqual(previous_close, Decimal('77.81'))

    def test_get_snapshot(self):
        self.mock_session.get.return_value.text = self.load_response('sampleEtradeResponse.xml')
        snapshot = self.client.get_snapshot('NKE')
        self.assertEqual(snapshot['symbol'], 'NKE')
        self.assertEqual(snapshot['lastTrade'], Decimal('77.81'))

    def test_get_grouped_daily_bars(self):
        self.mock_session.get.return_value.text = self.load_response('sampleEtradeResponse.xml')
        daily_bars = self.client.get_grouped_daily_bars('2025-03-06')
        self.assertIn('NKE', daily_bars)
        self.assertEqual(daily_bars['NKE']['close'], Decimal('77.81'))

    def test_get_option_snapshot(self):
        self.mock_session.get.return_value.text = self.load_response('sampleEtradeOptionResponse.xml')
        option_snapshot = self.client.get_option_snapshot('O:NKE250307P00078000')
        self.assertEqual(option_snapshot['symbol'], 'NKE')
        self.assertEqual(option_snapshot['lastTrade'], Decimal('0.99'))

if __name__ == '__main__':
    unittest.main()
