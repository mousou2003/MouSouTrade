"""
Vertical Spread Implementation
============================
This module implements both debit and credit vertical option spreads. It provides functionality to:

1. Select appropriate option contracts based on:
   - Trading direction (bullish/bearish)
   - Strategy type (credit/debit)
   - Delta values for optimal strike selection
   - Expiration dates

2. Calculate key spread metrics:
   - Net premium (credit received or debit paid)
   - Max profit and max risk
   - Probability of profit (POP)
   - Break-even prices
   - Target and stop prices for trade management

3. Generate detailed descriptions and serializations of spreads

The module implements two main vertical spread types:
- DebitSpread: For directional exposure (bull call or bear put spreads)
- CreditSpread: For premium collection (bull put or bear call spreads)

It uses the Options module for option selection logic and implements the SpreadDataModel interface
for consistent data representation across the application.
"""
""" 

# Vertical Spread Width in Real Trading Scenarios

In real-world options trading, vertical spread widths are chosen strategically based on several factors. Here's a detailed breakdown:

### Typical Spread Widths

1. **Small Spreads (1-5 points)**
   - **Common for:** Lower-priced stocks ($20-100)
   - **Applications:** Weekly or short-term (30-day) strategies
   - **Example:** For a $50 stock, a 2-point spread (e.g., 49/51 or 48/50) represents 4% of the underlying price
   - **Advantages:** Lower capital requirement, precise strikes around technical levels

2. **Medium Spreads (5-10 points)**
   - **Common for:** Mid-priced stocks ($100-300)
   - **Applications:** Monthly expirations (30-45 days)
   - **Example:** For a $150 stock, a 7.5-point spread (147.5/155) represents 5% of the underlying
   - **Advantages:** Balance between risk/reward and capital efficiency

3. **Wide Spreads (10-20+ points)**
   - **Common for:** High-priced stocks (>$300) or index options
   - **Applications:** Longer-term positions or higher conviction trades
   - **Example:** For SPX at 4000, a 20-point spread (3980/4000) is only 0.5% of the underlying
   - **Advantages:** Higher potential absolute profit, better commission efficiency

### General Guidelines by Market Professionals

1. **Percentage of Underlying Price:**
   - Typically ranges from 2% to 10% of the underlying's price
   - More liquid stocks tend toward the lower end (2-5%)
   - Less liquid stocks may require wider spreads (7-10%)

2. **Based on Implied Volatility (IV):**
   - Higher IV environments → wider spreads (to capture premium)
   - Lower IV environments → narrower spreads (for precision)

3. **Based on Strategy:**
   - **Credit spreads:** Often narrower to maximize probability of profit
   - **Debit spreads:** Often wider to increase potential return

4. **Risk Management Factors:**
   - Maximum acceptable loss (wider spreads = more capital at risk)
   - Reward-to-risk ratio target (typically 1:1 to 3:1)
   - Probability of profit target (higher with narrower spreads)

### Common Width Selection Methods

1. **Strike Liquidity Method:**
   - Choose the most liquid strikes available (highest open interest/volume)
   - Often results in round-number strikes (e.g., 100/105 rather than 102/107)

2. **Delta-Based Method:**
   - First leg: Select by target delta (e.g., 0.30 for credit spreads)
   - Second leg: Select by target delta spacing (e.g., 0.15-0.20 delta away)

3. **Technical Analysis Method:**
   - Choose strikes based on support/resistance levels
   - Often creates non-standard width spreads

4. **Standard Width Method:**
   - Use exchange-standard widths (e.g., 5-point spreads for stocks over $100)
   - Maximizes liquidity and ease of execution

### Real-World Examples

- **SPY ($420):** 5-point spreads (1.2% of underlying) are standard
- **AAPL ($175):** 5-point spreads (2.9% of underlying) are common
- **AMZN ($130):** 2.5 or 5-point spreads (2-4% of underlying)
- **TSLA ($250):** 10-point spreads (4% of underlying)
- **SPX ($4200):** 25-50 point spreads (0.6-1.2% of underlying)

In professional trading environments, spread width is often standardized by asset class to simplify risk management across portfolios. """

import operator
from tracemalloc import Snapshot
from engine.data_model import *
from engine.Options import Options, TradeStrategy
from engine.contract_selector import ContractSelector, StandardContractSelector
import logging
from datetime import datetime, timedelta
from typing import ClassVar, Optional, List, Tuple, Dict, TYPE_CHECKING
from decimal import Decimal, getcontext

logger = logging.getLogger(__name__)

