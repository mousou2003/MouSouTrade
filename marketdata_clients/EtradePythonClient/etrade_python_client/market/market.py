import json
import logging
import xml.etree.ElementTree as ET
from logging.handlers import RotatingFileHandler

# logger settings
logger = logging.getLogger('my_logger')

class Market:
    def __init__(self, session, base_url):
        self.session = session
        self.base_url = base_url

    def quotes(self):
        """
        Calls quotes API to provide quote details for equities, options, and mutual funds

        :param self: Passes authenticated session in parameter
        """
        symbols = input("\nOne or more (comma-separated) symbols for equities or options, up to a maximum of 25. Symbols for equities are simple, for example, GOOG. Symbols for options are more complex, consisting of six elements separated by colons, in this format: underlier:year:month:day:optionType:strikePrice. Please enter Stock Symbol: ")

        # URL for the API endpoint
        url = self.base_url + "/v1/market/quote/" + symbols

        # Make API call for GET request
        response = self.session.get(url)
        logger.debug("Request Header: %s", response.request.headers)

        if response is not None and response.status_code == 200:

            logger.debug("Response Body: %s", response.text)

            # Parse XML response
            root = ET.fromstring(response.text)

            # Handle and parse response
            for quote_data in root.findall('QuoteData'):
                dateTime = quote_data.find('dateTime').text if quote_data.find('dateTime') is not None else "N/A"
                logger.info("Date Time: " + dateTime)
                
                product = quote_data.find('Product')
                if product is not None:
                    symbol = product.find('symbol').text if product.find('symbol') is not None else "N/A"
                    securityType = product.find('securityType').text if product.find('securityType') is not None else "N/A"
                    logger.info("Symbol: " + symbol)
                    logger.info("Security Type: " + securityType)
                
                all_data = quote_data.find('All')
                if all_data is not None:
                    for elem in all_data:
                        logger.info(f"{elem.tag}: {elem.text}")

                    # Query next Friday option at strike price ATM
                    from datetime import datetime, timedelta

                    today = datetime.today()
                    next_friday = today + timedelta((4 - today.weekday()) % 7)
                    strike_price = round(float(all_data.find('lastTrade').text if all_data.find('lastTrade') is not None else 0))
                    option_symbol = f"{symbol}:{next_friday.year}:{next_friday.month}:{next_friday.day}:C:{strike_price}"

                    option_url = self.base_url + "/v1/market/quote/" + option_symbol
                    logger.debug(option_url)
                    option_response = self.session.get(option_url)
                    logger.debug("Option Request Header: %s", option_response.request.headers)

                    if option_response is not None and option_response.status_code == 200:
                        logger.debug("Option Response Body: %s", option_response.text) 
                        option_root = ET.fromstring(option_response.text)
                        option_data = option_root.find('QuoteData')
                        if option_data is not None:
                            option_all_data = option_data.find('All')
                            if option_all_data is not None:
                                for elem in option_all_data:
                                    logger.info(f"{elem.tag}: {elem.text}")
                    else:
                        logger.error("Error: Option API service error")

        else:
            logger.debug("Response Body: %s", response)
            logger.error("Error: Quote API service error")

    def option_chain(self, symbol):
        """
        Calls option chains API to provide option chain details for a given symbol.

        :param symbol: The ticker symbol for which to retrieve the option chain
        """
        # URL for the API endpoint
        url = self.base_url + f"/v1/market/optionchains/{symbol}"
        logger.debug(url)
        # Make API call for GET request
        response = self.session.get(url)
        logger.debug("Request Header: %s", response.request.headers)

        if response is not None and response.status_code == 200:
            logger.debug("Response Body: %s", response.text)

            # Parse XML response
            root = ET.fromstring(response.text)

            # Handle and parse response
            for option_pair in root.findall('OptionPair'):
                call_option = option_pair.find('Call')
                put_option = option_pair.find('Put')

                if call_option is not None:
                    logger.info("Call Option:")
                    logger.info(f"  Symbol: {call_option.find('symbol').text}")
                    logger.info(f"  Strike Price: {call_option.find('strikePrice').text}")
                    logger.info(f"  Expiration Date: {call_option.find('expirationDate').text}")
                    logger.info(f"  Bid: {call_option.find('bid').text}")
                    logger.info(f"  Ask: {call_option.find('ask').text}")

                if put_option is not None:
                    logger.info("Put Option:")
                    logger.info(f"  Symbol: {put_option.find('symbol').text}")
                    logger.info(f"  Strike Price: {put_option.find('strikePrice').text}")
                    logger.info(f"  Expiration Date: {put_option.find('expirationDate').text}")
                    logger.info(f"  Bid: {put_option.find('bid').text}")
                    logger.info(f"  Ask: {put_option.find('ask').text}")

            # Handle errors
            if root.find('Messages') is not None:
                for error_message in root.find('Messages').findall('Message'):
                    logger.error("Error: " + error_message.find('description').text)
        else:
            logger.debug("Response Body: %s", response)
            logger.error("Error: Option Chain API service error")
