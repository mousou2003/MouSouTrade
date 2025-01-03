from MarketDataClients.MarketDataClient import MarketDataException
from engine.Options import CreditSpread, Option
from PolygoneClients.PolygoneClient import PolygoneClient
import engine.data_model as dm

from requests import ReadTimeout
import json
from colorama import Fore
import sys

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

if __name__ == '__main__':
    n = len(sys.argv)
    logger.info("Total arguments passed: %s", n)
    # Arguments passed
    logger.info("\nName of Python script: %s", sys.argv[0])
    logger.info("\nArguments passed: %s", sys.argv)
    logger.info("Target date: %s"%Option.get_followingThirdFriday())

    with open(sys.argv[1]) as file:
        stocks = json.load(file)
        for stock in stocks:
            try:
                direction=dm.BULLISH
                strategy=dm.CREDIT
                creditVerticalSpreadTest = CreditSpread(underlying_ticker=stock['Ticker'],direction=direction,strategy=strategy, client= PolygoneClient())
                if creditVerticalSpreadTest.matchOption(date=Option.get_followingThirdFriday()):
                    print(Fore.GREEN + creditVerticalSpreadTest.get_plain_English_Result()+Fore.RESET)
                else:
                    logger.info("No match for %s"% stock['Ticker'])
                logger.debug(creditVerticalSpreadTest.toJSON())
            except MarketDataException as e:
                logger.warning("Fail to get options %s"% stock['Ticker'])
                logger.warning(e)
            except ReadTimeout as e:
                logger.warning("Readtimeout for %s"% stock['Ticker'])
                logger.warning(e)
                PolygoneClient().release()

            try:
                direction=dm.BEARISH
                strategy=dm.CREDIT
                creditVerticalSpreadTest = CreditSpread(underlying_ticker=stock['Ticker'],direction=direction,strategy=strategy, client= PolygoneClient())
                if creditVerticalSpreadTest.matchOption(date=Option.get_followingThirdFriday()):
                    print(Fore.RED + creditVerticalSpreadTest.get_plain_English_Result()+ Fore.RESET)
                else:
                    logger.info("No match for %s"% stock['Ticker'])
                logger.debug(creditVerticalSpreadTest.toJSON())
            except MarketDataException as e:
                logger.warning("Fail to get options %s"% stock['Ticker'])
                logger.warning(e)
            except ReadTimeout as e:
                logger.warning("Readtimeout for %s"% stock['Ticker'])
                logger.warning(e)
                PolygoneClient.release()
    print("done")
            