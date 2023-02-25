from MarketDataClients.MarketDataClient import MarketDataException
from engine.Options import CreditSpread, Option
from PolygoneClients.PolygoneClient import PolygoneClient
from requests import ReadTimeout
import json
import logging
import json

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    with open("config/stocks.json") as file:
        stocks = json.load(file)
        for stock in stocks:
            try:
                direction=CreditSpread.BULLISH
                strategy=CreditSpread.CREDIT
                creditVerticalSpreadTest = CreditSpread(underlying_ticker=stock['Ticker'],direction=direction,strategy=strategy, client= PolygoneClient())
                if creditVerticalSpreadTest.matchOption(date=Option.get_followingThirdFriday()):
                    print(creditVerticalSpreadTest.get_plain_English_Result())
                else:
                    logging.info("No match for %s"% stock['Ticker'])
            except MarketDataException as e:
                logging.warning("Fail to get options %s"% stock['Ticker'])
                logging.warning(e)
            try:
                direction=CreditSpread.BEARISH
                strategy=CreditSpread.CREDIT
                creditVerticalSpreadTest = CreditSpread(underlying_ticker=stock['Ticker'],direction=direction,strategy=strategy, client= PolygoneClient())
                if creditVerticalSpreadTest.matchOption(date=Option.get_followingThirdFriday()):
                    print(creditVerticalSpreadTest.get_plain_English_Result())
                else:
                    logging.info("No match for %s"% stock['Ticker'])
            except MarketDataException as e:
                logging.warning("Fail to get options %s"% stock['Ticker'])
                logging.warning(e)
            except ReadTimeout as e:
                logging.warning("Readtimeout for %s"% stock['Ticker'])
                logging.warning(e)
                PolygoneClient.release()
    print("done")
            