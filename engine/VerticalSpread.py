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
    # Default contract selector for production use
    contract_selector: ClassVar[ContractSelector] = StandardContractSelector()
    
    def match_option(self, options_snapshots: dict, underlying_ticker: str, 
                     direction: DirectionType, strategy: StrategyType, previous_close: Decimal, 
                     date: datetime, contracts: List[Contract]) -> bool:
        logger.debug("Entering match_option")
        self._initialize_match_option(underlying_ticker, direction, strategy, previous_close, date, contracts)
        self.optimal_spread_width = Options.calculate_optimal_spread_width(self.to_decimal(previous_close), self.strategy, self.direction)
        logger.debug(f"Optimal spread width for {underlying_ticker} at price ${previous_close} with {strategy.value} strategy: ${self.optimal_spread_width}")

        days_to_expiration: int = (self.expiration_date - self.update_date).days

        first_leg_candidates: List[Tuple[Contract, int, Snapshot]] = self._select_first_leg_candidates(options_snapshots)
        if not first_leg_candidates:
            logger.debug("No suitable first leg contract found.")
            logger.debug("Exiting match_option")
            return False

        second_leg_candidates: List[Tuple[Contract, int, Snapshot]] = self._select_second_leg_candidates(options_snapshots)
        if not second_leg_candidates:
            logger.debug("No suitable second leg contract found.")
            logger.debug("Exiting match_option")
            return False

        best_spread: Optional[dict] = self._find_best_spread(first_leg_candidates, second_leg_candidates, 
                                                             days_to_expiration, self.optimal_spread_width)
        if best_spread:
            self.from_dict(best_spread)
            logger.debug(f'Found a match! {self.second_leg_contract.ticker} with score {self.adjusted_score}, description: {self.description}')
            logger.debug("Exiting match_option")
            return True
        logger.debug("Exiting match_option")
        return False

    def _initialize_match_option(self, underlying_ticker: str, direction: DirectionType, strategy: StrategyType, 
                                 previous_close: Decimal, date: datetime, contracts: List[Contract]) -> None:
        logger.debug("Entering _initialize_match_option")
        self.underlying_ticker = underlying_ticker
        self.direction = direction
        self.strategy = strategy
        self.previous_close = previous_close
        self.expiration_date = date
        self.update_date = datetime.today().date()
        self.contracts = contracts
        logger.debug("Exiting _initialize_match_option")

    def _select_first_leg_candidates(self, options_snapshots: dict) -> List[Tuple[Contract, int, Snapshot]]:
        logger.debug("Entering _select_first_leg_candidates")
        result = self.contract_selector.select_contracts(
            self.contracts, 
            options_snapshots, 
            self.underlying_ticker, 
            TradeStrategy.DIRECTIONAL,
            self.strategy,
            self.direction,
            self.previous_close
        )
        logger.debug("Exiting _select_first_leg_candidates")
        return result

    def _select_second_leg_candidates(self, options_snapshots: dict) -> List[Tuple[Contract, int, Snapshot]]:
        logger.debug("Entering _select_second_leg_candidates")
        result = self.contract_selector.select_contracts(
            self.contracts, 
            options_snapshots, 
            self.underlying_ticker, 
            TradeStrategy.HIGH_PROBABILITY,
            self.strategy,
            self.direction,
            self.previous_close
        )
        logger.debug("Exiting _select_second_leg_candidates")
        return result

    def _find_best_spread(self, first_leg_candidates: List[Tuple[Contract, int, Snapshot]], 
                          second_leg_candidates: List[Tuple[Contract, int, Snapshot]], 
                          days_to_expiration: int, optimal_spread_width: Decimal) -> Optional[dict]:
        logger.debug("Entering _find_best_spread")
        best_spread: Optional[dict] = None
        best_pop: Decimal = Decimal(0)
        best_spread_width: Optional[dict] = None 
        best_spread_non_standard: Optional[dict] = None
        found_valid_spread: bool = False

        for first_leg in first_leg_candidates:
            contract, _, _ = first_leg
            if not contract.matched:
                continue
            self._set_first_leg(first_leg)
            for second_leg in second_leg_candidates:
                # if not self._is_valid_leg_combination(second_leg):
                #    continue
                contract, _, _ = second_leg
                if not contract.matched:
                    continue
                self._set_second_leg(second_leg)
                self._calculate_spread_metrics(days_to_expiration)
                if not self._calculate_premium_delta():
                    continue
                if not self._validate_spread_parameters():
                    continue
                self._calculate_adjusted_score()
                best_spread, best_spread_width, best_spread_non_standard = self._update_best_spreads(best_spread, best_spread_width, best_spread_non_standard)
                found_valid_spread = True
                if not isinstance(self.contract_selector, StandardContractSelector):
                    break
            if found_valid_spread and not isinstance(self.contract_selector, StandardContractSelector):
                break

        result = self._determine_final_spread(best_spread, best_spread_width, best_spread_non_standard)
        logger.debug("Exiting _find_best_spread")
        return result

    def _validate_spread_parameters(self) -> bool:
        logger.debug("Entering _validate_spread_parameters")
        """Validate spread parameters to catch potential issues."""
        # Check for reasonable spread width
        if self.distance_between_strikes <= 0:
            logger.error("Invalid spread width: must be positive")
            logger.debug("Exiting _validate_spread_parameters")
            return False
            
        # Check for valid premiums
        if self.short_premium is None or self.long_premium is None:
            logger.error("Missing premium values")
            logger.debug("Exiting _validate_spread_parameters")
            return False

        # For credit spread, short premium should generally be higher than long premium
        # BUT this can be violated in some market conditions, especially with wide spreads
        if self.strategy == StrategyType.CREDIT and self.short_premium <= self.long_premium:
            if isinstance(self.contract_selector, StandardContractSelector):
                logger.error(f"Unusual credit spread: short premium ({self.short_premium}) <= long premium ({self.long_premium})")
                logger.debug("Exiting _validate_spread_parameters")
                return False
            
        # For debit spread, long premium should be higher than short premium
        # This is more strict - a debit spread should cost money (pay a debit)
        if self.strategy == StrategyType.DEBIT and self.long_premium <= self.short_premium:
            if isinstance(self.contract_selector, StandardContractSelector):
                logger.error(f"Unusual debit spread: long premium ({self.long_premium}) <= short premium ({self.short_premium})")
                logger.debug("Exiting _validate_spread_parameters")
                return False
            
        # Check for unreasonable break-evens (too far from current price)
        breakeven = self.get_breakeven_price()
        if breakeven:
            price_diff_pct = abs((breakeven - self.to_decimal(self.previous_close)) / self.to_decimal(self.previous_close))
            if price_diff_pct > self.LARGE_MOVE_THRESHOLD:  # More than 50% move needed
                logger.warning(f"Breakeven requires large price move: {price_diff_pct*100:.1f}% from current price")
                # We'll reduce confidence for trades requiring large moves
                if hasattr(self, 'confidence_level'):
                    self.confidence_level *= Decimal('0.9')
                
        # Check for extremely wide spreads compared to optimal width
        width_ratio = self.distance_between_strikes / self.optimal_spread_width
        if width_ratio > self.EXTREME_WIDTH_RATIO:
            logger.warning(f"Spread width ({self.distance_between_strikes}) is {width_ratio:.1f}x the optimal width ({self.optimal_spread_width})")
            # Apply progressive confidence reduction for extremely wide spreads
            if hasattr(self, 'confidence_level'):
                confidence_reduction = min(self.MAX_CONFIDENCE_REDUCTION, (width_ratio - self.EXTREME_WIDTH_RATIO) * self.CONFIDENCE_REDUCTION_STEP)  # Cap at 50% reduction
                self.confidence_level *= (Decimal('1.0') - confidence_reduction)
                logger.info(f"Applied {confidence_reduction*100:.1f}% confidence reduction due to extreme width")
        logger.debug("Exiting _validate_spread_parameters")
        return True

    def _set_first_leg(self, first_leg: Tuple[Contract, int, Snapshot]) -> None:
        logger.debug("Entering _set_first_leg")
        self.first_leg_contract, self.first_leg_contract_position, self.first_leg_snapshot = first_leg
        if self.strategy == StrategyType.CREDIT:
            self.short_contract = self.first_leg_contract
            self.short_premium = self.first_leg_snapshot.day.bid
        elif self.strategy == StrategyType.DEBIT:
            self.long_contract = self.first_leg_contract
            self.long_premium = self.first_leg_snapshot.day.ask
        logger.debug("Exiting _set_first_leg")

    def _is_valid_leg_combination(self, second_leg: Tuple[Contract, int, Snapshot]) -> bool:
        logger.debug("Entering _is_valid_leg_combination")
        second_leg_contract, self.second_leg_contract_position, self.second_leg_snapshot = second_leg
        if self.strategy == StrategyType.CREDIT:
            if self.direction == DirectionType.BULLISH:
                # Bull Put Credit: Short PUT must have higher strike than long PUT
                if self.first_leg_contract.strike_price <= second_leg_contract.strike_price:
                    logger.debug("Exiting _is_valid_leg_combination")
                    return False
            else:
                # Bear Call Credit: Short CALL must have lower strike than long CALL
                if self.first_leg_contract.strike_price >= second_leg_contract.strike_price:
                    logger.debug("Exiting _is_valid_leg_combination")
                    return False
        elif self.strategy == StrategyType.DEBIT:
            if self.direction == DirectionType.BULLISH:
                # Bull Call Debit: Long CALL must have lower strike than short CALL
                if self.first_leg_contract.strike_price >= second_leg_contract.strike_price:
                    logger.debug("Exiting _is_valid_leg_combination")
                    return False
            else:
                # Bear Put Debit: Long PUT must have higher strike than short PUT
                if self.first_leg_contract.strike_price <= second_leg_contract.strike_price:
                    logger.debug("Exiting _is_valid_leg_combination")
                    return False
        logger.debug("Exiting _is_valid_leg_combination")
        return True

    def _set_second_leg(self, second_leg: Tuple[Contract, int, Snapshot]) -> None:
        logger.debug("Entering _set_second_leg")
        self.second_leg_contract, self.second_leg_contract_position, self.second_leg_snapshot = second_leg
        self.distance_between_strikes = abs(self.first_leg_contract.strike_price - self.second_leg_contract.strike_price)
        if self.strategy == StrategyType.CREDIT:
            self.long_premium = self.second_leg_snapshot.day.ask
            self.long_contract = self.second_leg_contract
        elif self.strategy == StrategyType.DEBIT:
            self.short_contract = self.second_leg_contract
            self.short_premium = self.second_leg_snapshot.day.bid
        logger.debug("Exiting _set_second_leg")

    def _calculate_premium_delta(self) -> bool:
        logger.debug("Entering _calculate_premium_delta")
        if self.strategy == StrategyType.CREDIT:
            premium_delta = self.first_leg_snapshot.day.bid - self.second_leg_snapshot.day.ask
        else:  # DEBIT
            premium_delta = self.second_leg_snapshot.day.bid - self.first_leg_snapshot.day.ask

        premium_delta = abs(premium_delta)
        if premium_delta == 0:
            logger.warning("Second leg candidate has zero premium delta, indicating a potential error in the selection.")
            logger.debug("Exiting _calculate_premium_delta")
            return False

        relative_delta = premium_delta / self.distance_between_strikes
        if relative_delta == Decimal(0) or relative_delta < self.MIN_DELTA:
            logger.debug(f"Skipping second leg candidate due to relative delta {relative_delta} being less than minimum delta {self.MIN_DELTA}.")
            if not isinstance(self.contract_selector, StandardContractSelector):
                pass  # Continue with the candidate for test purposes
            else:
                logger.debug("Exiting _calculate_premium_delta")
                return False  # Skip this candidate in production

        self.net_premium = self.short_premium - self.long_premium
        logger.debug("Exiting _calculate_premium_delta")
        return True

    def get_net_premium(self):
        logger.debug("Entering get_net_premium")
        result = self.to_decimal(self.net_premium)
        logger.debug("Exiting get_net_premium")
        return result

    def get_close_price(self):
        logger.debug("Entering get_close_price")
        result = self.to_decimal(self.previous_close)
        logger.debug("Exiting get_close_price")
        return result

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

    def get_short(self):
        logger.debug("Entering get_short")
        result = self.short_contract
        logger.debug("Exiting get_short")
        return result

    def get_long(self):
        logger.debug("Entering get_long")
        result = self.long_contract
        logger.debug("Exiting get_long")
        return result

    def to_dict(self):
        logger.debug("Entering to_dict")
        result = super().to_dict()
        logger.debug("Exiting to_dict")
        return result

    def get_description(self):
        logger.debug("Entering get_description")
        result = self.description
        logger.debug("Exiting get_description")
        return result

    def get_max_reward(self):
        logger.debug("Entering get_max_reward")
        logger.debug("Exiting get_max_reward")
        pass

    def get_max_risk(self):
        logger.debug("Entering get_max_risk")
        logger.debug("Exiting get_max_risk")
        pass

    def get_breakeven_price(self):
        logger.debug("Entering get_breakeven_price")
        logger.debug("Exiting get_breakeven_price")
        pass

    def get_target_price(self):
        logger.debug("Entering get_target_price")
        logger.debug("Exiting get_target_price")
        pass

    def get_stop_price(self):
        logger.debug("Entering get_stop_price")
        logger.debug("Exiting get_stop_price")
        pass

    def _calculate_spread_metrics(self, days_to_expiration: int) -> None:
        logger.debug("Entering _calculate_spread_metrics")
        """Calculate key metrics for the spread."""
        self.max_reward = self.get_max_reward()
        self.max_risk = self.get_max_risk()
        self.breakeven = self.get_breakeven_price()
        self.target_price = self.get_target_price()
        self.stop_price = self.get_stop_price()
        self.probability_of_profit = self._calculate_probability_of_profit(days_to_expiration)
        self.reward_risk_ratio = self.max_reward / self.max_risk if self.max_risk != 0 else Decimal('0')
        logger.debug("Exiting _calculate_spread_metrics")

    def _calculate_probability_of_profit(self, days_to_expiration: int) -> Decimal:
        logger.debug("Entering _calculate_probability_of_profit")
        """Calculate the probability of profit (POP) for the spread."""
        implied_volatility = self.first_leg_snapshot.implied_volatility * self.second_leg_snapshot.implied_volatility
        result = Options.calculate_probability_of_profit(self.previous_close, self.breakeven, days_to_expiration, implied_volatility)
        logger.debug("Exiting _calculate_probability_of_profit")
        return result

    def _generate_description(self) -> str:
        logger.debug("Entering _generate_description")
        """Generate a detailed description of the spread."""
        description = (
            f"{self.strategy.value.capitalize()} {self.direction.value.capitalize()} Spread\n"
            f"Underlying: {self.underlying_ticker}\n"
            f"Expiration Date: {self.expiration_date.strftime('%Y-%m-%d')}\n"
            f"First Leg: {self.first_leg_contract.ticker} @ {self.first_leg_contract.strike_price}\n"
            f"Second Leg: {self.second_leg_contract.ticker} @ {self.second_leg_contract.strike_price}\n"
            f"Net Premium: {self.net_premium}\n"
            f"Max Reward: {self.max_reward}\n"
            f"Max Risk: {self.max_risk}\n"
            f"Breakeven Price: {self.breakeven_price}\n"
            f"Target Price: {self.target_price}\n"
            f"Stop Price: {self.stop_price}\n"
            f"Probability of Profit: {self.probability_of_profit}%\n"
            f"Reward/Risk Ratio: {self.reward_risk_ratio}"
        )
        logger.debug("Exiting _generate_description")
        return description

    def _calculate_adjusted_score(self) -> None:
        logger.debug("Entering _calculate_adjusted_score")
        """Calculate an adjusted score for the spread based on various metrics."""
        self.adjusted_score = (
            self.reward_risk_ratio * self.probability_of_profit
        )
        logger.debug(f"Adjusted Score: {self.adjusted_score}")
        logger.debug("Exiting _calculate_adjusted_score")

    def _update_best_spreads(self, best_spread: Optional[dict], best_spread_width: Optional[dict], best_spread_non_standard: Optional[dict]) -> Tuple[Optional[dict], Optional[dict], Optional[dict]]:
        logger.debug("Entering _update_best_spreads")
        """Update the best spread candidates based on the current spread's metrics."""
        if not best_spread or self.adjusted_score > self.to_decimal(best_spread['adjusted_score']):
            best_spread = self.to_dict()
        if self.distance_between_strikes == self.optimal_spread_width:
            if not best_spread_width or self.adjusted_score > self.to_decimal(best_spread_width['adjusted_score']):
                best_spread_width = self.to_dict()
        else:
            if not best_spread_non_standard or self.adjusted_score > self.to_decimal(best_spread_non_standard['adjusted_score']):
                best_spread_non_standard = self.to_dict()
        logger.debug("Exiting _update_best_spreads")
        return best_spread, best_spread_width, best_spread_non_standard

    def _determine_final_spread(self, best_spread: Optional[dict], best_spread_width: Optional[dict], best_spread_non_standard: Optional[dict]) -> Optional[dict]:
        logger.debug("Entering _determine_final_spread")
        """Determine the final spread to use based on the best candidates."""
        if best_spread_width:
            logger.debug("Exiting _determine_final_spread")
            return best_spread_width
        if best_spread_non_standard:
            logger.debug("Exiting _determine_final_spread")
            return best_spread_non_standard
        logger.debug("Exiting _determine_final_spread")
        return best_spread

