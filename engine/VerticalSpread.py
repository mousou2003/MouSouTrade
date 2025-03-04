from engine.data_model import *
from engine.Options import Options, TradeStrategy  # Import TradeStrategy
import logging
from datetime import datetime, timedelta
from typing import ClassVar, Optional, List, Tuple
from decimal import Decimal, InvalidOperation, Inexact, getcontext

from marketdata_clients.BaseMarketDataClient import IMarketDataClient, MarketDataException

logger = logging.getLogger(__name__)

class VerticalSpread(SpreadDataModel):
    """Base class for vertical spread calculations (credit and debit)."""
    MAX_STRIKES: ClassVar[int] = 20  # Maximum number of strikes to consider
    MIN_DELTA: ClassVar[Decimal] = Decimal(0.26)  # Minimum absolute delta for a contract to be considered
    SHORT_PREMIUM_MULTIPLIER: ClassVar[Decimal] = Decimal(0.95)  # Multiplier for short premium
    LONG_PREMIUM_MULTIPLIER: ClassVar[Decimal] = Decimal(1.05)  # Multiplier for long premium

    market_data_client: IMarketDataClient = None
    contracts: List[Contract] = []

    def find_first_leg_contract(self) -> bool:
        """
        Finds the first leg contract for a vertical spread based on the strategy and direction.

        Returns:
        bool : True if a suitable first leg contract is found, False otherwise
        """
        try:
            result = Options.select_contract(
                self.contracts, self.strategy, self.direction, self.market_data_client, self.underlying_ticker, 
                TradeStrategy.DIRECTIONAL)
            if result is None:
                return False
            self.first_leg_contract, self.first_leg_contract_position, self.first_leg_snapshot = result
            return True
        except ValueError as e:
            logger.error(f"Error finding first leg contract: {e}")
            return False

    def find_second_leg_contract(self, start: int, stop: int) -> bool:
        """
        Finds the second leg contract for a vertical spread based on the strategy and direction.

        Parameters:
        start : int : Starting index for the search
        stop : int : Stopping index for the search

        Returns:
        bool : True if a suitable second leg contract is found, False otherwise
        """
        try:
            result = Options.select_contract(
                self.contracts, self.strategy, self.direction, self.market_data_client, self.underlying_ticker, 
                TradeStrategy.HIGH_PROBABILITY)
            if result is None:
                return False
            self.second_leg_contract, self.second_leg_contract_position, self.second_leg_snapshot = result
            return True
        except ValueError as e:
            logger.error(f"Error finding second leg contract: {e}")
            return False

    def match_option(self, market_data_client: IMarketDataClient, underlying_ticker: str, 
                     direction: DirectionType, strategy: StrategyType, previous_close: Decimal, date: datetime, contracts) -> bool:
        self.market_data_client = market_data_client
        self.underlying_ticker = underlying_ticker
        self.direction = direction
        self.strategy = strategy
        self.previous_close = previous_close
        self.expiration_date = date
        self.second_leg_depth = 0
        self.update_date = datetime.today().date()
        self.contracts = contracts

        try:
            days_to_expiration = (self.expiration_date - self.update_date).days

            if not self.find_first_leg_contract():
                logger.info("No suitable first leg contract found.")
                return False

            logger.info("Staging FIRST LEG contract: %s for previous close of %.5f", self.first_leg_contract.ticker, previous_close)

            if self.strategy == StrategyType.CREDIT:
                try:
                    self.short_contract = self.first_leg_contract
                    self.short_premium = self.first_leg_snapshot.day.close * self.SHORT_PREMIUM_MULTIPLIER
                except Inexact:
                    logger.error("Inexact value encountered in short premium calculation")
                    raise

            elif self.strategy == StrategyType.DEBIT:
                try:
                    self.long_premium = self.first_leg_snapshot.day.close * self.LONG_PREMIUM_MULTIPLIER
                    self.long_contract = self.first_leg_contract
                except Inexact:
                    logger.error("Inexact value encountered in long premium calculation")
                    raise
            
            start = max(self.first_leg_contract_position - self.MAX_STRIKES, 0)
            stop = self.first_leg_contract_position

            # Second loop to search for the matching contract
            if self.find_second_leg_contract(start, stop):
                premium_delta = self.first_leg_snapshot.day.close - self.second_leg_snapshot.day.close
                if premium_delta == 0:
                    raise Exception("Premium delta is zero")
                self.distance_between_strikes = abs(self.first_leg_contract.strike_price - self.second_leg_contract.strike_price)
                if self.distance_between_strikes == 0:
                    raise ZeroDivisionError("Distance between strikes is zero")

                relative_delta = abs(premium_delta / self.distance_between_strikes)

                logger.debug('distance_between_strikes %.5f, premium_delta %.5f', self.distance_between_strikes, premium_delta)

                if relative_delta == Decimal(0):
                    logger.error("Delta is zero, skipping")
                    raise Exception("Delta is zero")
                if relative_delta >= self.MIN_DELTA:
                    if self.strategy == StrategyType.CREDIT:
                        try:
                            self.long_premium = self.second_leg_snapshot.day.close * self.LONG_PREMIUM_MULTIPLIER
                            self.long_contract = self.second_leg_contract
                        except Inexact:
                            logger.warning("Inexact value encountered in long premium calculation, skipping")
                            return False
                    elif self.strategy == StrategyType.DEBIT:
                        try:
                            self.short_contract = self.second_leg_contract
                            self.short_premium = self.second_leg_snapshot.day.close * self.SHORT_PREMIUM_MULTIPLIER
                        except Inexact:
                            logger.warning("Inexact value encountered in short premium calculation, skipping")
                            return False

                    self.description = self.get_description()
                    logger.info(f'Found a match! {self.second_leg_contract.ticker} with delta {self.second_leg_snapshot.greeks.delta}')

                    # Calculate and assign other parameters
                    self.net_premium = self.short_premium - self.long_premium
                    self.max_risk = self.get_max_risk()
                    self.max_reward = self.get_max_reward()
                    self.breakeven = self.get_breakeven_price()
                    self.entry_price = self.get_close_price()
                    self.target_price = self.get_target_price()
                    self.stop_price = self.get_stop_price()
                    self.exit_date = self.get_exit_date()
                    self.description = self.get_description()

                    # Calculate Probability of Profit (POP)
                    self.probability_of_profit = Options.calculate_probability_of_profit(
                        current_price=Decimal(self.previous_close),
                        breakeven_price=Decimal(self.breakeven),
                        days_to_expiration=days_to_expiration,
                        implied_volatility=Decimal(self.second_leg_snapshot.implied_volatility)
                    )

                    self.description = f"Sell {self.short_contract.strike_price} {self.short_contract.contract_type.value}, "\
                        f"buy {self.long_contract.strike_price} {self.long_contract.contract_type.value}; " \
                        f"max risk {self.max_risk:.2f}, max reward {self.max_reward:.2f}, breakeven {self.breakeven:.2f}, " \
                        f"enter at {self.entry_price:.2f}, target exit at {self.target_price:.2f}, " \
                        f"stop loss at {self.stop_price:.2f} and before {self.exit_date}."
                    if self.second_leg_snapshot.open_interest < 100:
                        self.description += f"\nOpen Interest is less than 100, careful!"
                    if self.second_leg_snapshot.day.volume < 100:
                        self.description += f"\nVolume is less than 100, careful!"

                    logger.info(f'Found a match! {self.second_leg_contract.ticker} with delta {self.second_leg_snapshot.greeks.delta}')

                    return True

            if self.second_leg_contract is None:
                logger.info("No suitable second leg found.")

            return False

        except Exception as e:
            logger.exception(f"An unexpected error occurred in match_option: {e}")
            raise

    def get_net_premium(self):
        return Decimal(self.net_premium)

    def get_close_price(self):
        return Decimal(self.previous_close)

    def get_expiration_date(self):
        return self.expiration_date

    def get_exit_date(self):
        return self.get_expiration_date() - timedelta(days=21)

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

    def match_option(self, market_data_client: IMarketDataClient, underlying_ticker: str, direction: DirectionType, strategy: StrategyType, previous_close: Decimal, date: datetime, contracts) -> bool:
        return super().match_option(market_data_client, underlying_ticker, direction, strategy, previous_close, date, contracts)

    def get_max_reward(self):
        return self.get_net_premium()*100

    def get_max_risk(self):
        return Decimal((abs(self.distance_between_strikes) - self.get_net_premium())*Decimal(100))

    def get_breakeven_price(self):
        net_premium = self.get_net_premium()
        return Decimal(self.short_contract.strike_price) + (-net_premium if self.direction == DirectionType.BULLISH else net_premium)

    def get_target_price(self):
        target_reward = (self.get_net_premium() * Decimal(0.8))
        return self.previous_close + (target_reward if self.direction == DirectionType.BULLISH else -target_reward)

    def get_stop_price(self):
        target_stop = (self.get_net_premium() / Decimal(2))
        return self.previous_close - (target_stop if self.direction == DirectionType.BULLISH else -target_stop)

class DebitSpread(VerticalSpread):
    ideal_expiration: ClassVar[int] = 45

    def match_option(self, market_data_client: IMarketDataClient, underlying_ticker: str, direction: DirectionType, strategy: StrategyType, previous_close: Decimal, date: datetime, contracts) -> bool:
        return super().match_option(market_data_client, underlying_ticker, direction, strategy, previous_close, date, contracts)

    def get_max_reward(self):
        return (self.distance_between_strikes - self.long_premium)*100

    def get_max_risk(self):
        return abs(self.get_net_premium()*100)

    def get_breakeven_price(self):
        net_premium = self.get_net_premium()
        return Decimal(self.long_contract.strike_price) + (-net_premium if self.direction == DirectionType.BULLISH else net_premium)

    def get_target_price(self):
        target_reward = (self.get_net_premium() * Decimal(0.8))
        return self.previous_close + (target_reward if self.direction == DirectionType.BULLISH else -target_reward)

    def get_stop_price(self):
        target_stop = (self.get_net_premium() / Decimal(2))
        return self.previous_close - (target_stop if self.direction == DirectionType.BULLISH else -target_stop)