class VerticalSpread(SpreadDataModel):
    """
    Vertical Spread Base Implementation
    =================================
    Handles the core logic for vertical option spreads. Each spread consists of:
    1. Two legs with same expiration but different strikes
    2. One long position and one short position
    3. Width between strikes that scales with underlying price

    Spread Width Logic:
    ------------------
    - Minimum width: 2.5% of underlying price
      Example: $100 stock -> min width = $2.50
              $200 stock -> min width = $5.00
    
    - Maximum width: 15% of underlying price
      Example: $100 stock -> max width = $15.00
              $200 stock -> max width = $30.00
    
    - Optimal width: 5% of underlying price (balances risk/reward)
      Example: $100 stock -> optimal = $5.00
              $200 stock -> optimal = $10.00

    Validation Mathematics:
    ---------------------
    1. Premium Validation:
       - Credit spreads: short_premium > long_premium (net credit)
       - Debit spreads: long_premium > short_premium (net debit)
       
    2. Width Validation:
       width_percent = (strike_distance / stock_price) * 100
       2.5% <= width_percent <= 15%
       
    3. Risk/Reward Metrics:
       - Credit Spreads:
         Max Reward = net_credit * 100
         Max Risk = (width - net_credit) * 100
         
       - Debit Spreads:
         Max Reward = (width - net_debit) * 100
         Max Risk = net_debit * 100
         
    4. Reward/Risk Ratio:
       target_ratio = 2.0 (minimum acceptable)
       actual_ratio = max_reward / max_risk
       
    5. Position Sizing:
       max_loss_percent = max_risk / (stock_price * 100)
       Must be <= 5% of account
       
    Width Ratios by Strategy and Direction:
    ------------------------------------
    CREDIT Spreads:
    - Bull Put: Wider spreads (3-15%) - More room for price appreciation
    - Bear Call: Narrower spreads (2.5-10%) - Tighter control on risk
    
    DEBIT Spreads:
    - Bull Call: Wider spreads (3-15%) - Capture upside movement
    - Bear Put: Narrower spreads (2.5-10%) - Precise entry/exit points
    """
    MAX_STRIKES: ClassVar[int] = 20  # Maximum number of strikes to consider
    
    # Constants for scoring calculations
    TARGET_REWARD_RISK_RATIO: ClassVar[Decimal] = Decimal('2.0')  # Target 2:1 reward-to-risk ratio
    MAX_ACCEPTABLE_LOSS_PERCENT: ClassVar[Decimal] = Decimal('0.05')  # 5% of account per trade
    # Minimum liquidity thresholds
    MIN_ACCEPTABLE_VOLUME: ClassVar[int] = 10  # Minimum acceptable volume
    MIN_ACCEPTABLE_OI: ClassVar[int] = 25  # Minimum acceptable open interest
    OI_EXCELLENT_THRESHOLD: ClassVar[int] = 500  # Threshold for excellent open interest
    VOLUME_EXCELLENT_THRESHOLD: ClassVar[int] = 200  # Threshold for excellent volume
    LONG_TERM_THRESHOLD: ClassVar[int] = 30  # Threshold for long-term options
    CONFIDENCE_REDUCTION_FACTOR: ClassVar[Decimal] = Decimal('0.7')  # Confidence reduction factor
    LARGE_MOVE_THRESHOLD: ClassVar[Decimal] = Decimal('0.1')  # Threshold for large price moves
    MAX_CONFIDENCE_REDUCTION: ClassVar[Decimal] = Decimal('0.5')  # Maximum confidence reduction
    CONFIDENCE_REDUCTION_STEP: ClassVar[Decimal] = Decimal('0.1')  # Step for confidence reduction

    # Replace single EXTREME_WIDTH_RATIO with specific ratios
    EXTREME_WIDTH_RATIO_DEBIT: ClassVar[Decimal] = Decimal('4.0')  # More conservative for debit spreads
    EXTREME_WIDTH_RATIO_CREDIT: ClassVar[Decimal] = Decimal('6.0')  # More flexible for credit spreads
    EXTREME_WIDTH_RATIO_HIGH_VOL: ClassVar[Decimal] = Decimal('3.0')  # More conservative in high volatility
    EXTREME_WIDTH_RATIO_LOW_VOL: ClassVar[Decimal] = Decimal('7.0')  # More flexible in low volatility
    VOL_THRESHOLD_HIGH: ClassVar[Decimal] = Decimal('0.3')  # 30% IV threshold for high volatility
    VOL_THRESHOLD_LOW: ClassVar[Decimal] = Decimal('0.15')  # 15% IV threshold for low volatility

    # Add these class constants
    MIN_SPREAD_WIDTH_PERCENT: ClassVar[Decimal] = Decimal('0.025')  # 2.5% of underlying price
    MAX_SPREAD_WIDTH_PERCENT: ClassVar[Decimal] = Decimal('0.15')  # 15% of underlying price
    OPTIMAL_SPREAD_WIDTH_PERCENT: ClassVar[Decimal] = Decimal('0.05')  # 5% of underlying price

    # Add back the MIN_RATIO constants
    MIN_RATIO_PREMIUM_TO_DISTANCE: ClassVar[Decimal] = Decimal('0.26')  # Lowered base minimum delta
    MIN_RATIO_PREMIUM_TO_DISTANCE_HIGH_PRICE: ClassVar[Decimal] = Decimal('0.30')  # For stocks > $100
    MIN_RATIO_PREMIUM_TO_DISTANCE_MID_PRICE: ClassVar[Decimal] = Decimal('0.26')   # For stocks $50-$100
    MIN_RATIO_PREMIUM_TO_DISTANCE_LOW_PRICE: ClassVar[Decimal] = Decimal('0.22')   # For stocks < $50

    contracts: List[Contract] = []
    # Make contract_selector an instance attribute instead of ClassVar
    contract_selector: ContractSelector = StandardContractSelector()
    
    # Remove WIDTH_CONFIG as we'll use Options.py methods instead

    @staticmethod
    def get_width_config(strategy: StrategyType, direction: DirectionType) -> dict:
        """Get width configuration based on strategy and direction."""
        min_width, max_width, optimal_width = Options.get_width_config(
            current_price=self.previous_close,
            strategy=strategy,
            direction=direction
        )
        return {
            'min_width_pct': min_width / self.previous_close,
            'max_width_pct': max_width / self.previous_close,
            'optimal_width_pct': optimal_width / self.previous_close
        }

    @staticmethod
    def get_minimum_spread_width(stock_price: Decimal, strategy: StrategyType, direction: DirectionType) -> Decimal:
        """Calculate minimum spread width based on strategy, direction and stock price."""
        min_width, _, _ = Options.get_width_config(stock_price, strategy, direction)
        return min_width

    @staticmethod
    def get_maximum_spread_width(stock_price: Decimal, strategy: StrategyType, direction: DirectionType) -> Decimal:
        """Calculate maximum spread width based on strategy, direction and stock price."""
        _, max_width, _ = Options.get_width_config(stock_price, strategy, direction)
        return max_width

    @staticmethod
    def get_optimal_spread_width(stock_price: Decimal, strategy: StrategyType, direction: DirectionType) -> Decimal:
        """Calculate optimal spread width based on strategy, direction and stock price."""
        return Options.calculate_optimal_spread_width(stock_price, strategy, direction)

    def get_net_premium():
        pass

    def calculate_net_premium(self) -> Decimal:
        """Calculate net premium based on actual prices or snapshot values."""
        logger.debug("Calculating net premium")
        
        if (self.short_contract and self.short_contract.actual_entry_price and 
            self.long_contract and self.long_contract.actual_entry_price):
            # Use actual entry prices if available
            short_price = self.short_contract.actual_entry_price
            long_price = self.long_contract.actual_entry_price
            logger.debug("Using actual contract prices")
        elif (self.first_leg_snapshot and self.first_leg_snapshot.day and 
              self.second_leg_snapshot and self.second_leg_snapshot.day):
            # Use snapshot values
            if self.strategy == StrategyType.CREDIT:
                short_price = self.first_leg_snapshot.day.bid
                long_price = self.second_leg_snapshot.day.ask
            else:  # DEBIT
                short_price = self.second_leg_snapshot.day.bid
                long_price = self.first_leg_snapshot.day.ask
            logger.debug("Using snapshot prices")
        else:
            logger.warning("No valid prices available for net premium calculation")
            return Decimal('0')
            
        net = short_price - long_price
        logger.debug(f"Calculated net premium: {net}")
        return net
        
    def validate_net_premium(self) -> bool:
        """Base method for calculating net premium - to be implemented by subclasses"""
        
        # Validate we have both snapshots with day data
        if not (self.first_leg_snapshot and self.second_leg_snapshot and 
                self.first_leg_snapshot.day and self.second_leg_snapshot.day):
            logger.warning("Missing snapshot data")
            return False
            
        return True
    
    def get_expiration_date(self):
        logger.debug("Entering get_expiration_date")
        result = self.expiration_date
        logger.debug("Exiting get_expiration_date")
        return result

    def get_exit_date(self):
        logger.debug("Entering get_exit_date")
        result = self.get_expiration_date() - timedelta(days=21)
        logger.debug("Exiting get_exit_date")
        return result

    def get_description(self):
        logger.debug("Entering get_description")
        result = self.description
        logger.debug("Exiting get_description")
        return result

    def copy(self) -> 'VerticalSpread':
        """Create a complete deep copy of the vertical spread."""
        logger.debug("Creating deep copy of vertical spread")
        
        try:
            # First, create a copy using parent's copy method
            new_spread:VerticalSpread = super().model_copy()
            
            # Get all attributes from SpreadDataModel (parent class)
            parent_attrs = set(SpreadDataModel.__annotations__.keys())
            
            # Deep copy all attributes based on their type
            for attr_name in parent_attrs:
                if hasattr(self, attr_name):
                    value = getattr(self, attr_name)
                    if value is not None:
                        if isinstance(value, (Contract, Snapshot)):
                            # Deep copy Contract and Snapshot objects
                            setattr(new_spread, attr_name, value.__class__().from_dict(value.to_dict()))
                        elif isinstance(value, list) and value and isinstance(value[0], DayData):
                            # Deep copy lists of DayData
                            setattr(new_spread, attr_name, [DayData().from_dict(x.to_dict()) for x in value])
                        else:
                            # Direct copy for primitive types
                            setattr(new_spread, attr_name, value)
            
            # Set instance-specific contract_selector
            new_spread.contract_selector = self.contract_selector
            
            logger.debug(f"Created deep copy of {self.__class__.__name__}")
            return new_spread
            
        except Exception as e:
            logger.error(f"Error creating vertical spread copy: {str(e)}")
            raise

    def update_snapshots(self, snapshots: dict) -> None:
        """Update spread snapshots with latest market data."""
        if self.first_leg_contract and self.first_leg_contract.ticker in snapshots:
            self.first_leg_snapshot = snapshots[self.first_leg_contract.ticker]
        if self.second_leg_contract and self.second_leg_contract.ticker in snapshots:
            self.second_leg_snapshot = snapshots[self.second_leg_contract.ticker]

    @staticmethod
    def get_current_profit(spread: SpreadDataModel) -> Decimal:
        """Calculate current profit/loss for a spread."""
        if not spread.stock or not spread.actual_entry_price:
            return Decimal('0')
        
        # For completed trades, calculate P&L from actual contract prices
        if spread.agent_status == TradeState.COMPLETED:
            # Use actual entry prices
            entry_net = abs(spread.short_contract.actual_entry_price - spread.long_contract.actual_entry_price)
            # Use snapshot prices for exit to simulate market prices
            if spread.strategy == StrategyType.CREDIT:
                exit_net = abs(spread.first_leg_snapshot.day.ask - spread.second_leg_snapshot.day.bid)
                pnl = (entry_net - exit_net) * 100  # Credit spread: want to exit for less than collected
            else:  # DEBIT
                exit_net = abs(spread.first_leg_snapshot.day.bid - spread.second_leg_snapshot.day.ask)
                pnl = (exit_net - entry_net) * 100  # Debit spread: want to exit for more than paid
            return pnl

        # For active trades, calculate based on current market price
        current_price = spread.stock.close
        if spread.strategy == StrategyType.CREDIT:
            net_premium = abs(spread.first_leg_snapshot.day.bid - spread.second_leg_snapshot.day.ask) * 100
            pnl = net_premium - abs(spread.actual_entry_price - current_price)
        else:  # DEBIT
            net_premium = abs(spread.first_leg_snapshot.day.bid - spread.second_leg_snapshot.day.ask) * 100
            pnl = abs(current_price - spread.actual_entry_price) - net_premium
        
        # Ensure we don't exceed max profit/loss bounds
        target_stop = spread.target_stop if spread.target_stop is not None else (spread.max_risk * Decimal('0.5'))
        target_reward = spread.target_reward if spread.target_reward is not None else (spread.max_reward * Decimal('0.8'))
        
        return max(-target_stop, min(target_reward, pnl))

    def _validate_spread_parameters(self) -> bool:
        """Validate spread parameters against essential criteria."""
        logger.debug("Validating spread parameters")
        
        if self.distance_between_strikes == Decimal('0'):
            logger.error("Invalid spread width of zero. It is maybe because of the the width is out of range.")
            return False
        
        # Basic premium validation
        if self.short_premium is None or self.long_premium is None:
            logger.error("Missing premium values")
            return False

        # Premium relationship validation
        if self.strategy == StrategyType.CREDIT:
            if self.short_premium <= self.long_premium:
                logger.error(f"Invalid credit spread premium: short ({self.short_premium}) <= long ({self.long_premium})")
                return False
        else:  # DEBIT
            if self.long_premium <= self.short_premium:
                logger.error(f"Invalid debit spread premium: long ({self.long_premium}) <= short ({self.short_premium})")
                return False

        # Width validation
        if self.distance_between_strikes <= 0:
            logger.error("Invalid spread width")
            return False

        # Get width boundaries from Options.py
        min_width, max_width, _ = Options.get_width_config(
            self.previous_close, 
            self.strategy, 
            self.direction
        )

        # Validate width is within acceptable range
        if not (min_width <= self.distance_between_strikes <= max_width):
            logger.debug(f"Spread width {self.distance_between_strikes} outside range [{min_width}, {max_width}]")
            return False

        # Verify it's a standard width
        if not Options.is_standard_width(self.distance_between_strikes):
            logger.warning(f"Non-standard spread width: {self.distance_between_strikes}")
            return False

        logger.debug("Spread parameters validated successfully")
        return True

    def _calculate_spread_metrics(self, days_to_expiration: int) -> bool:
        """Calculate spread metrics with the given days to expiration."""
        logger.debug("Entering _calculate_spread_metrics")
        
        if self.net_premium == 0:
            logger.warning("Net premium is zero, spread calculation failed")
            return False
            
        if self.distance_between_strikes == 0:
            logger.warning("Strike distance is zero, invalid spread")
            return False
        
        # Get price-adjusted minimum delta with stricter rules for credit spreads
        min_delta = self.MIN_RATIO_PREMIUM_TO_DISTANCE  # Start with base minimum
        if self.previous_close >= Decimal('100.0'):
            min_delta = self.MIN_RATIO_PREMIUM_TO_DISTANCE_HIGH_PRICE
        elif self.previous_close >= Decimal('50.0'):
            min_delta = self.MIN_RATIO_PREMIUM_TO_DISTANCE_MID_PRICE
        else:
            min_delta = self.MIN_RATIO_PREMIUM_TO_DISTANCE_LOW_PRICE
            
        # Normalize relative delta calculation
        normalized_premium_to_distance_between_strikes = abs(self.net_premium) / abs(self.distance_between_strikes)
        logger.debug(f"Normalized premium ratio: {normalized_premium_to_distance_between_strikes}")
        logger.debug(f"Minimum required delta: {min_delta}")
        
        if normalized_premium_to_distance_between_strikes < min_delta:
            logger.debug(f"Premium ratio {normalized_premium_to_distance_between_strikes} below minimum {min_delta}")
            return False
            
        # Calculate all other metrics - these handle negative net premium correctly already
        self.max_reward = self.get_max_reward()
        self.max_risk = self.get_max_risk()
        self.breakeven = self.get_breakeven_price()
        self.target_price = self.get_target_price()
        self.stop_price = self.get_stop_price()
        
        # Calculate optimal profit and loss
        contracts = Decimal('100')  # Standard contract size
        if self.strategy == StrategyType.CREDIT:
            # Credit spread optimal scenarios
            self.optimal_profit = self.net_premium * contracts  # Max profit at target
            self.optimal_loss = (self.distance_between_strikes - self.net_premium) * contracts  # Max loss at stop
        else:
            # Debit spread optimal scenarios
            self.optimal_profit = (self.distance_between_strikes - abs(self.net_premium)) * contracts  # Max profit at target
            self.optimal_loss = abs(self.net_premium) * contracts  # Max loss at stop
            
        # Calculate profit factor (ratio of optimal profit to optimal loss)
        if self.optimal_loss and self.optimal_loss != 0:
            self.profit_factor = abs(self.optimal_profit / self.optimal_loss)
        else:
            self.profit_factor = Decimal('0')
            
        self.entry_price = self.previous_close
        self.exit_date = self.get_exit_date()
        self.contract_type = self.short_contract.contract_type
        self.probability_of_profit = VerticalSpread._calculate_probability_of_profit(self, days_to_expiration)
        
        if self.probability_of_profit is None:
            logger.warning("Probability of profit calculation failed.")
            logger.debug("Exiting _calculate_spread_metrics")
            return False

        self.reward_risk_ratio = self.max_reward / self.max_risk if self.max_risk != 0 else Decimal('0')
        
        logger.debug("Exiting _calculate_spread_metrics")
        return True

    @staticmethod
    def _calculate_probability_of_profit(spread: 'VerticalSpread', days_to_expiration: int) -> Optional[Decimal]:
        """Calculate probability of profit using implied volatility and time to expiration."""
        logger.debug("Entering _calculate_probability_of_profit")
        implied_volatility = spread.first_leg_snapshot.implied_volatility * spread.second_leg_snapshot.implied_volatility
        result = Options.calculate_probability_of_profit(spread.previous_close, spread.breakeven, days_to_expiration, implied_volatility)
        logger.debug("Exiting _calculate_probability_of_profit")
        return result