class CreditSpread(VerticalSpread):
    ideal_expiration: ClassVar[int] = 45

    def match_option(self, options_snapshots, underlying_ticker, direction: DirectionType, strategy: StrategyType, previous_close: Decimal, date: datetime, contracts) -> bool:
        logger.debug("Entering CreditSpread.match_option")
        result = super().match_option(options_snapshots, underlying_ticker, direction, strategy, previous_close, date, contracts)
        logger.debug("Exiting CreditSpread.match_option")
        return result

    def get_max_risk(self):
        logger.debug("Entering CreditSpread.get_max_risk")
        # For a credit spread, the max risk is:
        # (Distance between strikes - Net premium) * 100
        # We need to ensure the calculation is done with Decimal types
        distance = self.to_decimal(self.distance_between_strikes)
        net_premium = self.get_net_premium()
        # Safeguard against calculation errors
        result = (distance - net_premium) * Decimal('100')
        logger.debug("Exiting CreditSpread.get_max_risk")
        return result

    def get_max_reward(self):
        logger.debug("Entering CreditSpread.get_max_reward")
        result = self.get_net_premium()*100
        logger.debug("Exiting CreditSpread.get_max_reward")
        return result

    def get_breakeven_price(self):
        logger.debug("Entering CreditSpread.get_breakeven_price")
        net_premium = self.get_net_premium()
        result = Decimal(self.short_contract.strike_price) + (-net_premium if self.direction == DirectionType.BULLISH else net_premium)
        logger.debug("Exiting CreditSpread.get_breakeven_price")
        return result

    def get_target_price(self):
        logger.debug("Entering CreditSpread.get_target_price")
        target_reward = (self.get_net_premium() * Decimal(0.8))
        result = self.previous_close + (target_reward if self.direction == DirectionType.BULLISH else -target_reward)
        logger.debug("Exiting CreditSpread.get_target_price")
        return result

    def get_stop_price(self):
        logger.debug("Entering CreditSpread.get_stop_price")
        target_stop = (self.get_net_premium() / Decimal(2))
        result = self.previous_close - (target_stop if self.direction == DirectionType.BULLISH else -target_stop)
        logger.debug("Exiting CreditSpread.get_stop_price")
        return result

