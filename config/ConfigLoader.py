import json
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class ClientKeys(Enum):
    ETRADE = "etrade"
    POLYGON = "polygon"

class ConfigLoader:
    def __init__(self, json_file: str):
        self.config = self._load_config(json_file)
        self.json_file = json_file
        self._load_config(self.json_file)

    def _load_config(self, json_file: str) -> dict:
        try:
            with open(json_file) as f:
                content = f.read()
                config = json.loads(content)
                logger.debug("Loaded JSON content")
                return config
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON content: {e}")
            raise
        except FileNotFoundError as e:
            logger.error(f"Configuration file not found: {json_file}")
            raise

    def reload_config(self):
        self.config = self._load_config(self.json_file)

    def get_client_keys(self, client_name: str, stage: str) -> dict:
        try:
            client_config = self.config["Clients"][client_name][stage]
            return {
                "Key": client_config["Key"],
                "Secret": client_config["Secret"],
                "code": client_config["code"],
                "BaseUrl": client_config["BaseUrl"]
            }
        except KeyError as e:
            logger.error(f"Key error: {e}")
            raise

# Example usage:
# json_content = '{"Clients": {"etrade": {"Sandbox": {"Key": "1025b5b95145bcedb668a4415d55fa58", "Secret": "e71ccb84cb8dfbd090e7c4c2857b61602621a52a315aa7b3f5299d2c8cdb9312"}, "Prod": {"Key": "9a64fcef0c840ca87fd5290c717270c5", "Secret": "2fe708c86e1cb9f74ead8f0932958b2a7d5cf9a617cef6646a3799463c3f42a5"}}, "polygon": {"Sandbox": {"Key": "pvV7LYD62nDB1cxynOjrlfn5PfwaHQwS", "Secret": ""}, "Prod": {"Key": "", "Secret": ""}}}}'
# config_loader = ConfigLoader(json_content)
# keys = config_loader.get_client_keys(ClientKeys.POLYGON, "Sandbox")
# print(keys)