class CreditSpread(VerticalSpread):

    ideal_expiration: ClassVar[int] = 45

    def get_max_reward(self):
        return self.get_net_premium()*100

    def get_max_risk(self):
        return Decimal((abs(self.distance_between_strikes) - self.get_net_premium())*Decimal(100))

    def get_breakeven_price(self):
        net_premium = self.get_net_premium()
        return Decimal(self.short_contract.strike_price) + (-net_premium if self.direction == DirectionType.BULLISH else net_premium)

    def get_target_price(self):
        self.target_reward = (self.get_net_premium() * Decimal(0.8))
        return self.previous_close + (self.target_reward if self.direction == DirectionType.BULLISH else -self.target_reward)

    def get_stop_price(self):
        self.target_stop = (self.get_net_premium() / Decimal(2))
        return self.previous_close - (self.target_stop if self.direction == DirectionType.BULLISH else -self.target_stop)

    def get_net_premium(self) -> Decimal:

        if self.net_premium is not None:
            logger.debug(f"Using cached net premium: {self.net_premium}")
            return self.net_premium
        
        # Use parent class validation - if returns 0, data is invalid
        if not self.validate_net_premium():
            logger.debug("Parent validation failed")
            return Decimal('0')

        logger.debug("Calculating credit spread net premium")
        # Set contract type based on first leg
        self.contract_type = self.first_leg_contract.contract_type

        logger.debug(f"Processing call spread - comparing strikes firt {self.first_leg_contract.strike_price} and second {self.second_leg_contract.strike_price}")
        
        if self.first_leg_contract.strike_price < self.second_leg_contract.strike_price:
            # Bear Call: Short lower strike call, Long higher strike call
            # First leg is short (lower strike), second leg is long (higher strike)
            short_snapshot = self.first_leg_snapshot
            long_snapshot = self.second_leg_snapshot
            logger.debug("Bear Call. Using first leg as short (lower strike)")
        else:
            # Bull Put: Short higher strike put, Long lower strike put
            # Second leg is short (lower strike), first leg is long (higher strike)
            short_snapshot = self.second_leg_snapshot
            long_snapshot = self.first_leg_snapshot
            logger.debug("Bull Put. Using second leg as short (lower strike)")
            
        # Calculate credit spread premium
        self.net_premium = short_snapshot.day.bid - long_snapshot.day.ask
        logger.debug(f"Net premium = {short_snapshot.day.bid} - {long_snapshot.day.ask} = {self.net_premium}")
        
        if self.net_premium <= 0:
            logger.warning(f"Invalid credit spread - net debit of {self.net_premium}")
            return Decimal('0')
            
        return self.net_premium  # Already positive for credit