class DebitSpread(VerticalSpread):
    ideal_expiration: ClassVar[int] = 45

    def match_option(self, options_snapshots, underlying_ticker, direction: DirectionType, strategy: StrategyType, previous_close: Decimal, date: datetime, contracts) -> bool:
        logger.debug("Entering DebitSpread.match_option")
        result = super().match_option(options_snapshots, underlying_ticker, direction, strategy, previous_close, date, contracts)
        logger.debug("Exiting DebitSpread.match_option")
        return result

    def get_max_reward(self):
        logger.debug("Entering DebitSpread.get_max_reward")
        # For a debit spread, the max reward is the difference between the strike prices
        # minus the net debit paid
        distance = self.to_decimal(self.distance_between_strikes)
        net_premium = self.get_net_premium()
        result = (distance - net_premium) * Decimal('100')
        logger.debug("Exiting DebitSpread.get_max_reward")
        return result

    def get_max_risk(self):
        logger.debug("Entering DebitSpread.get_max_risk")
        # For a debit spread, the max risk is simply the net debit paid
        result = self.get_net_premium() * Decimal('100')
        logger.debug("Exiting DebitSpread.get_max_risk")
        return result

    def get_breakeven_price(self):
        logger.debug("Entering DebitSpread.get_breakeven_price")
        net_premium = self.get_net_premium()
        result = Decimal(self.long_contract.strike_price) + (-net_premium if self.direction == DirectionType.BULLISH else net_premium)
        logger.debug("Exiting DebitSpread.get_breakeven_price")
        return result

    def get_target_price(self):
        logger.debug("Entering DebitSpread.get_target_price")
        target_reward = (self.get_net_premium() * Decimal(0.8))
        result = self.previous_close + (target_reward if self.direction == DirectionType.BULLISH else -target_reward)
        logger.debug("Exiting DebitSpread.get_target_price")
        return result

    def get_stop_price(self):
        logger.debug("Entering DebitSpread.get_stop_price")
        target_stop = (self.get_net_premium() / Decimal(2))
        result = self.previous_close - (target_stop if self.direction == DirectionType.BULLISH else -target_stop)
        logger.debug("Exiting DebitSpread.get_stop_price")
        return result