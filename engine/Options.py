import calendar
import datetime
import logging
import operator

from MarketDataClients.MarketDataClient import MarketDataStrikeNotFoundException, MarketDataException, MarketDataClient
from engine.data_model import SpreadDataModel, BULLISH, BEARISH, CREDIT, DEBIT, SPREAD_TYPE, DESC, ASC

logger = logging.getLogger(__name__)

class Option:
    """Helper class for calculating option expiration dates."""
    @staticmethod
    def get_thirdFridayOfMonth(year, month):
        """Calculates the date of the third Friday of a given month and year."""
        c = calendar.Calendar(firstweekday=calendar.SUNDAY)
        monthcal = c.monthdatescalendar(year, month)
        third_friday = [day for week in monthcal for day in week if
                        day.weekday() == calendar.FRIDAY and
                        day.month == month][2]
        return third_friday

    @staticmethod
    def get_thirdFridayOfCurrentMonth():
        """Calculates the date of the third Friday of the current month."""
        today = datetime.datetime.today()
        year = today.year
        month = today.month
        return Option.get_thirdFridayOfMonth(year, month)

    @staticmethod
    def get_followingThirdFriday():
        """Calculates the date of the third Friday of the next month."""
        today = datetime.datetime.today()
        year = today.year
        month = today.month + 1
        return Option.get_thirdFridayOfMonth(year, month)


