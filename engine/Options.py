import calendar
from datetime import datetime, timedelta
import logging
from typing import Tuple
import numpy as np
from scipy.stats import norm
from decimal import Decimal, Inexact, InvalidOperation
from enum import Enum  # Import Enum
from datetime import datetime, timedelta
from marketdata_clients.BaseMarketDataClient import MarketDataException, IMarketDataClient
from engine.data_model import *
import operator

logger = logging.getLogger(__name__)

class TradeStrategy(Enum):
    HIGH_PROBABILITY = 'high_probability'
    BALANCED = 'balanced'
    DIRECTIONAL = 'directional'

class ContractType(Enum):
    CALL = 'call'
    PUT = 'put'
    
class Options:
    """Helper class for calculating option expiration dates and fetching option contracts."""
    def __init__(self, r=0.05, sigma=0.2):
        self.r = r  # Risk-free interest rate (5%)
        self.sigma = sigma  # Implied volatility (20%)

    @staticmethod
    def get_third_friday_of_month(year, month):
        """Calculates the date of the third Friday of a given month and year."""
        c = calendar.Calendar(firstweekday=calendar.SUNDAY)
        monthcal = c.monthdatescalendar(year, month)
        third_friday = [day for week in monthcal for day in week if
                        day.weekday() == calendar.FRIDAY and
                        day.month == month][2]
        return third_friday

    @staticmethod
    def get_next_friday(date: datetime.date):
        """Calculates the date of the next Friday after a given date."""
        days_ahead = 4 - date.weekday()  # Friday is the 4th day of the week (0-indexed)
        if days_ahead <= 0:  # Target day already passed this week
            days_ahead += 7
        next_friday = date + timedelta(days_ahead)
        return next_friday

    @staticmethod
    def get_third_friday_of_current_month():
        """Calculates the date of the third Friday of the current month."""
        today = datetime.today().date()
        year = today.year
        month = today.month
        return Options.get_third_friday_of_month(year, month)

    @staticmethod
    def get_following_third_friday():
        """Calculates the date of the third Friday of the next month."""
        today = datetime.today().date()
        year = today.year
        month = today.month + 1
        return Options.get_third_friday_of_month(year, month)
    
    def black_scholes_call(self, S, K, T):
        """
        Calculate the Black-Scholes call option price.
        
        Parameters:
        S : float : Current stock price
        K : float : Strike price
        T : float : Time to expiration in years
        
        Returns:
        float : Call option price
        """
        d1 = (np.log(S / K) + (self.r + 0.5 * self.sigma ** 2) * T) / (self.sigma * np.sqrt(T))
        d2 = d1 - self.sigma * np.sqrt(T)
        call_price = S * norm.cdf(d1) - K * np.exp(-self.r * T) * norm.cdf(d2)
        return call_price

    def black_scholes_put(self, S, K, T,):
        """
        Calculate the Black-Scholes put option price.
        
        Parameters:
        S : float : Current stock price
        K : float : Strike price
        T : float : Time to expiration in years
        
        Returns:
        float : Put option price
        """
        d1 = (np.log(S / K) + (self.r + 0.5 * self.sigma ** 2) * T) / (self.sigma * np.sqrt(T))
        d2 = d1 - self.sigma * np.sqrt(T)
        put_price = K * np.exp(-self.r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        return put_price

    @staticmethod
    def calculate_probability_of_profit(current_price: Decimal, breakeven_price: Decimal, days_to_expiration: int, implied_volatility: Decimal) -> Decimal:
        """
        Calculate the Probability of Profit (POP) for an option position.
        
        Parameters:
        current_price : Decimal : Current price of the underlying asset
        breakeven_price : Decimal : Breakeven price of the option position
        days_to_expiration : int : Number of days until the option expires
        implied_volatility : Decimal : Implied volatility of the underlying asset
        
        Returns:
        Decimal : Probability of Profit (POP) as a percentage
        """
        # Calculate standard deviation for the underlying asset price
        annualized_sd = implied_volatility * current_price
        daily_sd = annualized_sd / Decimal(np.sqrt(252))  # 252 trading days in a year
        price_movement_sd = daily_sd * Decimal(np.sqrt(days_to_expiration))

        # Calculate Z-Score for Breakeven
        z_score = (breakeven_price - current_price) / price_movement_sd

        # Calculate Probability of Profit (POP)
        probability_of_profit = Decimal(norm.cdf(float(z_score)))

        return probability_of_profit * Decimal(100)

    @staticmethod
    def get_delta_range(trade_strategy: TradeStrategy):
        """
        Provides typical delta ranges for vertical spreads based on the trading strategy.
        
        Parameters:
        trade_strategy : TradeStrategy : The trading strategy (TradeStrategy.HIGH_PROBABILITY, TradeStrategy.BALANCED, TradeStrategy.DIRECTIONAL)
        
        Returns:
        tuple : A tuple containing the lower and upper bounds of the delta range
        """
        if trade_strategy == TradeStrategy.HIGH_PROBABILITY:
            return (Decimal('0.10'), Decimal('0.30'))
        elif trade_strategy == TradeStrategy.BALANCED:
            return (Decimal('0.30'), Decimal('0.50'))
        elif trade_strategy == TradeStrategy.DIRECTIONAL:
            return (Decimal('0.50'), Decimal('0.70'))
        else:
            raise ValueError("Invalid trade strategy. Choose from TradeStrategy.HIGH_PROBABILITY, TradeStrategy.BALANCED, or TradeStrategy.DIRECTIONAL.")

    @staticmethod
    def calculate_standard_deviation(current_price: Decimal, iv: Decimal, days_to_expiration: Decimal) -> Decimal:
        """
        Calculate the standard deviation of the underlying asset.
        
        Parameters:
        current_price : Decimal : Current price of the underlying asset
        iv : Decimal : Implied volatility (expressed as a decimal)
        time_to_expiration : Decimal : Time to expiration in years
        
        Returns:
        Decimal : Standard deviation of the underlying asset
        """
        return Decimal(current_price * iv * Decimal(np.sqrt(Decimal(days_to_expiration/365))))

    @staticmethod
    def identify_strike_price_type(delta: Decimal, trade_strategy: TradeStrategy) -> StrikePriceType:
        """
        Identifies if the contract is ITM, ATM, or OTM based on the delta value and trade strategy.

        Parameters:
        delta : Decimal : The delta value of the option
        trade_strategy : TradeStrategy : The trading strategy

        Returns:
        StrikePriceType : The type of the contract (ITM, ATM, or OTM)
        """
        lower_bound, upper_bound = Options.get_delta_range(trade_strategy)
        if lower_bound <= abs(delta) <= upper_bound:
            return StrikePriceType.ATM
        elif abs(delta) > upper_bound:
            return StrikePriceType.ITM
        else:
            return StrikePriceType.OTM

    @staticmethod
    def get_order(strategy: StrategyType, direction: DirectionType) -> OrderType:
        """Returns the order (ASC/DESC) based on strategy and direction."""
        return {StrategyType.CREDIT: {DirectionType.BULLISH: DESC, DirectionType.BEARISH: ASC}, 
                StrategyType.DEBIT: {DirectionType.BULLISH: ASC, DirectionType.BEARISH: DESC}}[strategy][direction]

    @staticmethod
    def get_search_op(strategy, direction):
        """Returns the search operator (operator.ge or operator.le) based on strategy and direction.""" 
        return {StrategyType.CREDIT: {DirectionType.BULLISH: operator.ge, DirectionType.BEARISH: operator.le}, 
                StrategyType.DEBIT: {DirectionType.BULLISH: operator.le, DirectionType.BEARISH: operator.ge}}[strategy][direction]

    @staticmethod
    def get_contract_type(strategy: StrategyType, direction: DirectionType) -> ContractType:
        """
        Returns the contract type (CALL or PUT) based on the strategy and direction.

        Parameters:
        strategy : StrategyType : The trading strategy (CREDIT or DEBIT)
        direction : DirectionType : The market direction (BULLISH or BEARISH)

        Returns:
        ContractType : The type of the contract (CALL or PUT)
        """
        if strategy == StrategyType.CREDIT:
            return ContractType.CALL if direction == DirectionType.BEARISH else ContractType.PUT
        elif strategy == StrategyType.DEBIT:
            return ContractType.PUT if direction == DirectionType.BEARISH else ContractType.CALL
        else:
            raise ValueError("Invalid strategy or direction.")

    @staticmethod
    def select_contract(
        contracts: List[Contract],  
        market_data_client: IMarketDataClient, 
        underlying_ticker: str,
        trade_strategy: TradeStrategy
    ) -> List[Tuple[Contract, int, Snapshot]]:
        """
        Selects the contracts for the first leg of a vertical spread based on the strategy, direction, and delta value.

        underlying_ticker : str : The ticker symbol of the underlying asset
        trade_strategy : TradeStrategy : The trading strategy (HIGH_PROBABILITY, BALANCED, or DIRECTIONAL)
        contracts : list : List of option contracts
        strategy : StrategyType : The trading strategy (CREDIT or DEBIT)
        direction : DirectionType : The market direction (BULLISH or BEARISH)
        market_data_client : IMarketDataClient : The market data client
        underlying_ticker : str : The ticker symbol of the underlying asset

        Returns:
        list : A list of tuples containing the selected contract, its position in the list, and the snapshot
        """
        matching_contracts = []
        for position, contract in enumerate(contracts):
            try:
                snapshot: Snapshot = Snapshot.from_dict(
                    market_data_client.get_option_snapshot(underlying_ticker=underlying_ticker, option_symbol=contract.ticker)
                )
                if not snapshot.day.timestamp:
                    logger.debug("Snapshot is not up-to-date. Option may not be traded yet.")
                if not all([snapshot.day.close, snapshot.implied_volatility, snapshot.greeks.delta]):
                    logger.debug(f"Missing key data for {contract.ticker}. Skipping.")
                    continue
                strike_price_type = Options.identify_strike_price_type(snapshot.greeks.delta, trade_strategy)
                if (((trade_strategy == TradeStrategy.DIRECTIONAL) 
                     and (strike_price_type == StrikePriceType.ATM))
                     or (trade_strategy == TradeStrategy.HIGH_PROBABILITY
                     and (strike_price_type == StrikePriceType.OTM))): 
                    logger.info(f"Selected contract {contract.ticker} with delta {snapshot.greeks.delta} and strike price type {strike_price_type.value}.")
                    matching_contracts.append((contract, position, snapshot))
            except (MarketDataException, KeyError, TypeError) as e:
                logger.warning(f"Error processing contract {contract.ticker}: {type(e).__name__} - {e}")
                continue

        return matching_contracts
