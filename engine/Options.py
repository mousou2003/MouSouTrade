"""
Options Trading Utilities
=======================
This module provides core functionality for options trading calculations and analysis:

1. Option pricing and probability calculations:
   - Black-Scholes model implementations for calls and puts
   - Probability of profit calculations
   - Standard deviation and risk metrics

2. Option expiration date utilities:
   - Third Friday calculations for standard options
   - Forward date projections

3. Delta-based option selection strategies:
   - HIGH_PROBABILITY: 0.10-0.30 delta for premium collection
   - BALANCED: 0.30-0.45 delta for moderate exposure
   - DIRECTIONAL: 0.45-0.70 delta for directional trades

4. Contract selection and filtering:
   - Strike price identification (ITM/ATM/OTM)
   - Contract type determination based on strategy
   - Orderbook analysis and liquidity checking

5. Vertical spread width utilities:
   - Optimal width calculation based on underlying price
   - Standard width validation
   - Width selection based on market conditions

This module serves as a foundation for the more specific spread strategy implementations
and provides the mathematical models needed for options trading.
"""

import calendar
from datetime import datetime, timedelta
import logging
from typing import Tuple
import numpy as np
from scipy.stats import norm
from decimal import Decimal, Inexact, InvalidOperation
from enum import Enum
from datetime import datetime, timedelta
from marketdata_clients.BaseMarketDataClient import MarketDataException
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

class OrderType(Enum):
    ASC = 'asc'
    DESC = 'desc'
    