class VerticalSpread(SpreadDataModel):
    """Base class for vertical spread calculations (credit and debit)."""
    MAX_STRIKES = 20  # Maximum number of strikes to consider
    MIN_DELTA = 0.26  # Minimum absolute delta for a contract to be considered

    def __init__(self, underlying_ticker, direction, strategy, client):
        """Initializes VerticalSpread with market data."""
        logger.info("Processing %s", underlying_ticker)
        self.underlying_ticker = underlying_ticker
        self.client = MarketDataClient()
        self.previous_close = self.client.get_previous_stock_close(self.underlying_ticker)
        logger.info("%s last close price :%s", self.underlying_ticker, self.previous_close)
        self.contract_type = SPREAD_TYPE[strategy][direction]
        self.order = self.get_order(strategy, direction)
        self.direction = direction
        self.strategy = strategy
        self.secondLegDepth = 0

    def get_order(self, strategy, direction):
        """Returns the order (ASC/DESC) based on strategy and direction."""
        return {CREDIT: {BULLISH: DESC, BEARISH: ASC}, DEBIT: {BULLISH: ASC, BEARISH: DESC}}[strategy][direction]

    def calculateAbsDelta(self, previous_premium, premium, previous_price, price):
        """Calculates the absolute delta between two option contracts."""
        try:
            premium_delta = previous_premium - premium
            price_delta = previous_price - price
            return abs(premium_delta / price_delta)
        except ZeroDivisionError:
            logger.warning(f"Division by zero calculating delta for {self.underlying_ticker}.")
            return 0

    def matchOption(self, date, expiration_date_gte, expiration_date_lte):
        """Finds suitable short and long options for a vertical spread."""
        self.secondLegDepth = 0
        first_leg_contract = None  # First leg (e.g., short contract)
        first_leg_premium = None
        previous_premium = None
        previous_contract = None
        self.expiration_date = date

        try:
            self.contracts = self.client.get_option_contracts(
                underlying_ticker=self.underlying_ticker,
                expiration_date_gte=expiration_date_gte,
                expiration_date_lte=expiration_date_lte,
                contract_type=self.contract_type,
                order=self.order
            )
            
            for contract in self.contracts:
                if self.get_search_op(self.strategy, self.direction)(self.previous_close,
                                                                    round(float(contract['strike_price']), 2)) and \
                self.secondLegDepth < self.MAX_STRIKES:
                    self.secondLegDepth += 1
                    premium = self.client.get_option_previous_close(contract['ticker'])

                    # Stage the first leg (put or call) based on the contract
                    if first_leg_contract is None:
                        first_leg_contract = contract
                        first_leg_premium = premium
                        logger.info("Staging FIRST LEG contract: %s for a premium of %.2f", first_leg_contract['ticker'], first_leg_premium)
                    
                    # Stage the second leg (put or call) based on the contract
                    else:
                        if first_leg_contract['expiration_date'] != contract['expiration_date']:
                            logger.warning("Exit as we are going vertical")
                            break 
                         
                        self.distance_between_Strikes = abs(
                            float(contract['strike_price']) - float(first_leg_contract['strike_price']))
                        delta = self.calculateAbsDelta(previous_premium=float(previous_premium), premium=float(premium),
                                                       previous_price=float(previous_contract['strike_price']),
                                                       price=float(contract['strike_price']))
                        logger.debug('delta %s, self.distance_between_Strikes %s', delta, self.distance_between_Strikes)
                        if delta <= self.MIN_DELTA:
                            spread_premium = abs(float(first_leg_premium) - float(premium))
                            logger.debug('spread_premium %s', spread_premium)

                            if spread_premium >= self.distance_between_Strikes / 3:
                                # Assign based on direction and strategy
                                if self.strategy == CREDIT:
                                    self.long_premium = premium
                                    self.long_contract = contract
                                    self.short_contract = first_leg_contract
                                    self.short_premium = first_leg_premium
                                elif self.strategy == DEBIT:
                                    self.long_premium = first_leg_premium
                                    self.long_contract = first_leg_contract
                                    self.short_contract = contract
                                    self.short_premium = premium
                                else:
                                    # Handle other combinations as needed
                                    logger.warning("Unsupported strategy and direction combination.")

                                logger.info("Assigned LONG contract: %s for a premium of %.2f",
                                            self.long_contract['ticker'], self.long_premium)

                                # Calculate and assign other parameters
                                self.max_risk = self.get_max_risk()
                                self.max_reward = self.get_max_reward()
                                self.breakeven = self.get_breakeven_price()
                                self.entry_price = self.get_close_price()
                                self.target_price = self.get_target_price()
                                self.stop_price = self.get_stop_price()
                                self.exit_date_str = self.get_exit_date().strftime('%Y-%m-%d')
                                break

                    previous_premium = premium
                    previous_contract = contract
            return self.short_contract is not None and self.long_contract is not None
        except (MarketDataStrikeNotFoundException, MarketDataException) as e:
            logger.warning(f"Error getting option contracts: {e}")
            return False
        except Exception as e:
            logger.exception(f"An unexpected error occurred in matchOption: {e}")
            return False
    def get_search_op(self, strategy, direction):
        """Returns the search operator (operator.ge or operator.le) based on strategy and direction."""
        return {CREDIT: {BULLISH: operator.ge, BEARISH: operator.le}, DEBIT: {BULLISH: operator.le, BEARISH: operator.ge}}[strategy][direction]

    def get_net_premium(self):
            return abs(self.short_premium - self.long_premium)

    def get_close_price(self):
        return self.previous_close
    
    def get_expiration_date(self):
        return  self.expiration_date

    def get_exit_date(self):
        return self.get_expiration_date() - datetime.timedelta(days=21)

    def get_short(self):
        return self.short_contract

    def get_Long(self):
        return self.long_contract

    def to_dict(self):
        return super().to_dict()

    def get_plain_English_Result(self):
        return f"Sell {self.get_short()['ticker']}, buy {self.get_Long()['ticker']}; " \
            f"max risk {self.max_risk:.2f}, max reward {self.max_reward:.2f}, breakeven {self.breakeven:.2f}, " \
            f"enter at {self.entry_price:.2f}, target exit at {self.target_price:.2f}, " \
            f"stop loss at {self.stop_price:.2f} and before {self.exit_date_str}"


    def get_max_reward(self):
        pass

    def get_max_risk(self):
        pass

    def get_breakeven_price(self):
        pass

    def get_target_price(self):
        pass

    def get_stop_price(self):
        pass


