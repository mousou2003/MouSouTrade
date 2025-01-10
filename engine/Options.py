import calendar
import datetime
import logging
import operator
from MarketDataClients.MarketDataClient import MarketDataStrikeNotFoundException, MarketDataException, MarketDataClient
from engine.data_model import SpreadDataModel
import engine.data_model as datamodel
logger = logging.getLogger(__name__)

class Option:
    @staticmethod
    def get_thirdFridayOfMonth(year, month):
        c = calendar.Calendar(firstweekday=calendar.SUNDAY)
        monthcal = c.monthdatescalendar(year, month)
        third_friday = [day for week in monthcal for day in week if
                        day.weekday() == calendar.FRIDAY and
                        day.month == month][2]
        return third_friday

    @staticmethod
    def get_thirdFridayOfCurrentMonth():
        today = datetime.datetime.today()
        year = today.year;
        month = today.month
        return Option.get_thirdFridayOfMonth(year, month)

    @staticmethod
    def get_followingThirdFriday():
        today = datetime.datetime.today()
        year = today.year;
        month = today.month + 1
        return Option.get_thirdFridayOfMonth(year, month)


class VerticalSpread(SpreadDataModel):
    REQUEST_ORDER={datamodel.CREDIT:{datamodel.BULLISH:datamodel.DESC, datamodel.BEARISH:datamodel.ASC},datamodel.DEBIT:{datamodel.BULLISH:datamodel.ASC, datamodel.BEARISH:datamodel.DESC}}
    SEARCH_OPS={datamodel.CREDIT:{datamodel.BULLISH:operator.ge, datamodel.BEARISH:operator.le},datamodel.DEBIT:{datamodel.BULLISH:operator.le, datamodel.BEARISH:operator.ge}}
    WRONG_DIRECTION_ADJ_OPS={datamodel.CREDIT:{datamodel.BULLISH:operator.sub, datamodel.BEARISH:operator.add},datamodel.DEBIT:{datamodel.BULLISH:operator.add, datamodel.BEARISH:operator.sub}}
    GOOD_DIRECTION_ADJ_OPS={datamodel.CREDIT:{datamodel.BULLISH:operator.add, datamodel.BEARISH:operator.sub},datamodel.DEBIT:{datamodel.BULLISH:operator.sub, datamodel.BEARISH:operator.add}}
    MAX_STRIKES = 20 # we limit the number of strike to improve performance
    MIN_DELTA =0.26 # no benefit to sell or buy an option under this delta

    #client = None

    def __init__(self, underlying_ticker, direction, strategy, client):
        logger.info("processing %s" % underlying_ticker)
        self.underlying_ticker = underlying_ticker
        self.client = MarketDataClient()
        self.previous_close = self.client.get_previous_stock_close(self.underlying_ticker)
        logger.info("%s last close price :%s"% (self.underlying_ticker, self.previous_close))
        self.contract_type = datamodel.SPREAD_TYPE[strategy][direction]
        self.order = self.REQUEST_ORDER[strategy][direction]
        self.direction = direction
        self.strategy = strategy
        self.short_contract = None
        self.long_contract = None
        self.short_premium = None
        self.long_premium = None
        self.distance_between_Strikes = None

    def calculateAbsDelta(self, previous_premium, premium, previous_price, price):
        try:
            premium_delta = previous_premium - premium
            price_delta = previous_price - price
            return abs(premium_delta / price_delta)
        except ZeroDivisionError:
            logger.warning(f"Division by zero calculating delta for {self.underlying_ticker}.")
            return 0  # Or handle appropriately for your use case

    def matchOption(self, expiration_date_gte, expiration_date_lte):
        n_strikes = 0
        self.contracts = self.client.get_option_contracts(underlying_ticker=self.underlying_ticker,
                                                          expiration_date_gte=expiration_date_gte,
                                                          expiration_date_lte=expiration_date_lte,
                                                          contract_type=self.contract_type,
                                                          order=self.order)
        for contract in self.contracts:
            try:
                if self.SEARCH_OPS[self.strategy][self.direction](self.previous_close,
                                                                   round(float(contract['strike_price']), 1)) and \
                        n_strikes < self.MAX_STRIKES:
                    n_strikes += 1
                    premium = self.client.get_option_previous_close(contract['ticker'])
                    if self.short_contract is None:
                        self.short_premium = premium
                        self.short_contract = contract
                        logger.info(
                            f"Found a SHORT with : {self.short_contract['ticker']} for a premium of {premium:.5f}")
                    else:
                        if self.short_contract['expiration_date'] != contract['expiration_date']:
                            logger.warning("Exit as we are going vertical")
                            break
                        self.distance_between_Strikes = abs(
                            float(contract['strike_price']) - float(self.short_contract['strike_price']))
                        delta = self.calculateAbsDelta(previous_premium=self.short_premium, premium=premium,
                                                       previous_price=float(self.short_contract['strike_price']),
                                                       price=float(contract['strike_price']))
                        if delta <= self.MIN_DELTA:
                            spread_premium = abs(self.short_premium - premium)
                            if spread_premium >= self.distance_between_Strikes / 3:
                                self.long_premium = premium
                                self.long_contract = contract
                                logger.info(
                                    f"Found a LONG with : {contract['ticker']} for a premium of {premium:.5f} with short delta of {delta:.5f}")
                            break
            except MarketDataStrikeNotFoundException as e:
                logger.info(e)
            except Exception as e:
                logger.warning(f"Error processing contract {contract.get('ticker', 'N/A')}: {e}")

        return self.short_contract is not None and self.long_contract is not None

    # ... (rest of VerticalSpread methods remain largely the same, with adjustments for debit spreads) ...

    def get_max_risk(self):
        if self.strategy == datamodel.CREDIT:
            return abs(self.distance_between_Strikes - (self.short_premium - self.long_premium))
        elif self.strategy == datamodel.DEBIT:
            return self.short_premium + self.long_premium
        else:
            raise ValueError("Invalid strategy")

    def get_breakeven_price(self):
        if self.strategy == datamodel.CREDIT:
            return self.WRONG_DIRECTION_ADJ_OPS[self.strategy][self.direction](
                float(self.short_contract['strike_price']), self.get_max_reward())
        elif self.strategy == datamodel.DEBIT:
            return self.GOOD_DIRECTION_ADJ_OPS[self.strategy][self.direction](
                float(self.short_contract['strike_price']), self.get_max_reward())
        else:
            raise ValueError("Invalid strategy")

    def get_max_reward(self):
        if self.strategy == datamodel.CREDIT:
            return self.short_premium - self.long_premium
        elif self.strategy == datamodel.DEBIT:
            return float('inf')
        else:
            raise ValueError("Invalid strategy")

    def get_plain_English_Result(self):
        buy_sell = ("Buy", "Sell") if self.strategy == datamodel.DEBIT else ("Sell", "Buy")
        return format(
            f"{buy_sell[1]} {self.get_short()['ticker']}, {buy_sell[0]} {self.get_Long()['ticker']}; max risk {self.get_max_risk():.5f}, max reward {self.get_max_reward():.5f}, breakeven {self.get_breakeven_price():.5f}, enter at {self.get_close_price():.5f}, target exit at {self.get_target_price():.5f}, stop loss at {self.get_stop_price():.5f} and before {self.get_exit_date().strftime('%Y-%m-%d')}")


