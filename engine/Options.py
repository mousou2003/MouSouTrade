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
                                        days_to_expiration: int, implied_volatility: Decimal) -> Decimal:
        """
        Calculate probability of profit based on price, implied volatility, and time to expiration.
        
        Args:
            current_price: Current price of the underlying
            breakeven_price: Breakeven price for the trade
            days_to_expiration: Days until option expiration
            implied_volatility: IV as a decimal (e.g., 0.30 for 30%)
            
        Returns:
            Probability of profit as a percentage (0-100)
        """
        try:
            # Ensure inputs are valid
            if days_to_expiration <= 0:
                logger.warning(f"Invalid days_to_expiration: {days_to_expiration}. Using default of 30.")
                days_to_expiration = 30
                
            # Sanity checks for implied_volatility - keep the check for zero/negative
            if implied_volatility <= Decimal('0'):
                logger.warning(f"Invalid implied_volatility: {implied_volatility}. Using default of 0.3.")
                implied_volatility = Decimal('0.3')
            
            # For debit spreads, we need to factor in the fact that price needs to move favorably
            # For credit spreads, we benefit from time decay and need price to stay within a range
            
            # Calculate distance to breakeven as a percentage of current price
            price_diff_pct = abs((breakeven_price - current_price) / current_price) * Decimal('100')
            
            # Calculate standard deviation move based on IV and time
            time_factor = Decimal(days_to_expiration) / Decimal('365')
            annual_stddev_pct = implied_volatility * Decimal('100')  # Convert to percentage
            period_stddev_pct = annual_stddev_pct * time_factor.sqrt()
            
            # Calculate number of standard deviations to breakeven
            if period_stddev_pct == Decimal('0'):
                # Fallback if stddev calculation fails
                std_deviations = Decimal('0.5')  # Default value
                logger.warning(f"Standard deviation calculation resulted in zero. Using default of {std_deviations} std deviations.")
            else:
                std_deviations = price_diff_pct / period_stddev_pct
            
            logger.debug(f"Price diff: {price_diff_pct:.2f}%, Period StdDev: {period_stddev_pct:.2f}%, "
                       f"Std deviations to breakeven: {std_deviations:.2f}")
            
            # Apply a more relaxed model for the probability calculation without capping
            # NOTE: This can result in very high probability values for deep OTM options
            
            # The closer the breakeven is (fewer std deviations away), the lower the probability of profit
            if std_deviations <= Decimal('0.25'):
                # Very close to breakeven (high risk)
                base_probability = Decimal('50') + (std_deviations * Decimal('40'))  # 50-60% range
            elif std_deviations <= Decimal('0.75'):
                # Moderately close to breakeven
                base_probability = Decimal('60') + ((std_deviations - Decimal('0.25')) * Decimal('20'))  # 60-70% range
            elif std_deviations <= Decimal('1.5'):
                # Reasonable distance from breakeven
                base_probability = Decimal('70') + ((std_deviations - Decimal('0.75')) * Decimal('15'))  # 70-81.25% range
            elif std_deviations <= Decimal('2.5'):
                # Far from breakeven
                base_probability = Decimal('81.25') + ((std_deviations - Decimal('1.5')) * Decimal('7.5'))  # 81.25-88.75% range
            else:
                # Very far from breakeven (low risk)
                # Continue the progression without capping
                base_probability = Decimal('88.75') + ((std_deviations - Decimal('2.5')) * Decimal('4.5'))
            
            # Apply additional factors based on days to expiration
            time_factor_adjustment = Decimal('0')
            
            if days_to_expiration < 14:  # Very short-dated
                time_factor_adjustment = Decimal('5')  # +5% for short duration
            elif days_to_expiration > 60:  # Longer-dated
                time_factor_adjustment = Decimal('-5')  # -5% for long duration
            
            # Final probability calculation
            result = base_probability + time_factor_adjustment
            
            # Log the calculation details
            logger.debug(f"POP calculation: Base={base_probability}, Time adjustment={time_factor_adjustment}, Final={result}")
            
            # Log unusually high or low values but don't cap them
            if result < Decimal('30'):
                logger.warning(f"Unusually low probability calculated: {result}%")
            elif result > Decimal('95'):
                logger.warning(f"Unusually high probability calculated: {result}%")
            
            return result
                
        except Exception as e:
            logger.error(f"Error calculating probability of profit: {str(e)}")
            # Return a reasonable default based on typical option strategies
            return Decimal('60')

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
        # Make sure to convert the result of np.sqrt to Decimal
        sqrt_result = Decimal(str(np.sqrt(float(days_to_expiration/Decimal('365')))))
        return current_price * iv * sqrt_result

    @staticmethod
    def identify_strike_price_type_by_delta(delta: Decimal, trade_strategy: TradeStrategy) -> StrikePriceType:
        """
        Identifies if the contract is ITM, ATM, or OTM based on the delta value and trade strategy.

        Parameters:
        delta : Decimal : The delta value of the option (-1 to 1)
        trade_strategy : TradeStrategy : The trading strategy

        Returns:
        StrikePriceType : The type of the contract (ITM, ATM, or OTM)
        """
        lower_bound, upper_bound = Options.get_delta_range(trade_strategy)
        abs_delta = abs(delta)  # Convert delta to absolute value for comparison
        
        # Use absolute delta values for comparison:
        # Call deltas: 0 to 1 (OTM to ITM)
        # Put deltas: -1 to 0 (ITM to OTM)
        if abs_delta >= upper_bound:
            return StrikePriceType.ITM
        elif abs_delta <= lower_bound:  
            return StrikePriceType.OTM
        else:
            return StrikePriceType.ATM

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
        # Calculate percentage difference from current price
        percent_diff = abs(strike_price - current_price) / current_price
        
        # If within threshold, consider it ATM
        if percent_diff <= threshold:
            return StrikePriceType.ATM
        
        if contract_type.value == ContractType.CALL.value:
            # For calls: strike < current = ITM, strike > current = OTM
            return StrikePriceType.ITM if strike_price < current_price else StrikePriceType.OTM
        else:  # PUT
            # For puts: strike > current = ITM, strike < current = OTM
            return StrikePriceType.ITM if strike_price > current_price else StrikePriceType.OTM

    @staticmethod
    def calculate_optimal_spread_width(current_price: Decimal, strategy: StrategyType, direction: DirectionType) -> Decimal:
        """
        Calculate the optimal spread width based on the underlying price and strategy type.
        Based on industry standard practices for vertical spreads.
        
        Parameters:
        current_price : Decimal : The current price of the underlying asset
        strategy : StrategyType : Strategy type (CREDIT or DEBIT) to optimize width for
        
        Returns:
        Decimal : The recommended spread width
        """
        # First calculate the base width based on stock price
        if current_price < Decimal('50'):
            # Very low-priced stocks: 1-2 point spreads (2-4% of price)
            base_width = Decimal('1')
        elif current_price < Decimal('100'):
            # Low-priced stocks: 2-5 point spreads (2-5% of price)
            base_width = Decimal('2.5')
        elif current_price < Decimal('300'):
            # Mid-priced stocks: 5-10 point spreads (2-5% of price)
            base_width = Decimal('5')
        elif current_price < Decimal('1000'):
            # High-priced stocks: 10-20 point spreads (1-3% of price)
            base_width = Decimal('10')
        else:
            # Very high-priced stocks or indices: 25+ point spreads (≤1% of price)
            base_width = Decimal('25')
        
        # Apply strategy-specific adjustments:
        # - Credit spreads: Often narrower to maximize probability of profit
        # - Debit spreads: Often wider to increase potential return

        if strategy:
            if strategy == StrategyType.CREDIT:
                width_multiplier = Decimal('0.8')
            elif strategy == StrategyType.DEBIT:
                width_multiplier = Decimal('1.2')

        # Adjust for directional bias
        if direction:
            if direction == DirectionType.BULLISH:
                width_multiplier *= Decimal('1.5')  # Wider spread for bullish expectation
            elif direction == DirectionType.BEARISH:
                width_multiplier *= Decimal('1.5')  # Wider spread for bearish expectation
            
        # Apply the multiplier
        adjusted_width = base_width * width_multiplier
        
        # Ensure we still return a standard width
        standard_widths = [Decimal('1'), Decimal('2.5'), Decimal('5'), 
                            Decimal('10'), Decimal('25'), Decimal('50')]
        
        # Find the closest standard width
        closest_width = min(standard_widths, key=lambda x: abs(x - adjusted_width))
        
        return closest_width
        

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