class DebitSpread(VerticalSpread):
    ideal_expiration: ClassVar[int] = 45

    def get_max_reward(self):
        return (abs(self.distance_between_strikes) - abs(self.get_net_premium()))*100

    def get_max_risk(self):
        return abs(self.get_net_premium()*100)

    def get_breakeven_price(self):
        net_premium = abs(self.get_net_premium())
        if self.direction == DirectionType.BULLISH:
            return Decimal(self.long_contract.strike_price) + net_premium
        else:
            return Decimal(self.long_contract.strike_price) - net_premium

    def get_target_price(self):
        self.target_reward = (self.distance_between_strikes * Decimal(0.8))
        return self.previous_close + (self.target_reward if self.direction == DirectionType.BULLISH else -self.target_reward)

    def get_stop_price(self):
        self.target_stop = (self.distance_between_strikes / Decimal(2))
        return self.previous_close - (self.target_stop if self.direction == DirectionType.BULLISH else -self.target_stop)

    def get_net_premium(self) -> Decimal:
        """Calculate net premium for debit spreads:
        Net Debit = Long ask price - Short bid price"""
        logger.debug("Calculating debit spread net premium")
        
        if self.net_premium is not None:
            logger.debug(f"Using cached net premium: {self.net_premium}")
            return self.net_premium
        
        # Use parent class validation - if returns False, data is invalid
        if not self.validate_net_premium():
            logger.debug("Parent validation failed")
            return Decimal('0')

        # Set contract type based on first leg
        self.contract_type = self.first_leg_contract.contract_type

        logger.debug(f"Processing call spread - comparing strikes first {self.first_leg_contract.strike_price} and second {self.second_leg_contract.strike_price}")
        
        if self.first_leg_contract.strike_price < self.second_leg_contract.strike_price:
            # Bull Call: Long lower strike call, Short higher strike call
            # First leg is long (lower strike), second leg is short (higher strike)
            long_snapshot = self.first_leg_snapshot
            short_snapshot = self.second_leg_snapshot
            logger.debug("Using first leg as long (lower strike)")
        else:
            # Bear Put: Long higher strike put, Short lower strike put
            # First leg is long (higher strike), second leg is short (lower strike)
            long_snapshot = self.second_leg_snapshot
            short_snapshot = self.first_leg_snapshot
            logger.debug("Using second leg as long (higher strike)")
            
        # Calculate debit spread premium
        self.net_premium = long_snapshot.day.ask - short_snapshot.day.bid
        logger.debug(f"Net premium = {long_snapshot.day.ask} - {short_snapshot.day.bid} = {self.net_premium}")
        
        if self.net_premium >= 0:
            logger.warning(f"Invalid debit spread - net credit of {self.net_premium}")
            return Decimal('0')
            
        return self.net_premium  # Should be negatif for debit