class CreditSpread(VerticalSpread):
    idealExpiration = 45

    def __init__(self, underlying_ticker, direction, strategy, client):
        super().__init__(underlying_ticker=underlying_ticker, direction=direction, strategy=strategy, client=client)

    def matchOption(self, date=None):
        if date:
            return super().matchOption(expiration_date_gte=date, expiration_date_lte=date)
        else:
            return super().matchOption(expiration_date_gte=datetime.date.today() + datetime.timedelta(days=self.idealExpiration - 4),
                                       expiration_date_lte=datetime.date.today() + datetime.timedelta(days=self.idealExpiration + 2))

    def get_target_price(self):
        return self.GOOD_DIRECTION_ADJ_OPS[self.strategy][self.direction](self.previous_close, self.get_max_reward())

    def get_stop_price(self):
        return self.WRONG_DIRECTION_ADJ_OPS[self.strategy][self.direction](self.previous_close, 2 * self.get_max_reward())

    def get_exit_date(self):
        return datetime.datetime.strptime(self.short_contract['expiration_date'], '%Y-%m-%d') - datetime.timedelta(days=21)


class DebitSpread(VerticalSpread):
    idealExpiration = 45

    def __init__(self, underlying_ticker, direction, strategy, client):
        super().__init__(underlying_ticker=underlying_ticker, direction=direction, strategy=strategy, client=client)

    def matchOption(self, date=None):
        if date:
            return super().matchOption(expiration_date_gte=date, expiration_date_lte=date)
        else:
            return super().matchOption(expiration_date_gte=datetime.date.today() + datetime.timedelta(days=self.idealExpiration - 4),
                                       expiration_date_lte=datetime.date.today() + datetime.timedelta(days=self.idealExpiration + 2))

    def get_target_price(self):
        return self.GOOD_DIRECTION_ADJ_OPS[self.strategy][self.direction](self.previous_close, self.get_max_reward())

    def get_stop_price(self):
        return self.WRONG_DIRECTION_ADJ_OPS[self.strategy][self.direction](self.previous_close, 2 * self.get_max_reward())

    def get_exit_date(self):
        return datetime.datetime.strptime(self.short_contract['expiration_date'], '%Y-%m-%d') - datetime.timedelta(days=21)