class CreditSpread(VerticalSpread):
    idealExpiration = 45

    def __init__(self, underlying_ticker, direction, strategy, client):
        super().__init__(underlying_ticker=underlying_ticker, direction=direction, strategy=strategy, client=client)
        self.option = None
        self.description = None

    def matchOption(self, date=None):
        if date:
            result = super().matchOption(date, expiration_date_gte=date, expiration_date_lte=date)
            if result:
                self.option = f'{{"date": "{date.strftime("%Y-%m-%d")}", "direction": "{self.direction}", "strategy": "{self.strategy}"}}'
                self.description = self.get_plain_English_Result()
            return result
        else:
            expiration_date = datetime.date.today() 
            result = super().matchOption(expiration_date, expiration_date, expiration_date_gte=expiration_date + datetime.timedelta(days=self.idealExpiration - 4),
                                       expiration_date_lte=expiration_date + datetime.timedelta(days=self.idealExpiration + 2))
            if result:
                date = datetime.date.today() + datetime.timedelta(days=self.idealExpiration)
                self.option = f'{{"date": "{date.strftime("%Y-%m-%d")}", "direction": "{self.direction}", "strategy": "{self.strategy}"}}'
                self.description = self.get_plain_English_Result()
            return result

    def get_max_reward(self):
        return self.get_net_premium()

    def get_max_risk(self):
        return self.distance_between_Strikes - self.get_net_premium()

    def get_breakeven_price(self):
        net_premium = self.get_net_premium()
        return float(self.short_contract['strike_price']) + (-net_premium if self.direction == BULLISH else net_premium)

    def get_target_price(self):
        target_reward = (self.get_max_reward()*0.8)
        return self.previous_close + (target_reward if self.direction == BULLISH else -target_reward)

    def get_stop_price(self):
        target_stop = (self.get_max_risk()/2)
        return self.previous_close - (target_stop if self.direction == BULLISH else -target_stop)


class DebitSpread(VerticalSpread):
    idealExpiration = 45

    def __init__(self, underlying_ticker, direction, strategy, client):
        super().__init__(underlying_ticker=underlying_ticker, direction=direction, strategy=strategy, client=client)
        self.option = None
        self.description = None

    def matchOption(self, date=None):
        if date:
            result = super().matchOption(date, expiration_date_gte=date, expiration_date_lte=date)
            if result:
                self.option = f'{{"date": "{date.strftime("%Y-%m-%d")}", "direction": "{self.direction}", "strategy": "{self.strategy}"}}'
                self.description = self.get_plain_English_Result()
            return result
        else:
            expiration_date = datetime.date.today() 
            result = super().matchOption(expiration_date, expiration_date_gte=expiration_date + datetime.timedelta(days=self.idealExpiration - 4),
                                       expiration_date_lte=expiration_date + datetime.timedelta(days=self.idealExpiration + 2))
            if result:
                date = datetime.date.today() + datetime.timedelta(days=self.idealExpiration)
                self.option = f'{{"date": "{date.strftime("%Y-%m-%d")}", "direction": "{self.direction}", "strategy": "{self.strategy}"}}'
                self.description = self.get_plain_English_Result()
            return result

    def get_max_reward(self):
        return self.distance_between_Strikes + self.get_net_premium()

    def get_max_risk(self):
        return self.get_net_premium()

    def get_breakeven_price(self):
        net_premium = self.get_net_premium()
        return float(self.long_contract['strike_price']) + (-net_premium if self.direction == BULLISH else net_premium)

    def get_target_price(self):
        target_reward = (self.get_max_reward()*0.8)
        return self.previous_close + (target_reward if self.direction == BULLISH else -target_reward)

    def get_stop_price(self):
        target_stop = (self.get_max_risk()/2)
        return self.previous_close - (target_stop if self.direction == BULLISH else -target_stop)