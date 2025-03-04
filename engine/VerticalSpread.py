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

        days_to_expiration = (self.expiration_date - self.update_date).days

        first_leg_candidates = Options.select_contract(
            self.contracts, self.market_data_client, self.underlying_ticker, 
            TradeStrategy.DIRECTIONAL)
        if not first_leg_candidates:
            logger.info("No suitable first leg contract found.")
            return False
        logger.debug(f"Number of first leg candidates: {len(first_leg_candidates)}")

        second_leg_candidates = Options.select_contract(
            self.contracts, self.market_data_client, self.underlying_ticker, 
            TradeStrategy.HIGH_PROBABILITY)
        if not second_leg_candidates:
            logger.info("No suitable second leg contract found.")
            return False
        logger.debug(f"Number of second leg candidates: {len(second_leg_candidates)}")
        
        best_spread = None
        best_pop = Decimal(0)

        for first_leg in first_leg_candidates:
            self.first_leg_contract, self.first_leg_contract_position, self.first_leg_snapshot = first_leg

            if self.strategy == StrategyType.CREDIT:
                self.short_contract = self.first_leg_contract
                self.short_premium = self.first_leg_snapshot.day.close * self.SHORT_PREMIUM_MULTIPLIER
            elif self.strategy == StrategyType.DEBIT:
                self.long_premium = self.first_leg_snapshot.day.close * self.LONG_PREMIUM_MULTIPLIER
                self.long_contract = self.first_leg_contract

            start = max(self.first_leg_contract_position - self.MAX_STRIKES, 0)
            stop = self.first_leg_contract_position

            for second_leg in second_leg_candidates:
                self.second_leg_contract, self.second_leg_contract_position, self.second_leg_snapshot = second_leg

                premium_delta = self.first_leg_snapshot.day.close - self.second_leg_snapshot.day.close
                if premium_delta == 0:
                    raise ValueError("Second leg candidate due to zero premium delta indicate an error in the selection.")
                
                self.distance_between_strikes = abs(self.first_leg_contract.strike_price - self.second_leg_contract.strike_price)
                if self.distance_between_strikes == 0:
                    raise ValueError("Zero distance between strikes is not allowed.")

                relative_delta = abs(premium_delta / self.distance_between_strikes)
                if relative_delta == Decimal(0) or relative_delta < self.MIN_DELTA:
                    logger.debug(f"Skipping second leg candidate due to relative delta {relative_delta} being less than minimum delta {self.MIN_DELTA}.")
                    continue

                if self.strategy == StrategyType.CREDIT:
                    self.long_premium = self.second_leg_snapshot.day.close * self.LONG_PREMIUM_MULTIPLIER
                    self.long_contract = self.second_leg_contract
                elif self.strategy == StrategyType.DEBIT:
                    self.short_contract = self.second_leg_contract
                    self.short_premium = self.second_leg_snapshot.day.close * self.SHORT_PREMIUM_MULTIPLIER

                self.net_premium = self.short_premium - self.long_premium
                max_profit_percent = (self.distance_between_strikes - self.long_premium / abs(self.net_premium)) * 100
                self.max_risk = self.get_max_risk()
                self.max_reward = self.get_max_reward()
                self.breakeven = self.get_breakeven_price()
                self.entry_price = self.get_close_price()
                self.target_price = self.get_target_price()
                self.stop_price = self.get_stop_price()
                self.exit_date = self.get_exit_date()

                self.probability_of_profit = Options.calculate_probability_of_profit(
                    current_price=Decimal(self.previous_close),
                    breakeven_price=Decimal(self.breakeven),
                    days_to_expiration=days_to_expiration,
                    implied_volatility=Decimal(self.second_leg_snapshot.implied_volatility)
                )

                if self.strategy == StrategyType.CREDIT:
                    self.description = f"Sell {self.short_contract.strike_price} {self.short_contract.contract_type.value}, \n"\
                                        f"buy {self.long_contract.strike_price} {self.long_contract.contract_type.value}; \n" \
                                        f"max profit as fraction of the distance between strikes {relative_delta*100:.2f}%."
                elif self.strategy == StrategyType.DEBIT:
                    self.description = f"Buy {self.long_contract.strike_price} {self.long_contract.contract_type.value}, \n"\
                                        f"sell {self.short_contract.strike_price} {self.short_contract.contract_type.value}; \n" \
                                        f"max profit as percent of the debit {max_profit_percent:.2f}%."
                if self.second_leg_snapshot.open_interest < 10:
                    self.description += f"\nOpen Interest is less than 10, careful!"
                if self.second_leg_snapshot.day.volume < 10:
                    self.description += f"\nVolume is less than 10, careful!"

                if self.probability_of_profit > best_pop:
                    best_pop = self.probability_of_profit
                    best_spread = self.to_dict()

        if best_spread:
            self.from_dict(best_spread)
            logger.info(f'Found a match! {self.second_leg_contract.ticker} with delta {self.second_leg_snapshot.greeks.delta}')
            return True

        return False

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