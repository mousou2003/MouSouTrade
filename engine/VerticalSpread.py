from marketdata_clients.PolygonStocksClient import PolygonStocksClient
from marketdata_clients.MarketDataClient import MarketDataStrikeNotFoundException, MarketDataException
from engine.data_model import *
from engine.Options import Options
import logging
import datetime
import operator
from typing import ClassVar, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)

class VerticalSpread(SpreadDataModel):
    """Base class for vertical spread calculations (credit and debit)."""
    MAX_STRIKES: ClassVar[int] = 20  # Maximum number of strikes to consider
    MIN_DELTA: ClassVar[Decimal] = Decimal(0.26)  # Minimum absolute delta for a contract to be considered
    def __init__(self, underlying_ticker, direction, strategy, previous_close=None):
        super().__init__(underlying_ticker=underlying_ticker, direction=direction, strategy=strategy)
        
        """Initializes VerticalSpread with market data."""
        logger.info("Processing %s", underlying_ticker)
        self.underlying_ticker = underlying_ticker
        self.previous_close = previous_close if previous_close is not None else PolygonStocksClient().get_previous_stock_close(self.underlying_ticker)
        logger.info("%s last close price :%s", self.underlying_ticker, self.previous_close)
        self.contract_type = SPREAD_TYPE[strategy][direction]
        self.direction = direction
        self.strategy = strategy

    def get_order(self, strategy, direction):
        """Returns the order (ASC/DESC) based on strategy and direction."""
        return {CREDIT: {BULLISH: ASC, BEARISH: DESC}, DEBIT: {BULLISH: ASC, BEARISH: DESC}}[strategy][direction]

    def match_option(self, date: datetime.date):
        """Finds suitable short and long options for a vertical spread."""
        self.second_leg_depth = 0
        first_leg_contract = None
        first_leg_premium: Optional[Decimal] = None
        self.expiration_date = date

        try:
            options = Options(
                underlying_ticker=self.underlying_ticker,
                expiration_date_gte=self.expiration_date,
                expiration_date_lte=self.expiration_date,
                contract_type=self.contract_type,
                order=self.get_order(strategy=self.strategy, direction=self.direction)
            )
            self.contracts = options.get_option_contracts()

            # First loop to search for the first_leg_contract
            first_leg_contract_position = -1
            first_leg_strike_price = Decimal(0.0)
            premium: Optional[Decimal] = None
            for contract in self.contracts:
                first_leg_contract_position += 1
                distance_between_strikes = abs(Decimal(contract['strike_price']) - self.previous_close)
                if self.get_search_op(self.strategy, self.direction)(Decimal(contract['strike_price']), self.previous_close) and\
                    distance_between_strikes < Decimal(0.1) * self.previous_close :
                    try:
                        if self.get_order(strategy=self.strategy, direction=self.direction) == DESC:
                            contract = self.contracts[first_leg_contract_position - 1]
                        snapshot = options.get_snapshot(option_symbol=contract['ticker'])
                        premium = snapshot['day']['close']
                        first_leg_contract = contract
                        first_leg_premium = premium
                        first_leg_strike_price = Decimal(contract['strike_price'])  # Store first leg strike price
                        logger.info("Staging FIRST LEG contract: %s for a premium of %.5f, for previous close of %.5f", first_leg_contract['ticker'],
                                     first_leg_premium,self.previous_close)
                        break
                    except MarketDataException as e:
                        logger.warning(f"Error getting previous close for first leg contract {contract['ticker']}:\n{e.with_traceback(None)}")
                        continue
                    except KeyError as e:
                        logger.warning(f"KeyError accessing 'day' or 'close' in snapshot for {contract['ticker']}: {e}")
                        continue
                    
            if not first_leg_contract:
                logger.info("No suitable short contract found.")
                return False
            
            # Assign based on direction and strategy
            if self.strategy == CREDIT:
                self.short_contract = first_leg_contract
                self.short_premium = first_leg_premium
            elif self.strategy == DEBIT:
                self.long_premium = first_leg_premium
                self.long_contract = first_leg_contract

            # Second loop to search for the matching contract
            for contract in self.contracts[first_leg_contract_position-self.MAX_STRIKES:first_leg_contract_position - 1]:
                snapshot = None
                self.second_leg_depth += 1
                self.distance_between_strikes = abs(Decimal(contract['strike_price'] - first_leg_strike_price))
                try:
                    if self.distance_between_strikes > Decimal(0.1) * self.previous_close :
                        logger.debug(f"Distance between strikes {self.distance_between_strikes} is more than 10% of previous close {self.previous_close}")
                        continue
                    snapshot = options.get_snapshot(option_symbol=contract['ticker'])
                    #premium = options.get_option_previous_close(contract['ticker'])
                    logger.debug(f"Snapshot for {contract['ticker']}: {snapshot}")
                    #TODO: check why day is empty
                    premium = snapshot['day']['close']
                except MarketDataException as e:
                    logger.warning(f"Error getting previous close for second leg contract {contract['ticker']}:\n{e}")
                    continue
                except KeyError as e:
                    logger.warning(f"KeyError accessing 'day' or 'close' in snapshot for {contract['ticker']}: {e}")
                    continue

                if first_leg_contract['expiration_date'] != contract['expiration_date']:
                    logger.warning("Exit as we are going asymmetrical")
                    break

                self.net_premium = Decimal(first_leg_premium) - Decimal(premium)
                relative_delta = abs(self.net_premium / self.distance_between_strikes)

                logger.debug('distance_between_strikes %s, premium_delta %s', self.distance_between_strikes, self.net_premium)
                if self.net_premium == Decimal(0):
                    logger.warning("Delta is zero, skipping")
                    continue
                if relative_delta >= self.MIN_DELTA:
                    if abs(Decimal(snapshot["greeks"]["delta"])) < 0.3:
                        logger.debug(f'Delta is less than {snapshot["greeks"]["delta"]}, skipping')
                        continue
                    if abs(Decimal(snapshot["greeks"]["delta"])) > 0.5:
                        logger.warning('Delta is greater than 0.7, carefull!')
                    if snapshot["open_interest"] < 100:
                        logger.warning('Open Interest is less than 100, careful!')

                    logger.info(f'Found a match! {contract["ticker"]} with delta {snapshot["greeks"]["delta"]}')
                    
                    # Assign based on direction and strategy
                    if self.strategy == CREDIT:
                        self.long_premium = premium
                        self.long_contract = contract
                    elif self.strategy == DEBIT:
                        self.short_contract = contract
                        self.short_premium = premium

                    logger.info("Assigned LONG contract: %s for a premium of %.5f",
                                self.long_contract['ticker'], self.long_premium)

                    # Calculate and assign other parameters
                    self.max_risk = self.get_max_risk()
                    self.max_reward = self.get_max_reward()
                    self.breakeven = self.get_breakeven_price()
                    self.entry_price = self.get_close_price()
                    self.target_price = self.get_target_price()
                    self.stop_price = self.get_stop_price()
                    self.exit_date = self.get_exit_date()
                    self.description = self.get_description()
                    
                    # Calculate Probability of Profit (POP)
                    days_to_expiration = (self.expiration_date - datetime.date.today()).days
                    self.probability_of_profit = Options.calculate_probability_of_profit(
                        current_price=Decimal(self.previous_close),
                        breakeven_price=Decimal(self.breakeven),
                        days_to_expiration=days_to_expiration,
                        implied_volatility=Decimal(snapshot['implied_volatility'])
                    )

                    self.description = f"Sell {self.short_contract['strike_price']} {self.short_contract['contract_type']}, "\
                        f"buy {self.long_contract['strike_price']} {self.long_contract['contract_type']}; " \
                        f"max risk {self.max_risk:.2f}, max reward {self.max_reward:.2f}, breakeven {self.breakeven:.2f}, " \
                        f"enter at {self.entry_price:.2f}, target exit at {self.target_price:.2f}, " \
                        f"stop loss at {self.stop_price:.2f} and before {self.exit_date}"
                    
                    break

            if self.long_contract is None:
                logger.info("No suitable long contract found.")

            return self.short_contract is not None and self.long_contract is not None
        except Exception as e:
            logger.exception(f"An unexpected error occurred in match_option: {e}")
            return False

    def get_search_op(self, strategy, direction):
        """Returns the search operator (operator.ge or operator.le) based on strategy and direction.""" 
        return {CREDIT: {BULLISH: operator.ge, BEARISH: operator.le}, DEBIT: {BULLISH: operator.le, BEARISH: operator.ge}}[strategy][direction]

    def get_net_premium(self):
        return self.net_premium

    def get_close_price(self):
        return Decimal(self.previous_close)

    def get_expiration_date(self):
        return self.expiration_date

    def get_exit_date(self):
        return self.get_expiration_date() - datetime.timedelta(days=21)

    def get_short(self):
        return self.short_contract

    def get_long(self):
        return self.long_contract

    def to_dict(self):
        """Override to_dict to ensure only serializable data from the parent SpreadDataModel is included."""
        data = super().to_dict()
        return data

    def get_description(self):
        return self.description

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

    ideal_expiration: ClassVar[int] = 45

    def __init__(self, underlying_ticker, direction, strategy, previous_close=None):
        super().__init__(underlying_ticker=underlying_ticker, direction=direction, strategy=strategy, previous_close=previous_close)

    def get_max_reward(self):
        return self.get_net_premium()

    def get_max_risk(self):
        return abs(self.distance_between_strikes) - self.get_net_premium()

    def get_breakeven_price(self):
        net_premium = self.get_net_premium()
        return Decimal(self.short_contract['strike_price']) + (-net_premium if self.direction == BULLISH else net_premium)

    def get_target_price(self):
        target_reward = (self.get_max_reward() * Decimal(0.8))
        return self.previous_close + (target_reward if self.direction == BULLISH else -target_reward)

    def get_stop_price(self):
        target_stop = (self.get_max_risk() / Decimal(2))
        return self.previous_close - (target_stop if self.direction == BULLISH else -target_stop)

class DebitSpread(VerticalSpread):
    ideal_expiration: ClassVar[int] = 45

    def __init__(self, underlying_ticker, direction, strategy, previous_close=None):
        super().__init__(underlying_ticker=underlying_ticker, direction=direction, strategy=strategy, previous_close=previous_close)

    def get_max_reward(self):
        return self.distance_between_strikes + self.get_net_premium()

    def get_max_risk(self):
        return self.get_net_premium()

    def get_breakeven_price(self):
        net_premium = self.get_net_premium()
        return Decimal(self.long_contract['strike_price']) + (-net_premium if self.direction == BULLISH else net_premium)

    def get_target_price(self):
        target_reward = (self.get_max_reward() * Decimal(0.8))
        return self.previous_close + (target_reward if self.direction == BULLISH else -target_reward)

    def get_stop_price(self):
        target_stop = (self.get_max_risk() / Decimal(2))
        return self.previous_close - (target_stop if self.direction == BULLISH else -target_stop)