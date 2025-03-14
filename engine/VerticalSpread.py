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
from typing import ClassVar, Optional, List, Tuple
from decimal import Decimal, getcontext

logger = logging.getLogger(__name__)

class VerticalSpread(SpreadDataModel):
    """Base class for vertical spread calculations (credit and debit)."""
    MAX_STRIKES: ClassVar[int] = 20  # Maximum number of strikes to consider
    MIN_DELTA: ClassVar[Decimal] = Decimal(0.26)  # Minimum absolute delta for a contract to be considered
    
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
    EXTREME_WIDTH_RATIO: ClassVar[Decimal] = Decimal('5.0')  # Ratio for extremely wide spreads
    MAX_CONFIDENCE_REDUCTION: ClassVar[Decimal] = Decimal('0.5')  # Maximum confidence reduction
    CONFIDENCE_REDUCTION_STEP: ClassVar[Decimal] = Decimal('0.1')  # Step for confidence reduction

    contracts: List[Contract] = []
    # Make contract_selector an instance attribute instead of ClassVar
    contract_selector: ContractSelector = StandardContractSelector()
    
    def get_net_premium(self)-> Decimal:
        logger.debug("Entering get_net_premium")
        if self.short_premium is None or self.long_premium is None:
            logger.error("Missing premium values")
            return Decimal('0')
        
        net = self.short_premium - self.long_premium
        
        # Validation: Credit spreads should have positive net premium
        if self.strategy == StrategyType.CREDIT and net <= 0:
            logger.warning(f"Credit spread has negative or zero net premium: {net}")
            return Decimal('0')
            
        # Validation: Debit spreads should have negative net premium
        if self.strategy == StrategyType.DEBIT and net >= 0:
            logger.warning(f"Debit spread has positive or zero net premium: {net}")
            return Decimal('0')
            
        logger.debug(f"Net Premium: {net} (Short: {self.short_premium} - Long: {self.long_premium})")
        logger.debug("Exiting get_net_premium")
        return net

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
        target_reward = (self.get_net_premium() * Decimal(0.8))
        return self.previous_close + (target_reward if self.direction == DirectionType.BULLISH else -target_reward)

    def get_stop_price(self):
        target_stop = (self.get_net_premium() / Decimal(2))
        return self.previous_close - (target_stop if self.direction == DirectionType.BULLISH else -target_stop)

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
        target_reward = (self.distance_between_strikes * Decimal(0.8))
        return self.previous_close + (target_reward if self.direction == DirectionType.BULLISH else -target_reward)

    def get_stop_price(self):
        target_stop = (self.distance_between_strikes / Decimal(2))
        return self.previous_close - (target_stop if self.direction == DirectionType.BULLISH else -target_stop)

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
                        
                    VerticalSpreadMatcher._set_spread_legs(spread, first_leg, second_leg)
                    
                    if not VerticalSpreadMatcher._calculate_spread_metrics(spread, days_to_expiration):
                        logger.debug("Skipping candidate due to failed spread metrics calculation.")
                        continue
                        
                    if not VerticalSpreadMatcher._validate_spread_parameters(spread):
                        logger.debug("Skipping candidate due to failed spread parameter validation.")
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

        # Define strike price relationships for all combinations
        SPREAD_CONFIG = {
            (StrategyType.CREDIT, DirectionType.BULLISH): {  # Bull Put
                'short_higher': True,  # Short higher strike, Long lower strike
                'compare': operator.gt  # first_leg > second_leg for proper assignment
            },
            (StrategyType.CREDIT, DirectionType.BEARISH): {  # Bear Call
                'short_higher': False,  # Short lower strike, Long higher strike
                'compare': operator.lt  # first_leg < second_leg for proper assignment
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

        config = SPREAD_CONFIG[(spread.strategy, spread.direction)]
        compare_result = config['compare'](spread.first_leg_contract.strike_price, 
                                         spread.second_leg_contract.strike_price)

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

        logger.debug(f"Set {spread.strategy.value} {spread.direction.value} spread with short strike {spread.short_contract.strike_price} and long strike {spread.long_contract.strike_price}")

    @staticmethod
    def _calculate_spread_metrics(spread: VerticalSpread, days_to_expiration: int) -> bool:
        logger.debug("Entering _calculate_spread_metrics")
        spread.net_premium = spread.get_net_premium()
        if spread.net_premium == 0 or spread.distance_between_strikes == 0:
            logger.warning("spread has zero invalide delta, indicating a potential error in the selection.")
        
        # Normalize relative delta calculation for both credit and debit spreads
        relative_delta = abs(spread.net_premium) / abs(spread.distance_between_strikes)
        
        # Validate relative delta threshold
        if relative_delta == Decimal(0) or relative_delta < spread.MIN_DELTA:
            logger.debug(f"Skipping second leg candidate due to relative delta {relative_delta} being less than minimum delta {spread.MIN_DELTA}.")
            return False

        # Calculate all other metrics - these handle negative net premium correctly already
        spread.max_reward = spread.get_max_reward()
        spread.max_risk = spread.get_max_risk()
        spread.breakeven = spread.get_breakeven_price()
        spread.target_price = spread.get_target_price()
        spread.stop_price = spread.get_stop_price()
        spread.entry_price = spread.previous_close
        spread.exit_date = spread.get_exit_date()
        spread.contract_type = spread.short_contract.contract_type
        spread.probability_of_profit = VerticalSpreadMatcher._calculate_probability_of_profit(spread, days_to_expiration)
        
        if spread.probability_of_profit is None:
            logger.warning("Probability of profit calculation failed.")
            logger.debug("Exiting _calculate_spread_metrics")
            return False

        spread.reward_risk_ratio = spread.max_reward / spread.max_risk if spread.max_risk != 0 else Decimal('0')
        
        logger.debug("Exiting _calculate_spread_metrics")
        return True

    @staticmethod
    def _calculate_probability_of_profit(spread: VerticalSpread, days_to_expiration: int) -> Optional[Decimal]:
        logger.debug("Entering _calculate_probability_of_profit")
        implied_volatility = spread.first_leg_snapshot.implied_volatility * spread.second_leg_snapshot.implied_volatility
        result = Options.calculate_probability_of_profit(spread.previous_close, spread.breakeven, days_to_expiration, implied_volatility)
        logger.debug("Exiting _calculate_probability_of_profit")
        return result

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
    def _calculate_adjusted_score(spread: VerticalSpread) -> Tuple[Optional[VerticalSpread], Optional[VerticalSpread], Optional[VerticalSpread]]:
        logger.debug("Entering _calculate_adjusted_score")
        # Combine confidence levels from legs and snapshots
        short_confidence = spread.short_contract.confidence_level
        long_confidence = spread.long_contract.confidence_level
        first_snapshot_confidence = spread.first_leg_snapshot.confidence_level
        second_snapshot_confidence = spread.second_leg_snapshot.confidence_level
        
        # Overall confidence is the product of individual confidences
        spread.confidence_level = short_confidence * long_confidence * first_snapshot_confidence * second_snapshot_confidence
        breakeven = spread.get_breakeven_price()
        if breakeven:
            price_diff_pct = abs((breakeven - spread.previous_close) / spread.previous_close)
            if price_diff_pct > spread.LARGE_MOVE_THRESHOLD:  # More than threshold move needed
                logger.warning(f"Breakeven requires large price move: {price_diff_pct*100:.1f}% from current price")
                # We'll reduce confidence for trades requiring large moves
                spread.confidence_level *= spread.CONFIDENCE_REDUCTION_FACTOR         

        spread.adjusted_score = Decimal(100)*((spread.reward_risk_ratio * Decimal(0.3)) + 
                                              ((spread.probability_of_profit/Decimal(100)) * Decimal(0.3)) +
                                              (spread.confidence_level * Decimal(0.4)))

        logger.info(f"Spread confidence calculation: short={short_confidence}, long={long_confidence}, " +
                    f"first_snapshot={first_snapshot_confidence}, second_snapshot={second_snapshot_confidence}, " +
                    f"confidence_level={spread.confidence_level}, "+
                    f"Adjusted Score: {spread.adjusted_score}")
                
        logger.debug("Exiting _calculate_adjusted_score")

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

    @staticmethod
    def _validate_spread_parameters(spread: VerticalSpread) -> bool:
        logger.debug("Entering _validate_spread_parameters")
        """Validate spread parameters to catch potential issues."""
            
        # Check for valid premiums
        if spread.short_premium is None or spread.long_premium is None:
            logger.error("Missing premium values")
            logger.debug("Exiting _validate_spread_parameters")
            return False

        # For credit spread, short premium should generally be higher than long premium
        # BUT this can be violated in some market conditions, especially with wide spreads
        if spread.strategy == StrategyType.CREDIT and spread.short_premium <= spread.long_premium:
            logger.error(f"Unusual credit spread: short premium ({spread.short_premium}) <= long premium ({spread.long_premium})")
            logger.debug("Exiting _validate_spread_parameters")
            return False
            
        # For debit spread, long premium should be higher than short premium
        # This is more strict - a debit spread should cost money (pay a debit)
        if spread.strategy == StrategyType.DEBIT and spread.long_premium <= spread.short_premium:
            logger.error(f"Unusual debit spread: long premium ({spread.long_premium}) <= short premium ({spread.short_premium})\n"+
                            f"Spread details: first_leg_contract={spread.first_leg_contract}, second_leg_contract={spread.second_leg_contract}, distance_between_strikes={spread.distance_between_strikes}")
            logger.debug("Exiting _validate_spread_parameters")
            return False
                
        # Check for extremely wide spreads compared to optimal width
        if spread.distance_between_strikes < spread.optimal_spread_width:
            logger.debug(f"Spread width ({spread.distance_between_strikes}) is less than the optimal width ({spread.optimal_spread_width})")
            # Reject spreads that are too narrow
            logger.debug("Exiting _validate_spread_parameters")
            return False

        # Check for extremely wide spreads compared to optimal width
        width_ratio = spread.distance_between_strikes / spread.optimal_spread_width
        if width_ratio > spread.EXTREME_WIDTH_RATIO:
            logger.debug(f"Spread width ({spread.distance_between_strikes}) is {width_ratio:.1f}x the optimal width ({spread.optimal_spread_width})")
            logger.debug("Exiting _validate_spread_parameters")
            return False
        
        logger.debug("Exiting _validate_spread_parameters")
        return True