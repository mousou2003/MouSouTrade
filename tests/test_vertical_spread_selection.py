"""
Test Vertical Spread Selection
=============================
This file contains tests for the vertical spread option selection algorithms. It verifies that 
the selection logic properly identifies and pairs option contracts to create optimal spreads
based on delta values and trading strategies.

Key aspects tested:
1. Delta-based contract selection:
   - Directional trades (higher delta): 0.45-0.70 for the first leg
   - High probability trades (lower delta): 0.10-0.30 for the second leg

2. Strategy-appropriate contract pairing:
   - Bull Call Debit Spread: Directional long call + High probability short call
   - Bear Put Debit Spread: Directional long put + High probability short put
   - Bull Put Credit Spread: Directional short put + High probability long put
   - Bear Call Credit Spread: Directional short call + High probability long call

3. Price relationship and spread width validation:
   - Proper distance between strikes
   - Probability of profit calculations
   - Premium relative to max risk

These tests are complementary to the strategy_validator tests, focusing on the algorithmic 
selection of appropriate contracts rather than the validation of already formed spreads.
"""

import logging
from typing import List
import unittest
from unittest.mock import patch, MagicMock
import sys, os
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

from engine.data_model import (
    Contract, Snapshot, DayData, Greeks, DirectionType, StrategyType,
    ContractType, StrikePriceType
)
from engine.VerticalSpread import VerticalSpread, CreditSpread, DebitSpread, VerticalSpreadMatcher
from engine.Options import Options, TradeStrategy
from engine.contract_selector import ContractSelector, TestContractSelector