class Options:
    """Helper class for calculating option expiration dates and fetching option contracts."""
    def __init__(self, r=0.05, sigma=0.2):
        self.r = r  # Risk-free interest rate (5%)
        self.sigma = sigma  # Implied volatility (20%)

    # Add deep ITM/OTM bounds as class constants
    DEEP_ITM_DELTA = Decimal('0.90')  # Deltas above this are too deep ITM
    DEEP_OTM_DELTA = Decimal('0.10')  # Deltas below this are too deep OTM

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
    def calculate_probability_of_profit(current_price: Decimal, breakeven_price: Decimal, 
                                      days_to_expiration: int, implied_volatility: Decimal,
                                      is_debit_spread: bool = False) -> Decimal:
        """Calculate probability of profit based on price, implied volatility, and time to expiration."""
        try:
            # Ensure inputs are valid
            if days_to_expiration <= 0:
                logger.warning(f"Invalid days_to_expiration: {days_to_expiration}. Using default of 30.")
                days_to_expiration = 30
                
            if implied_volatility <= Decimal('0'):
                logger.warning(f"Invalid implied_volatility: {implied_volatility}. Using default of 0.3.")
                implied_volatility = Decimal('0.3')
            
            price_diff_pct = abs((breakeven_price - current_price) / current_price) * Decimal('100')
            
            # Calculate std_deviations same for both types
            time_factor = Decimal(days_to_expiration) / Decimal('365')
            annual_stddev_pct = implied_volatility * Decimal('100')
            period_stddev_pct = annual_stddev_pct * time_factor.sqrt()
            
            std_deviations = price_diff_pct / period_stddev_pct if period_stddev_pct != Decimal('0') else Decimal('0.5')
            
            # Use same base probability calculation for both types
            if std_deviations <= Decimal('0.25'):
                base_probability = Decimal('40') + (std_deviations * Decimal('40'))  # 40-50% range
            elif std_deviations <= Decimal('0.75'):
                base_probability = Decimal('50') + ((std_deviations - Decimal('0.25')) * Decimal('20'))  # 50-60% range
            elif std_deviations <= Decimal('1.5'):
                base_probability = Decimal('60') + ((std_deviations - Decimal('0.75')) * Decimal('15'))  # 60-71.25% range
            elif std_deviations <= Decimal('2.5'):
                base_probability = Decimal('71.25') + ((std_deviations - Decimal('1.5')) * Decimal('7.5'))  # 71.25-78.75% range
            else:
                base_probability = Decimal('78.75') + ((std_deviations - Decimal('2.5')) * Decimal('4.5'))

            # Apply smaller time adjustments
            time_factor_adjustment = Decimal('0')
            if days_to_expiration < 14:
                time_factor_adjustment = Decimal('3')  # +3% for short duration
            elif days_to_expiration > 60:
                time_factor_adjustment = Decimal('-3')  # -3% for long duration

            result = base_probability + time_factor_adjustment

            # Cap probabilities based on strategy
            if is_debit_spread:
                result = min(result, Decimal('65'))  # Allow slightly higher for debit spreads
            else:
                result = min(result, Decimal('85'))  # Cap credit spreads higher

            return result
                
        except Exception as e:
            logger.error(f"Error calculating probability of profit: {str(e)}")
            return Decimal('50')  # Return middle probability as default

    @staticmethod
    def get_delta_range(strategy: TradeStrategy) -> Tuple[Decimal, Decimal]:
        """Get appropriate delta range based on trade strategy.
        
        Delta ranges:
        - DIRECTIONAL: Higher delta for ATM/ITM options (0.40-0.70)
        - HIGH_PROBABILITY: Lower delta for OTM options (0.20-0.35)
        
        Returns:
            Tuple[Decimal, Decimal]: (lower_bound, upper_bound) for delta values
        """
        if strategy == TradeStrategy.DIRECTIONAL:
            return (Decimal('0.40'), Decimal('0.70'))
        else:  # HIGH_PROBABILITY
            return (Decimal('0.20'), Decimal('0.35'))

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
        sqrt_result = Decimal(str(np.sqrt(float(days_to_expiration/Decimal('365')))))
        return current_price * iv * sqrt_result

    @staticmethod
    def identify_strike_price_type_by_delta(delta: Decimal, trade_strategy: TradeStrategy) -> StrikePriceType:
        """Identify strike price type based on delta value and trade strategy."""
        abs_delta = abs(delta)
        if abs_delta >= Options.DEEP_ITM_DELTA:
            return StrikePriceType.EXCLUDED  # Too deep ITM
        if abs_delta <= Options.DEEP_OTM_DELTA:
            return StrikePriceType.EXCLUDED  # Too deep OTM

        lower_bound, upper_bound = Options.get_delta_range(trade_strategy)
        
        if lower_bound <= abs_delta <= upper_bound:
            if abs_delta >= Decimal('0.45'):
                return StrikePriceType.ATM
            else:
                return StrikePriceType.OTM
        elif abs_delta > upper_bound:
            return StrikePriceType.ITM  # Higher delta than upper bound = ITM
        
        return StrikePriceType.EXCLUDED

    @staticmethod
    def identify_strike_price_by_current_price(strike_price: Decimal, current_price: Decimal, contract_type: ContractType, threshold: Decimal = Decimal('0.02')) -> StrikePriceType:
        """
        Identifies if a strike price is ITM, ATM, or OTM based on its relationship to the current price.
        
        Parameters:
        strike_price : Decimal : The strike price of the option
        current_price : Decimal : The current price of the underlying asset
        contract_type : ContractType : The type of the contract (CALL or PUT)
        threshold : Decimal : The price threshold (as percentage) for considering a strike price ATM
        
        Returns:
        StrikePriceType : The type of the strike price (ITM, ATM, or OTM)
        """
        percent_diff = abs(strike_price - current_price) / current_price
        
        if percent_diff <= threshold:
            return StrikePriceType.ATM
        
        if contract_type.value == ContractType.CALL.value:
            return StrikePriceType.ITM if strike_price < current_price else StrikePriceType.OTM
        else:  # PUT
            return StrikePriceType.ITM if strike_price > current_price else StrikePriceType.OTM

    @staticmethod
    def calculate_optimal_spread_width(current_price: Decimal, strategy: StrategyType, direction: DirectionType) -> Decimal:
        """Calculate optimal spread width based on price and strategy."""
        
        base_width = current_price * Decimal('0.05')
        
        if strategy == StrategyType.CREDIT:
            if direction == DirectionType.BULLISH:
                width = base_width * Decimal('1.2') 
            else:
                width = base_width * Decimal('0.8')
        else:  # DEBIT
            if direction == DirectionType.BULLISH:
                width = base_width * Decimal('1.2')
            else:
                width = base_width * Decimal('0.8')
        
        return Options.round_to_standard_width(width)

    @staticmethod 
    def get_width_config(current_price: Decimal, strategy: StrategyType, direction: DirectionType) -> Tuple[Decimal, Decimal, Decimal]:
        """Get min, max and optimal width configuration."""
        
        min_width = current_price * Decimal('0.025')  # 2.5%
        max_width = current_price * Decimal('0.15')   # 15%
        
        optimal_width = Options.calculate_optimal_spread_width(current_price, strategy, direction)
        
        min_width = Options.round_to_standard_width(min_width)
        max_width = Options.round_to_standard_width(max_width)
        
        return min_width, max_width, optimal_width

    @staticmethod
    def is_standard_width(width: Decimal) -> bool:
        """
        Check if a spread width is a standard width used in options markets.
        Standard widths improve liquidity and ease of execution.
        
        Parameters:
        width : Decimal : The spread width to check
        
        Returns:
        bool : True if the width is standard, False otherwise
        """
        standard_widths = [Decimal('1'), Decimal('2.5'), Decimal('5'), 
                          Decimal('10'), Decimal('25'), Decimal('50')]
        return width in standard_widths

    @staticmethod
    def get_order(strategy: StrategyType, direction: DirectionType) -> OrderType:
        """Returns the order (ASC/DESC) based on strategy and direction."""
        return {StrategyType.CREDIT: {DirectionType.BULLISH: OrderType.DESC, DirectionType.BEARISH: OrderType.ASC}, 
                StrategyType.DEBIT: {DirectionType.BULLISH: OrderType.ASC, DirectionType.BEARISH: OrderType.DESC}}[strategy][direction]

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
    def round_to_standard_width(width: Decimal) -> Decimal:
        """
        Round a spread width to the nearest standard width.
        
        Standard widths are increments commonly used in options markets:
        - 1.0 point: For stocks under $25
        - 2.5 points: For stocks $25-$75
        - 5.0 points: For stocks $75-$150
        - 10.0 points: For stocks $150-$500
        - 25.0 points: For stocks $500+ or index options
        
        Parameters:
        width : Decimal : The spread width to round
        
        Returns:
        Decimal : The nearest standard width
        """
        standard_widths = [Decimal('1'), Decimal('2.5'), Decimal('5'), 
                          Decimal('10'), Decimal('25'), Decimal('50')]
        
        if width <= 0:
            return Decimal('1')  # Minimum standard width
            
        return min(standard_widths, key=lambda x: abs(x - width))