class VerticalSpreadMatcher:
    """Handles the matching and selection of vertical spread contracts."""
    
    @staticmethod
    def match_option(
        options_snapshots: dict,
        underlying_ticker: str,
        direction: DirectionType,
        strategy: StrategyType,
        previous_close: Decimal,
        date: datetime,
        contracts: list[Contract]
    ) -> VerticalSpread:
        """Create and match a vertical spread based on given parameters."""
        logger.debug("Entering match_option")
        
        # Log input parameters
        logger.debug(f"Input parameters:")
        logger.debug(f"- Underlying ticker: {underlying_ticker}")
        logger.debug(f"- Direction: {direction.value}")
        logger.debug(f"- Strategy: {strategy.value}")
        logger.debug(f"- Previous close: {previous_close}")
        logger.debug(f"- Expiration date: {date}")
        logger.debug(f"- Number of contracts: {len(contracts)}")
        logger.debug(f"- Number of snapshots: {len(options_snapshots)}")
        
        # Log contract details
        for contract in contracts:
            snapshot = options_snapshots.get(contract.ticker)
            if snapshot:
                logger.debug(f"Contract {contract.ticker}:")
                logger.debug(f"- Strike: {contract.strike_price}")
                logger.debug(f"- Delta: {snapshot.greeks.delta}")
                logger.debug(f"- Bid/Ask: {snapshot.day.bid}/{snapshot.day.ask}")
        
        spread = CreditSpread() if strategy == StrategyType.CREDIT else DebitSpread()
        VerticalSpreadMatcher._initialize_match_option(spread, underlying_ticker, direction, strategy, previous_close, date, contracts)
        
        days_to_expiration: int = (spread.expiration_date - spread.update_date).days
        first_leg_candidates = VerticalSpreadMatcher._select_first_leg_candidates(spread, options_snapshots)

        second_leg_candidates = VerticalSpreadMatcher._select_second_leg_candidates(spread, options_snapshots)

        final_spread:VerticalSpread = VerticalSpreadMatcher._find_best_spread(spread, first_leg_candidates, second_leg_candidates, 
                                                          days_to_expiration, spread.optimal_spread_width)
        
        return final_spread

    @staticmethod
    def _initialize_match_option(spread: VerticalSpread, underlying_ticker: str, direction: DirectionType, strategy: StrategyType, 
                                 previous_close: Decimal, date: datetime, contracts: List[Contract]) -> None:
        logger.debug("Entering _initialize_match_option")
        spread.underlying_ticker = underlying_ticker
        spread.direction = direction
        spread.strategy = strategy
        spread.previous_close = previous_close
        spread.expiration_date = date
        spread.update_date = datetime.today().date()
        spread.contracts = contracts
        spread.optimal_spread_width = Options.calculate_optimal_spread_width(previous_close, spread.strategy, spread.direction)
        logger.debug("Exiting _initialize_match_option")

    @staticmethod
    def _select_first_leg_candidates(spread: VerticalSpread, options_snapshots: dict) -> List[Tuple[Contract, int, Snapshot]]:
        logger.debug("Entering _select_first_leg_candidates")
        # Determine price status based on strategy and direction
        if spread.strategy == StrategyType.DEBIT:
            if spread.direction == DirectionType.BULLISH:
                # Bull Call: Buy lower strike call (closer to ATM)
                price_status = ['OTM']
            else:
                # Bear Put: Buy higher strike put (ITM/ATM)
                price_status = ['OTM']
        else:  # CREDIT
            if spread.direction == DirectionType.BULLISH:
                # Bull Put: Sell higher strike put (OTM)
                price_status = ['ATM']
            else:
                # Bear Call: Sell lower strike call (OTM)
                price_status = ['ATM']

        result = spread.contract_selector.select_contracts(
            spread.contracts, 
            options_snapshots, 
            spread.underlying_ticker, 
            spread.strategy,
            spread.direction,
            spread.previous_close,
            price_status,
            is_first_leg=True
        )
        logger.debug("Exiting _select_first_leg_candidates")
        return result

    @staticmethod
    def _select_second_leg_candidates(spread: VerticalSpread, options_snapshots: dict) -> List[Tuple[Contract, int, Snapshot]]:
        logger.debug("Entering _select_second_leg_candidates")
        # Determine price status based on strategy and direction
        if spread.strategy == StrategyType.DEBIT:
            if spread.direction == DirectionType.BULLISH:
                # Bull Call: Sell higher strike call (OTM)
                price_status = ['ATM']
            else:
                # Bear Put: Sell lower strike put (OTM)
                price_status = ['ATM']
        else:  # CREDIT
            if spread.direction == DirectionType.BULLISH:
                # Bull Put: Buy lower strike put (ATM/ITM)
                price_status = ['OTM']
            else:
                # Bear Call: Buy higher strike call (ATM)
                price_status = ['OTM']

        result = spread.contract_selector.select_contracts(
            spread.contracts, 
            options_snapshots, 
            spread.underlying_ticker, 
            spread.strategy,
            spread.direction,
            spread.previous_close,
            price_status,
            is_first_leg=False
        )
        logger.debug("Exiting _select_second_leg_candidates")
        return result

    @staticmethod
    def _find_best_spread(spread: VerticalSpread, first_leg_candidates: List[Tuple[Contract, int, Snapshot]], 
                          second_leg_candidates: List[Tuple[Contract, int, Snapshot]], 
                          days_to_expiration: int, optimal_spread_width: Decimal) -> VerticalSpread:
        logger.debug("Entering _find_best_spread")
        best_spread: Optional[VerticalSpread] = None
        best_spread_width: Optional[VerticalSpread] = None 
        best_spread_non_standard: Optional[VerticalSpread] = None 
        found_valid_spread: bool = False
        final_spread:VerticalSpread = spread

        if not first_leg_candidates or not second_leg_candidates:
            logger.debug("No valid first or second leg candidates found")
        else:
            for first_leg in first_leg_candidates:
                contract, _, _ = first_leg
                if not contract.matched:
                    continue
                
                for second_leg in second_leg_candidates:
                    contract, _, _ = second_leg
                    if not contract.matched:
                        continue

                    logger.debug("-------- Processing spread candidate --------")   
                    VerticalSpreadMatcher._set_spread_legs(spread, first_leg, second_leg)
                    
                    # Changed: Call instance method instead of static
                    if not spread._validate_spread_parameters():
                        logger.debug("Skipping candidate due to failed spread parameter validation.")
                        continue
                        
                    if not spread._calculate_spread_metrics(days_to_expiration):
                        logger.debug("Skipping candidate due to failed spread metrics calculation.")
                        continue
                        
                    VerticalSpreadMatcher._calculate_adjusted_score(spread)

                    found_valid_spread = True                
                    # Update best spreads with deep copies
                    best_spread, best_spread_width, best_spread_non_standard = VerticalSpreadMatcher._update_best_spreads(
                        spread, best_spread, best_spread_width, best_spread_non_standard)
                        
        if found_valid_spread:
            final_spread = VerticalSpreadMatcher._determine_final_spread(spread, best_spread_width, best_spread_non_standard)
            final_spread.matched = True
            if final_spread:  # Add null check
                final_spread.description = VerticalSpreadMatcher._generate_description(final_spread)
                logger.debug("Exiting _find_best_spread with valid spread")
            else:
                logger.warning("No valid spread found after determination")
        else:
            final_spread.matched = False

        logger.debug("Exiting _find_best_spread without finding valid spread")
        if final_spread is type(bool):
            return False
        return final_spread

    @staticmethod
    def _set_spread_legs(spread: VerticalSpread, first_leg: Tuple[Contract, int, Snapshot], 
                        second_leg: Tuple[Contract, int, Snapshot]) -> None:
        """Set both spread legs based on strategy and direction, ensuring proper strike relationships."""
        logger.debug("Setting spread legs")
        
        # Set contracts and positions
        spread.first_leg_contract, spread.first_leg_contract_position, spread.first_leg_snapshot = first_leg
        spread.second_leg_contract, spread.second_leg_contract_position, spread.second_leg_snapshot = second_leg

        # Calculate distance between strikes
        spread.distance_between_strikes = abs(spread.first_leg_contract.strike_price - spread.second_leg_contract.strike_price)
        
        # Calculate width boundaries based on stock price
        min_width = VerticalSpread.get_minimum_spread_width(spread.previous_close, spread.strategy, spread.direction)
        max_width = VerticalSpread.get_maximum_spread_width(spread.previous_close, spread.strategy, spread.direction)
        
        # Log width analysis
        logger.debug(f"First leg strike: {spread.first_leg_contract.strike_price}")
        logger.debug(f"Second leg strike: {spread.second_leg_contract.strike_price}")
        logger.debug(f"Spread width: {spread.distance_between_strikes} (min: {min_width}, max: {max_width})")
        
        # Validate spread width for all strategies
        if spread.distance_between_strikes < min_width or spread.distance_between_strikes > max_width:
            logger.debug(f"Spread width {spread.distance_between_strikes} outside acceptable range [{min_width}, {max_width}]")
            spread.distance_between_strikes = Decimal('0')  # Forces rejection in validation
            return

        # Define strike price relationships for all combinations
        SPREAD_CONFIG = {
            (StrategyType.CREDIT, DirectionType.BULLISH): {  # Bull Put
                'short_higher': True,  # Short higher strike, Long lower strike
                'compare': operator.gt  # first_leg > second_leg for proper assignment
            },
            (StrategyType.CREDIT, DirectionType.BEARISH): {  # Bear Call
                'short_higher': False,  # Short lower strike, Long higher strike
                'compare': operator.lt,  # first_leg < second_leg for proper assignment
            },
            (StrategyType.DEBIT, DirectionType.BULLISH): {  # Bull Call
                'short_higher': True,  # Long lower strike, Short higher strike
                'compare': operator.lt  # first_leg < second_leg for proper assignment
            },
            (StrategyType.DEBIT, DirectionType.BEARISH): {  # Bear Put
                'short_higher': False,  # Long higher strike, Short lower strike
                'compare': operator.gt  # first_leg > second_leg for proper assignment
            }
        }

        # Fix: Change config['compare'] to SPREAD_CONFIG[(spread.strategy, spread.direction)]['compare']
        config_key = (spread.strategy, spread.direction)
        compare_result = SPREAD_CONFIG[config_key]['compare'](
            spread.first_leg_contract.strike_price, 
            spread.second_leg_contract.strike_price
        )

        if compare_result:
            # First leg meets the criteria
            if spread.strategy == StrategyType.CREDIT:
                spread.short_contract, spread.short_premium = spread.first_leg_contract, spread.first_leg_snapshot.day.bid
                spread.long_contract, spread.long_premium = spread.second_leg_contract, spread.second_leg_snapshot.day.ask
            else:  # DEBIT
                spread.long_contract, spread.long_premium = spread.first_leg_contract, spread.first_leg_snapshot.day.ask
                spread.short_contract, spread.short_premium = spread.second_leg_contract, spread.second_leg_snapshot.day.bid
        else:
            # Second leg meets the criteria
            if spread.strategy == StrategyType.CREDIT:
                spread.short_contract, spread.short_premium = spread.second_leg_contract, spread.second_leg_snapshot.day.bid
                spread.long_contract, spread.long_premium = spread.first_leg_contract, spread.first_leg_snapshot.day.ask
            else:  # DEBIT
                spread.long_contract, spread.long_premium = spread.second_leg_contract, spread.second_leg_snapshot.day.ask
                spread.short_contract, spread.short_premium = spread.first_leg_contract, spread.first_leg_snapshot.day.bid

        spread.net_premium = spread.get_net_premium()

        logger.debug(f"{spread.strategy.value} {spread.direction.value} data:")
        logger.debug(f"Short strike {spread.short_contract.strike_price}, bid: {spread.short_premium}")
        logger.debug(f"Long strike {spread.long_contract.strike_price}, ask: {spread.long_premium}")
        logger.debug(f"Distance between strikes: {spread.distance_between_strikes}")

    @staticmethod
    def _generate_description(spread: VerticalSpread) -> str:
        logger.debug("Entering _generate_description")
        description = (
            f"{spread.strategy.value.capitalize()} {spread.direction.value.capitalize()} Spread\n"
            f"Underlying: {spread.underlying_ticker}\n"
            f"Sale: ${spread.short_contract.strike_price:.2f}\n"
            f"Buy: ${spread.long_contract.strike_price:.2f}\n"
            f"Net Premium: ${spread.net_premium:.2f}\n"
            f"Target Price: ${spread.target_price:.2f}\n"
        )
        logger.debug("Exiting _generate_description")
        return description

    @staticmethod
    def _calculate_adjusted_score(spread: VerticalSpread) -> None:
        """Calculate adjusted score based on multiple weighted components.
        
        Mathematical Components and Reasoning:
        -----------------------------------
        1. Probability of Profit Score (35% weight):
           - Uses Black-Scholes model for theoretical probability calculation
           - Optimal POP ranges differ by spread type:
             Credit spreads: 60-80% optimal (high probability strategy)
             Debit spreads: 40-60% optimal (directional strategy)
           - Score adjusted based on strategy:
             Credit: Linear scale with peak at 75% POP
             Debit: Linear scale with peak at 50% POP
           - Additional penalty for extreme POPs outside optimal ranges
           Example: 70% POP
           Credit spread: 70% is near optimal (95 points)
           Debit spread: 70% is too conservative (80 points)
           Final = adjusted_pop * 0.35
           Reasoning: Aligns scoring with strategy objectives

        2. Optimal Width Score (15% weight):
           - Measures how well spread width matches market conditions
           - Uses ratio = actual_width / optimal_width
           - Perfect score when ratio = 1.0 (exactly optimal)
           - Linear penalty function: score = 100 - (|1 - ratio| * 50)
           - Rejects extreme deviations (ratio < 0.5 or > 2.0)
           Example: ratio = 1.2
           Deviation = |1 - 1.2| = 0.2
           Score = 100 - (0.2 * 50) = 90 points
           Final = 90 * 0.15 = 13.5 points contribution
           Reasoning: Balances risk/reward while maintaining practical width

        3. Reward/Risk Ratio Score (20% weight):
           - Target R/R = 2.0 (standard risk management practice)
           - Score = min(100, (actual_R/R / target_R/R) * 100)
           - Linear scaling up to target, capped at 100
           - Higher weight because R/R directly impacts profitability
           Example: R/R = 1.5
           Score = min(100, (1.5/2.0) * 100) = 75 points
           Final = 75 * 0.20 = 15 points contribution
           Reasoning: Rewards trades with better risk-adjusted returns

        4. Risk Management Score (10% weight):
           - Based on position size vs max acceptable loss (5%)
           - max_loss_percent = max_risk / (underlying_price * 100)
           - Linear scaling: score = (1 - loss_pct/max_acceptable) * 100
           - Score = 0 if exceeds max acceptable loss
           Example: max_loss = 3% of position
           Score = (1 - 0.03/0.05) * 100 = 40 points
           Final = 40 * 0.10 = 4 points contribution
           Reasoning: Penalizes overleveraged positions

        5. Liquidity Score (20% weight):
           Per leg calculation:
           - Volume score = min(100, (volume/VOLUME_EXCELLENT) * 100)
           - OI score = min(100, (OI/OI_EXCELLENT) * 100)
           - Combined = (volume_score + oi_score) / 2
           Final = average_of_both_legs * 0.20
           Example:
           Leg 1: volume=150 (75%), OI=400 (80%) = 77.5%
           Leg 2: volume=100 (50%), OI=300 (60%) = 55%
           Average = 66.25%
           Final = 66.25 * 0.20 = 13.25 points contribution
           Reasoning: Ensures tradability and reasonable bid-ask spreads

        Edge Cases and Adjustments:
        -------------------------
        - Zero volume/OI: Automatic zero score for liquidity
        - Extreme width ratios: Score reduced based on deviation
        - Very high R/R (>3:1): Capped at 100 points
        - Near-zero POP (<20%): Additional penalty to risk score
        - High IV environment: Width scoring more forgiving

        Total Score Interpretation:
        -------------------------
        90-100: Excellent trade setup
        75-89: Strong candidate
        60-74: Acceptable setup
        40-59: Marginal setup
        <40: Poor setup, avoid trade

        Final Score = Sum of all weighted components (0-100 scale)
        """
        logger.debug("Entering _calculate_adjusted_score")

        # Define component weights based on strategy importance
        # POP and R/R get higher weights as they're primary performance indicators
        WEIGHT_CONFIDENCE = Decimal('0.15')  # New weight for confidence level
        # Adjust other weights to maintain total of 1.0
        WEIGHT_POP = Decimal('0.30')
        WEIGHT_WIDTH = Decimal('0.15')
        WEIGHT_RR = Decimal('0.15')
        WEIGHT_RISK = Decimal('0.10')
        WEIGHT_LIQUIDITY = Decimal('0.15')

        # POP thresholds optimized for each strategy type
        # Credit spreads need higher POP due to limited upside
        CREDIT_MIN_POP = Decimal('0.40')       # Was 0.60 - Lower minimum acceptable POP for credit spreads
        CREDIT_OPTIMAL_POP = Decimal('0.60')   # Was 0.75 - Lower target POP for credit spreads
        CREDIT_PENALTY_FACTOR = Decimal('0.25') # Was 0.40 - Reduced penalty for exceeding optimal POP

        # Debit spreads can accept lower POP due to higher potential returns
        DEBIT_MIN_POP = Decimal('0.30')        # Was 0.40 - Lower minimum acceptable POP for debit spreads
        DEBIT_OPTIMAL_POP = Decimal('0.50')    # Was 0.60 - Lower target POP for debit spreads
        DEBIT_PENALTY_FACTOR = Decimal('0.30')  # Was 0.60 - Reduced penalty for conservative debit spreads

        # Width ratio constraints for practical trade execution
        MIN_WIDTH_RATIO = Decimal('0.5')        # Minimum acceptable width vs optimal
        MAX_WIDTH_RATIO = Decimal('2.0')        # Maximum acceptable width vs optimal
        OPTIMAL_WIDTH_RATIO = Decimal('1.0')    # Perfect width ratio
        WIDTH_PENALTY_FACTOR = Decimal('50')    # Linear penalty for suboptimal width

        # Position sizing and risk parameters
        MAX_POSITION_SIZE = Decimal('100')      # Standard contract size (100 shares)
        RISK_PENALTY_FACTOR = Decimal('100')    # Scaling factor for risk penalties

        # Score boundaries for normalization
        MIN_SCORE = Decimal('0')
        MAX_SCORE = Decimal('100')

        # Calculate POP score with strategy-specific scaling
        pop_score = Decimal('0')
        if spread.probability_of_profit:
            # Convert POP from percentage to decimal form (e.g., 68.57240% -> 0.6857240)
            pop = spread.probability_of_profit / Decimal('100')
            if spread.strategy == StrategyType.CREDIT:
                if pop < CREDIT_MIN_POP:
                    # Scale linearly from 0 to MAX_SCORE
                    pop_score = MAX_SCORE * (pop / CREDIT_MIN_POP)
                elif pop <= CREDIT_OPTIMAL_POP:
                    # Scale linearly from MIN_POP to OPTIMAL_POP
                    pop_range = CREDIT_OPTIMAL_POP - CREDIT_MIN_POP
                    pop_above_min = pop - CREDIT_MIN_POP
                    pop_score = MAX_SCORE * (Decimal('0.8') + (Decimal('0.2') * (pop_above_min / pop_range)))
                else:
                    # Handle POP values that exceed optimal
                    pop_above_optimal = pop - CREDIT_OPTIMAL_POP
                    remaining_range = Decimal('1') - CREDIT_OPTIMAL_POP
                    if remaining_range <= Decimal('0'):
                        pop_score = MIN_SCORE
                    else:
                        excess = pop_above_optimal / remaining_range
                        pop_score = MAX_SCORE * (Decimal('1') - excess * CREDIT_PENALTY_FACTOR)
            else:  # DEBIT
                if pop < DEBIT_MIN_POP:
                    pop_score = MAX_SCORE * (pop / DEBIT_MIN_POP)
                elif pop <= DEBIT_OPTIMAL_POP:
                    # Scale linearly from MIN_POP to OPTIMAL_POP
                    pop_range = DEBIT_OPTIMAL_POP - DEBIT_MIN_POP
                    pop_above_min = pop - DEBIT_MIN_POP
                    pop_score = MAX_SCORE * (Decimal('0.8') + (Decimal('0.2') * (pop_above_min / pop_range)))
                else:
                    # Handle POP values that exceed optimal
                    pop_above_optimal = pop - DEBIT_OPTIMAL_POP
                    remaining_range = Decimal('1') - DEBIT_OPTIMAL_POP
                    if remaining_range <= Decimal('0'):
                        pop_score = MIN_SCORE
                    else:
                        excess = pop_above_optimal / remaining_range
                        pop_score = MAX_SCORE * (Decimal('1') - excess * DEBIT_PENALTY_FACTOR)
            
            # Keep score within standard bounds
            pop_score = max(MIN_SCORE, min(MAX_SCORE, pop_score))

        # Score the spread width relative to optimal width
        width_ratio = spread.distance_between_strikes / spread.optimal_spread_width
        width_score = MAX_SCORE
        if width_ratio < MIN_WIDTH_RATIO or width_ratio > MAX_WIDTH_RATIO:
            # Reject extreme width deviations
            width_score = MIN_SCORE
        elif width_ratio != OPTIMAL_WIDTH_RATIO:
            # Apply linear penalty based on deviation from optimal
            deviation = abs(OPTIMAL_WIDTH_RATIO - width_ratio)
            width_score = MAX_SCORE - (deviation * WIDTH_PENALTY_FACTOR)

        # Score reward/risk ratio relative to target
        target_rr = spread.TARGET_REWARD_RISK_RATIO
        actual_rr = spread.reward_risk_ratio
        # Cap R/R score at 100 to avoid overweighting extremely high ratios
        rr_score = min(MAX_SCORE, (actual_rr / target_rr) * MAX_SCORE)

        # Calculate risk score based on position size
        position_value = spread.previous_close * MAX_POSITION_SIZE
        max_loss_percent = spread.max_risk / position_value
        risk_score = MAX_SCORE
        if max_loss_percent > spread.MAX_ACCEPTABLE_LOSS_PERCENT:
            # Reject trades exceeding max risk threshold
            risk_score = MIN_SCORE
        else:
            # Linear scaling based on risk utilization (higher score for lower risk)
            risk_utilization = max_loss_percent / spread.MAX_ACCEPTABLE_LOSS_PERCENT
            risk_score = MAX_SCORE * (Decimal('1') - risk_utilization)

        # Score can't be negative
        risk_score = max(MIN_SCORE, risk_score)

        # Calculate average liquidity score across both legs with width adjustment
        liquidity_score = MIN_SCORE
        
        # Get standard widths for the stock price
        standard_widths = ContractSelector.get_standard_widths(spread.previous_close)
        
        # Calculate width adjustment factor
        # Spreads using standard widths get full liquidity score
        # Non-standard widths get penalized
        width_adjustment = Decimal('1.0')
        if spread.distance_between_strikes not in standard_widths:
            closest_width = min(standard_widths, key=lambda x: abs(x - spread.distance_between_strikes))
            width_diff_pct = abs(spread.distance_between_strikes - closest_width) / closest_width
            width_adjustment = max(Decimal('0.5'), Decimal('1.0') - width_diff_pct)
            logger.debug(f"Non-standard width adjustment: {width_adjustment}")
        
        for i, contract in enumerate([spread.long_contract, spread.short_contract]):
            snapshot = (spread.first_leg_snapshot if contract == spread.first_leg_contract 
                       else spread.second_leg_snapshot)
            
            # Score volume relative to excellent threshold
            volume_score = min(MAX_SCORE, 
                             (DataModelBase.to_decimal(snapshot.day.volume) / 
                              DataModelBase.to_decimal(spread.VOLUME_EXCELLENT_THRESHOLD)) * MAX_SCORE)
            
            # Score open interest relative to excellent threshold
            oi_score = min(MAX_SCORE, 
                          (DataModelBase.to_decimal(snapshot.day.open_interest) / 
                           DataModelBase.to_decimal(spread.OI_EXCELLENT_THRESHOLD)) * MAX_SCORE)
            
            # Average the volume and OI scores for this leg
            leg_score = (volume_score + oi_score) / Decimal('2')
            # Apply width adjustment to leg score
            leg_score *= width_adjustment
            liquidity_score += leg_score
            logger.debug(f"Leg {i+1} Liquidity: vol={volume_score}, oi={oi_score}, " + 
                        f"width_adj={width_adjustment}, final={leg_score}")
        
        # Average the liquidity scores of both legs
        liquidity_score /= Decimal('2')

        # Calculate confidence level score with None handling
        spread.confidence_level = Decimal('1.0')
        # Multiply confidence from contracts
        for contract in [spread.first_leg_contract, spread.second_leg_contract]:
            if hasattr(contract, 'confidence_level') and contract.confidence_level is not None:
                try:
                    spread.confidence_level *= Decimal(str(contract.confidence_level))
                except (TypeError, ValueError):
                    logger.warning(f"Invalid confidence_level in contract: {contract.confidence_level}")
                    spread.confidence_level *= Decimal('0.5')  # Default penalty for invalid confidence

        # Multiply confidence from snapshots
        for snapshot in [spread.first_leg_snapshot, spread.second_leg_snapshot]:
            if hasattr(snapshot, 'confidence_level') and snapshot.confidence_level is not None:
                try:
                    spread.confidence_level *= Decimal(str(snapshot.confidence_level))
                except (TypeError, ValueError):
                    logger.warning(f"Invalid confidence_level in snapshot: {snapshot.confidence_level}")
                    spread.confidence_level *= Decimal('0.5')  # Default penalty for invalid confidence

        # Ensure confidence is within valid range
        spread.confidence_level = max(Decimal('0.1'), min(Decimal('1.0'), spread.confidence_level))
        confidence_score = spread.confidence_level * MAX_SCORE

        # Store raw and calculated POP scores
        spread.score_pop_raw = pop if pop else Decimal('0')
        spread.score_pop = pop_score
        
        # Store width ratio and score
        spread.score_width_raw = width_ratio
        spread.score_width = width_score
        
        # Store reward/risk ratio and score  
        spread.score_reward_risk_raw = actual_rr
        spread.score_reward_risk = rr_score
        
        # Store risk scores
        spread.score_risk_raw = max_loss_percent * Decimal('100')  # Convert to percentage
        spread.score_risk = risk_score
        
        # Store liquidity scores
        spread.score_liquidity = liquidity_score
        spread.score_liquidity_volume = volume_score  # From last leg iteration
        spread.score_liquidity_oi = oi_score  # From last leg iteration

        # Store confidence metrics
        spread.score_confidence_raw = spread.confidence_level
        spread.score_confidence = confidence_score

        # Compute final weighted score
        spread.adjusted_score = (
            (pop_score * WEIGHT_POP) +
            (width_score * WEIGHT_WIDTH) +
            (rr_score * WEIGHT_RR) +
            (risk_score * WEIGHT_RISK) +
            (liquidity_score * WEIGHT_LIQUIDITY) +
            (confidence_score * WEIGHT_CONFIDENCE)
        )

        logger.debug(f"Final adjusted score: {spread.adjusted_score:.2f}")

    @staticmethod
    def _update_best_spreads(spread: VerticalSpread, best_spread: Optional[VerticalSpread],
                            best_spread_width: Optional[VerticalSpread],
                            best_spread_non_standard: Optional[VerticalSpread]) -> Tuple[Optional[VerticalSpread], Optional[VerticalSpread], Optional[VerticalSpread]]:
        logger.debug("Entering _update_best_spreads")
        
        # Create deep copy for best overall spread
        if not best_spread or (best_spread and spread.adjusted_score > best_spread.adjusted_score):
            best_spread = spread.copy()

        # Create deep copy for width-based spreads
        if spread.distance_between_strikes == spread.optimal_spread_width:
            if not best_spread_width or (best_spread_width and spread.adjusted_score > best_spread_width.adjusted_score):
                best_spread_width = spread.copy()
        else:
            if not best_spread_non_standard or (best_spread_non_standard and spread.adjusted_score > best_spread_non_standard.adjusted_score):
                best_spread_non_standard = spread.copy()

        logger.debug("Exiting _update_best_spreads")
        return best_spread, best_spread_width, best_spread_non_standard

    @staticmethod
    def _determine_final_spread(current_spread: VerticalSpread, best_spread_width: Optional[VerticalSpread], 
                               best_spread_non_standard: Optional[VerticalSpread]) -> VerticalSpread:
        logger.debug("Entering _determine_final_spread")
        if best_spread_width:
            logger.debug("Exiting _determine_final_spread with best width spread")
            return best_spread_width
        if best_spread_non_standard:
            logger.debug("Exiting _determine_final_spread with best non-standard spread")
            return best_spread_non_standard
        logger.debug("Exiting _determine_final_spread with current spread")
        return current_spread