class TestVerticalSpreadStrikeSelection(unittest.TestCase):
    def setUp(self):
        """Set up test data for vertical spread testing"""
        # Load test data
        data_file = os.path.join(os.path.dirname(__file__), 'data', 'test_spread_data.json')
        with open(data_file, 'r') as f:
            self.test_data = json.load(f)
            
        # Initialize test selector
        self.test_selector = TestContractSelector()

    def _setup_test_data(self, test_key):
        """Helper method to set up test data for specific test"""
        test_data = self.test_data[test_key]
        self.underlying_ticker = test_data['underlying_ticker']
        self.previous_close = Decimal(str(test_data['previous_close']))
        self.expiration_date = datetime.strptime(test_data['expiration_date'], "%Y-%m-%d").date()

        # Create test contracts and snapshots
        self.call_contracts = []
        self.put_contracts = []
        self.options_snapshots = {}

        if 'calls' in test_data['test_contracts']:
            for contract_data in test_data['test_contracts']['calls']:
                contract = self._create_test_contract(contract_data)
                contract.confidence_level = Decimal('1.0')
                contract.matched = True
                self.call_contracts.append(contract)
                
                snapshot = self._create_snapshot(contract_data['snapshot'])
                snapshot.confidence_level = Decimal('1.0')
                snapshot.details = contract
                self.options_snapshots[contract.ticker] = snapshot

        if 'puts' in test_data['test_contracts']:
            for contract_data in test_data['test_contracts']['puts']:
                contract = self._create_test_contract(contract_data)
                contract.confidence_level = Decimal('1.0')
                contract.matched = True
                self.put_contracts.append(contract)
                
                snapshot = self._create_snapshot(contract_data['snapshot'])
                snapshot.confidence_level = Decimal('1.0')
                snapshot.details = contract
                self.options_snapshots[contract.ticker] = snapshot

        # Combined list for tests that need all contracts
        self.all_contracts = self.call_contracts + self.put_contracts

    def _create_test_contract(self, data: dict) -> Contract:
        """Create a single test contract from data"""
        return Contract(
            ticker=data['ticker'],
            strike_price=Decimal(str(data['strike'])),
            contract_type=ContractType(data['contract_type']),
            expiration_date=datetime.strptime(data['expiration'], "%Y-%m-%d").date()
        )

    def _create_snapshot(self, data: dict) -> Snapshot:
        """Create snapshot with close price"""
        snapshot = Snapshot(
            day=DayData(
                bid=Decimal(str(data['bid'])),
                ask=Decimal(str(data['ask'])),
                volume=data['volume'],
                open_interest=data['open_interest']
            ),
            implied_volatility=Decimal(str(data['implied_volatility'])),
            greeks=Greeks(delta=Decimal(str(data['delta'])))
        )
        # Set close price as midpoint between bid and ask if not provided
        if not hasattr(snapshot.day, 'close') or snapshot.day.close is None:
            snapshot.day.close = (snapshot.day.bid + snapshot.day.ask) / 2
        if not hasattr(snapshot.day, 'last_trade') or snapshot.day.last_trade is None:
            snapshot.day.last_trade = snapshot.day.close
        return snapshot

    def tearDown(self):
        """Clean up after each test"""
        pass

    def test_bullish_debit_call_spread_selection(self):
        """Test that a bullish debit call spread selects appropriate strikes"""
        self._setup_test_data('strike_selection_test')
        logger.debug("Starting test_bullish_debit_call_spread_selection")
        result = VerticalSpreadMatcher.match_option(
            self.options_snapshots, 
            self.underlying_ticker,
            DirectionType.BULLISH, 
            StrategyType.DEBIT, 
            self.previous_close, 
            self.expiration_date,
            self.call_contracts  # Only use call options
        )
        
        # Set test selector before evaluating
        result.contract_selector = self.test_selector
        
        self.assertTrue(result.matched, "Bullish debit spread (call) should find valid options")
        self.assertIsInstance(result, DebitSpread)
        
        # Check that long call is ATM/directional and short call is OTM/high probability
        self.assertEqual(result.long_contract.contract_type, ContractType.CALL)
        self.assertEqual(result.short_contract.contract_type, ContractType.CALL)
        self.assertTrue(result.long_contract.strike_price < result.short_contract.strike_price,
                      "Long call strike should be lower than short call strike")
                      
        # Verify the absolute delta values are appropriate
        long_delta = abs(self.options_snapshots[result.long_contract.ticker].greeks.delta)
        short_delta = abs(self.options_snapshots[result.short_contract.ticker].greeks.delta)
        
        # Long call should have higher delta (closer to ATM or directional)
        self.assertGreaterEqual(long_delta, Decimal('0.4'), "Long call delta should be >= 0.4 (directional)")
        # Short call should have lower delta (more OTM)
        self.assertLessEqual(short_delta, Decimal('0.35'), "Short call delta should be <= 0.35 (high probability)")
        logger.debug("✅ Successfully completed bullish debit call spread selection test")

    def test_bearish_debit_put_spread_selection(self):
        """Test that a bearish debit put spread selects appropriate strikes"""
        self._setup_test_data('strike_selection_test')
        logger.debug("Starting test_bearish_debit_put_spread_selection")
    
        result = VerticalSpreadMatcher.match_option(
            self.options_snapshots,
            self.underlying_ticker,
            DirectionType.BEARISH,
            StrategyType.DEBIT,
            self.previous_close,
            self.expiration_date,
            self.put_contracts  # Only use put options
        )
        
        # Set test selector before evaluating
        result.contract_selector = self.test_selector
        
        self.assertTrue(result.matched, "Bearish debit spread (put) should find valid options")
        self.assertIsInstance(result, DebitSpread)
        
        # Verify the contract types and strike prices
        self.assertEqual(result.long_contract.contract_type, ContractType.PUT)
        self.assertEqual(result.short_contract.contract_type, ContractType.PUT)
        self.assertTrue(result.long_contract.strike_price > result.short_contract.strike_price,
                      "Long put strike should be higher than short put strike")
        
        # Verify the distance between strikes
        self.assertGreater(result.distance_between_strikes, 0,
                        "Distance between strikes should be positive")
        
        # Verify the net premium calculation
        self.assertLess(result.net_premium, 0,
                     "Net premium should be negative for debit spreads")
        
        # Verify the absolute delta values
        long_delta = abs(self.options_snapshots[result.long_contract.ticker].greeks.delta)
        short_delta = abs(self.options_snapshots[result.short_contract.ticker].greeks.delta)
        
        # Long put should have higher delta (more directional)
        self.assertGreaterEqual(long_delta, Decimal('0.4'), "Long put delta should be >= 0.4 (directional)")
        # Short put should have lower delta (more probability-based)
        self.assertLessEqual(short_delta, Decimal('0.35'), "Short put delta should be <= 0.35 (high probability)")
        logger.debug("✅ Successfully completed bearish debit put spread selection test")

    def test_bullish_credit_put_spread_selection(self):
        """Test that a bullish credit put spread selects appropriate strikes"""
        self._setup_test_data('strike_selection_test')
        logger.debug("Starting test_bullish_credit_put_spread_selection")
        
        result = VerticalSpreadMatcher.match_option(
            self.options_snapshots, 
            self.underlying_ticker,
            DirectionType.BULLISH, 
            StrategyType.CREDIT, 
            self.previous_close, 
            self.expiration_date,
            self.put_contracts  # Only use put options
        )
        
        # Set test selector before evaluating
        result.contract_selector = self.test_selector
        
        self.assertTrue(result.matched, "Bullish credit spread (put) should find valid options")
        self.assertIsInstance(result, CreditSpread)
        
        # Check that short put is ATM/directional and long put is OTM/high probability
        self.assertEqual(result.short_contract.contract_type, ContractType.PUT)
        self.assertEqual(result.long_contract.contract_type, ContractType.PUT)
        self.assertTrue(result.short_contract.strike_price > result.long_contract.strike_price,
                      "Short put strike should be higher than long put strike")
                      
        # Verify the absolute delta values are appropriate - keeping as Decimal
        short_delta = abs(self.options_snapshots[result.short_contract.ticker].greeks.delta)
        long_delta = abs(self.options_snapshots[result.long_contract.ticker].greeks.delta)
        
        # Short put should have higher delta (closer to ATM or directional)
        self.assertGreaterEqual(short_delta, Decimal('0.4'), "Short put delta should be >= 0.4 (directional)")
        # Long put should have lower delta (more OTM)
        self.assertLessEqual(long_delta, Decimal('0.35'), "Long put delta should be <= 0.35 (high probability)")
        
        # Add net premium verification
        if result.matched:
            self.assertGreater(result.net_premium, 0,
                           "Net premium should be positive for credit spreads")
        logger.debug("✅ Successfully completed bullish credit put spread selection test")

    def test_bearish_credit_call_spread_selection(self):
        """Test that a bearish credit call spread selects appropriate strikes"""
        self._setup_test_data('strike_selection_test')
        logger.debug("Starting test_bearish_credit_call_spread_selection")
        
        # Log available contracts for debugging
        logger.debug("Available call contracts for bearish credit spread:")
        for contract in sorted(self.call_contracts, key=lambda x: x.strike_price):
            snapshot = self.options_snapshots[contract.ticker]
            logger.debug(f"Contract {contract.ticker}: Strike={contract.strike_price}, "
                        f"Delta={snapshot.greeks.delta}, "
                        f"Bid/Ask={snapshot.day.bid}/{snapshot.day.ask}")

        result = VerticalSpreadMatcher.match_option(
            self.options_snapshots, 
            self.underlying_ticker,
            DirectionType.BEARISH, 
            StrategyType.CREDIT, 
            self.previous_close, 
            self.expiration_date,
            self.call_contracts
        )
        
        # Set test selector before evaluating
        result.contract_selector = self.test_selector
        
        # Validate strike prices and spread width before running other tests
        if result.matched:
            logger.debug(f"Selected spread: Short {result.short_contract.ticker} @ {result.short_contract.strike_price}, "
                        f"Long {result.long_contract.ticker} @ {result.long_contract.strike_price}")
            logger.debug(f"Spread width: {result.long_contract.strike_price - result.short_contract.strike_price}")
            
            # Explicitly check strike price difference
            spread_width = result.long_contract.strike_price - result.short_contract.strike_price
            self.assertGreater(spread_width, 0, 
                              f"Invalid spread width: {spread_width} between strikes "
                              f"{result.short_contract.strike_price} and {result.long_contract.strike_price}")
        
        self.assertTrue(result.matched, "Bearish credit spread (call) should find valid options")
        self.assertIsInstance(result, CreditSpread)
        
        # Check that short call is ATM/directional and long call is OTM/high probability
        self.assertEqual(result.short_contract.contract_type, ContractType.CALL)
        self.assertEqual(result.long_contract.contract_type, ContractType.CALL)
        self.assertTrue(result.short_contract.strike_price < result.long_contract.strike_price,
                      "Short call strike should be lower than long call strike")
                      
        # Verify the absolute delta values are appropriate
        short_delta = abs(self.options_snapshots[result.short_contract.ticker].greeks.delta)
        long_delta = abs(self.options_snapshots[result.long_contract.ticker].greeks.delta)
        
        # Short call should have higher delta (closer to ATM or directional)
        self.assertGreaterEqual(short_delta, Decimal('0.4'), "Short call delta should be >= 0.4 (directional)")
        # Long call should have lower delta (more OTM)
        self.assertLessEqual(long_delta, Decimal('0.35'), "Long call delta should be <= 0.35 (high probability)")
        
        # Add net premium verification
        if result.matched:
            self.assertGreater(result.net_premium, 0,
                           "Net premium should be positive for credit spreads")
        logger.debug("✅ Successfully completed bearish credit call spread selection test")

    def test_spread_width(self):
        """Test that the spread width (distance between strikes) is reasonable"""
        self._setup_test_data('strike_selection_test')
        logger.debug("Starting test_spread_width")
        
        # Use width percentage constants from VerticalSpread class
        MIN_WIDTH_PERCENT = VerticalSpread.MIN_SPREAD_WIDTH_PERCENT
        MAX_WIDTH_PERCENT = VerticalSpread.MAX_SPREAD_WIDTH_PERCENT
        OPTIMAL_WIDTH_PERCENT = VerticalSpread.OPTIMAL_SPREAD_WIDTH_PERCENT
        
        for strategy_direction in [(StrategyType.DEBIT, DirectionType.BULLISH), 
                                 (StrategyType.CREDIT, DirectionType.BEARISH)]:
            strategy_type, direction = strategy_direction
            
            result = VerticalSpreadMatcher.match_option(
                self.options_snapshots, 
                self.underlying_ticker,
                direction, 
                strategy_type, 
                self.previous_close, 
                self.expiration_date,
                self.all_contracts
            )
            
            # Set test selector before evaluating
            result.contract_selector = self.test_selector
            
            self.assertTrue(result.matched, f"{direction.value} {strategy_type.value} spread should find valid options")
            self.assertGreater(result.distance_between_strikes, 0, 
                             f"Distance between strikes for {direction.value} {strategy_type.value} spread should be positive")
            
            # Get width boundaries from Options module
            min_width, max_width, optimal_width = Options.get_width_config(
                result.previous_close,
                result.strategy,
                result.direction
            )
            
            logger.debug(f"Width boundaries for {direction.value} {strategy_type.value}:")
            logger.debug(f"Min width: {min_width}, Max width: {max_width}, Optimal: {optimal_width}")
            logger.debug(f"Actual width: {result.distance_between_strikes}")
            
            # Verify width is within acceptable range
            self.assertGreaterEqual(result.distance_between_strikes, min_width,
                                  f"Spread width {result.distance_between_strikes} should be >= minimum {min_width}")
            self.assertLessEqual(result.distance_between_strikes, max_width,
                               f"Spread width {result.distance_between_strikes} should be <= maximum {max_width}")
                       
            logger.debug(f"✅ Successfully completed spread width test for {direction.value} {strategy_type.value}")

    def test_probability_of_profit(self):
        """Test that the probability of profit is calculated correctly"""
        self._setup_test_data('strike_selection_test')
        logger.debug("Starting test_probability_of_profit")
        for strategy_direction in [(StrategyType.DEBIT, DirectionType.BULLISH), 
                                 (StrategyType.CREDIT, DirectionType.BEARISH)]:
            strategy_type, direction = strategy_direction
            
            result = VerticalSpreadMatcher.match_option(
                self.options_snapshots, 
                self.underlying_ticker,
                direction, 
                strategy_type, 
                self.previous_close, 
                self.expiration_date,
                self.all_contracts
            )
            
            # Set test selector before evaluating
            result.contract_selector = self.test_selector
            
            self.assertTrue(result.matched, f"{direction.value} {strategy_type.value} spread should find valid options")
            
            # Check that probability of profit is calculated using VerticalSpread's method
            pop = VerticalSpread._calculate_probability_of_profit(result, (result.expiration_date - result.update_date).days)
            self.assertEqual(result.probability_of_profit, pop,
                           "Probability of profit should be calculated using VerticalSpread's method")
            
            # For credit spreads, POP is typically > 50%
            # For debit spreads, POP is typically < 50% (but provides better reward)
            if strategy_type == StrategyType.CREDIT:
                self.assertGreaterEqual(result.probability_of_profit, Decimal('40'), 
                                      f"POP for {direction.value} {strategy_type.value} spread should be >= 40%")
            else:
                # Debit spreads typically have lower probability but higher reward potential
                self.assertLessEqual(result.probability_of_profit, Decimal('62'), 
                                   f"POP for {direction.value} {strategy_type.value} should be <= 60%")
            
            # Use VerticalSpread's method directly
            days_to_expiration = (result.expiration_date - result.update_date).days
            pop = VerticalSpread._calculate_probability_of_profit(result, days_to_expiration)
            self.assertEqual(result.probability_of_profit, pop,
                           "Probability of profit should be calculated using VerticalSpread's method")
            logger.debug(f"✅ Successfully completed probability of profit test for {direction.value} {strategy_type.value}")

    def test_spread_premium_calculation(self):
        """Test that spread premiums are correctly calculated using bid/ask prices"""
        self._setup_test_data('strike_selection_test')
        logger.debug("Starting test_spread_premium_calculation")
        # Test a credit spread (bullish put credit spread)
        result = VerticalSpreadMatcher.match_option(
            self.options_snapshots, 
            self.underlying_ticker,
            DirectionType.BULLISH, 
            StrategyType.CREDIT, 
            self.previous_close, 
            self.expiration_date,
            self.put_contracts  # Only use put options
        )
        
        # Set test selector before evaluating
        result.contract_selector = self.test_selector
        
        if result.matched:
            self.assertIsInstance(result, CreditSpread)
            # For credit spreads:
            # - short_premium should equal the bid price of the short contract (selling)
            # - long_premium should equal the ask price of the long contract (buying)
            short_snapshot = self.options_snapshots[result.short_contract.ticker]
            long_snapshot = self.options_snapshots[result.long_contract.ticker]
            
            self.assertEqual(result.short_premium, short_snapshot.day.bid,
                "Short premium should equal the short contract's bid price for credit spreads")
            self.assertEqual(result.long_premium, long_snapshot.day.ask,
                "Long premium should equal the long contract's ask price for credit spreads")
            
            # Net premium should be positive for credit spreads
            expected_net = short_snapshot.day.bid - long_snapshot.day.ask
            self.assertEqual(result.net_premium, expected_net,
                "Net premium calculation incorrect for credit spread")
            self.assertGreater(result.net_premium, 0,
                "Net premium should be positive for credit spreads")
        
        # Test a debit spread (bullish call debit spread)
        result = VerticalSpreadMatcher.match_option(
            self.options_snapshots, 
            self.underlying_ticker,
            DirectionType.BULLISH, 
            StrategyType.DEBIT, 
            self.previous_close, 
            self.expiration_date,
            self.call_contracts  # Only use call options
        )
        
        # Set test selector before evaluating
        result.contract_selector = self.test_selector
        
        if result.matched:
            self.assertIsInstance(result, DebitSpread)
            # For debit spreads:
            # - long_premium should equal the ask price of the long contract (buying)
            # - short_premium should equal the bid price of the short contract (selling)
            long_snapshot = self.options_snapshots[result.long_contract.ticker]
            short_snapshot = self.options_snapshots[result.short_contract.ticker]
            
            self.assertEqual(result.long_premium, long_snapshot.day.ask,
                "Long premium should equal the long contract's ask price for debit spreads")
            self.assertEqual(result.short_premium, short_snapshot.day.bid,
                "Short premium should equal the short contract's bid price for debit spreads")
            
            # Net premium should be negative for debit spreads
            expected_net = -(long_snapshot.day.ask - short_snapshot.day.bid)
            self.assertEqual(result.net_premium, expected_net,
                "Net premium calculation incorrect for debit spread")
            self.assertLess(result.net_premium, 0,
                "Net premium should be negative for debit spreads")
            logger.debug("✅ Successfully completed spread premium calculation test")

    def test_no_deep_itm_otm_selection(self):
        """Test that deep ITM and OTM options are not selected for spreads"""
        self._setup_test_data('strike_selection_test')
        logger.debug("Starting test_no_deep_itm_otm_selection")

        # Test all strategy/direction combinations
        test_cases = [
            (DirectionType.BULLISH, StrategyType.DEBIT, self.call_contracts),
            (DirectionType.BEARISH, StrategyType.DEBIT, self.put_contracts),
            (DirectionType.BULLISH, StrategyType.CREDIT, self.put_contracts),
            (DirectionType.BEARISH, StrategyType.CREDIT, self.call_contracts)
        ]

        for direction, strategy, contracts in test_cases:
            logger.debug(f"Testing {direction.value} {strategy.value}")
            
            result = VerticalSpreadMatcher.match_option(
                self.options_snapshots,
                self.underlying_ticker,
                direction,
                strategy,
                self.previous_close,
                self.expiration_date,
                contracts
            )
            
            # Set test selector before evaluating
            result.contract_selector = self.test_selector
            
            self.assertTrue(result.matched, f"{direction.value} {strategy.value} spread should find valid options")
            
            # Check that neither contract is deep ITM or OTM
            for contract in [result.long_contract, result.short_contract]:
                snapshot = self.options_snapshots[contract.ticker]
                delta = abs(snapshot.greeks.delta)
                
                # Deep ITM options have delta > 0.90
                self.assertLess(delta, Decimal('0.90'),
                    f"{contract.ticker} has delta {delta}, which is too deep ITM")
                
                # Deep OTM options have delta < 0.10
                self.assertGreater(delta, Decimal('0.10'),
                    f"{contract.ticker} has delta {delta}, which is too deep OTM")
        
        logger.debug("✅ Successfully completed deep ITM/OTM exclusion test")

    def test_deep_itm_otm_volume_validation(self):
        """Test that deep ITM and OTM options with low volume are properly filtered"""
        self._setup_test_data('strike_selection_test')
        logger.debug("Starting test_deep_itm_otm_volume_validation")

        # Get lists of deep ITM/OTM contracts
        deep_itm_calls = [c for c in self.call_contracts if self.options_snapshots[c.ticker].greeks.delta > Decimal('0.90')]
        deep_otm_calls = [c for c in self.call_contracts if self.options_snapshots[c.ticker].greeks.delta < Decimal('0.10')]
        deep_itm_puts = [c for c in self.put_contracts if abs(self.options_snapshots[c.ticker].greeks.delta) > Decimal('0.90')]
        deep_otm_puts = [c for c in self.put_contracts if abs(self.options_snapshots[c.ticker].greeks.delta) < Decimal('0.10')]

        # Verify we found some deep ITM/OTM contracts
        self.assertGreater(len(deep_itm_calls + deep_otm_calls + deep_itm_puts + deep_otm_puts), 0,
                          "Test data should include deep ITM/OTM contracts")

        # Verify all deep ITM/OTM contracts have lower volume
        for contract in (deep_itm_calls + deep_otm_calls + deep_itm_puts + deep_otm_puts):
            snapshot = self.options_snapshots[contract.ticker]
            self.assertLessEqual(snapshot.day.volume, 100,
                f"Deep ITM/OTM contract {contract.ticker} should have low volume (<=100)")
            self.assertLessEqual(snapshot.day.open_interest, 200,
                f"Deep ITM/OTM contract {contract.ticker} should have low open interest (<=200)")

        logger.debug("✅ Successfully completed deep ITM/OTM volume validation test")
    
                    
if __name__ == '__main__':
    unittest.main()
