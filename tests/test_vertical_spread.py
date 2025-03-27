import unittest
import json
import os
from datetime import datetime
from decimal import Decimal
from engine.data_model import *
from engine.VerticalSpread import VerticalSpread, CreditSpread, DebitSpread, VerticalSpreadMatcher

class TestVerticalSpreadSelection(unittest.TestCase):
    def setUp(self):
        # Load test data
        data_file = os.path.join(os.path.dirname(__file__), 'data', 'test_spread_data.json')
        with open(data_file, 'r') as f:
            self.test_data = json.load(f)

    def _create_test_contracts(self, leg_data: dict) -> List[Contract]:
        """Create test contracts from JSON data"""
        contracts = []
        for leg in ['first_leg', 'second_leg']:
            data = leg_data[leg]
            contract = Contract(
                ticker=data['ticker'],
                strike_price=Decimal(str(data['strike'])),
                contract_type=ContractType(data['contract_type']),
                expiration_date=datetime.strptime(leg_data['expiration'], "%Y-%m-%d").date()
            )
            contracts.append(contract)
        return contracts

    def _create_snapshot(self, data: dict) -> Snapshot:
        return Snapshot(
            day=DayData(
                bid=Decimal(str(data['bid'])),
                ask=Decimal(str(data['ask'])),
                volume=data['volume'],
                open_interest=data['open_interest']
            ),
            implied_volatility=Decimal(str(data['implied_volatility'])),
            greeks=Greeks(delta=Decimal(str(data['delta'])))
        )

    def test_optimal_width_selection(self):
        """Test spread selection with optimal width"""
        test_data = self.test_data['spread_selection_tests']['optimal_width_test']
        
        # Create contracts and snapshots using data directly from JSON
        contracts = self._create_test_contracts(test_data['expected_spread'])
        snapshots = {
            contracts[0].ticker: self._create_snapshot(test_data['expected_spread']['first_leg']),
            contracts[1].ticker: self._create_snapshot(test_data['expected_spread']['second_leg'])
        }

        # Match spread using actual contract data
        spread = VerticalSpreadMatcher.match_option(
            snapshots,
            test_data['underlying_ticker'],
            DirectionType(test_data['direction']),
            StrategyType(test_data['strategy']),
            Decimal(str(test_data['previous_close'])),
            datetime.strptime(test_data['expiration'], "%Y-%m-%d").date(),
            contracts
        )

        self.assertTrue(spread.matched)
        self.assertEqual(spread.distance_between_strikes, Decimal(str(test_data['ideal_width'])))
        self.assertEqual(spread.contract_type, ContractType(test_data['contract_type']))

    def test_high_volatility_spread(self):
        """Test spread selection in high volatility environment"""
        test_data = self.test_data['spread_selection_tests']['high_volatility_test']
        
        contracts = self._create_test_contracts(test_data['expected_spread'])
        snapshots = {
            contracts[0].ticker: self._create_snapshot(test_data['expected_spread']['first_leg']),
            contracts[1].ticker: self._create_snapshot(test_data['expected_spread']['second_leg'])
        }

        spread = VerticalSpreadMatcher.match_option(
            snapshots,
            test_data['underlying_ticker'],
            DirectionType(test_data['direction']),
            StrategyType(test_data['strategy']),
            Decimal(str(test_data['previous_close'])),
            datetime.strptime(test_data['expiration'], "%Y-%m-%d").date(),
            contracts
        )

        self.assertTrue(spread.matched)
        self.assertTrue(spread.distance_between_strikes > Decimal(str(test_data['ideal_width'])))

    def test_low_liquidity_rejection(self):
        """Test rejection of spreads with insufficient liquidity"""
        test_data = self.test_data['spread_selection_tests']['low_liquidity_test']
        
        contracts = self._create_test_contracts(test_data['expected_spread'])
        snapshots = {
            contracts[0].ticker: self._create_snapshot(test_data['expected_spread']['first_leg']),
            contracts[1].ticker: self._create_snapshot(test_data['expected_spread']['second_leg'])
        }

        spread = VerticalSpreadMatcher.match_option(
            snapshots,
            test_data['underlying_ticker'],
            DirectionType(test_data['direction']),
            StrategyType(test_data['strategy']),
            Decimal(str(test_data['previous_close'])),
            datetime.strptime(test_data['expiration'], "%Y-%m-%d").date(),
            contracts
        )

        self.assertFalse(spread.matched)

    def test_invalid_width_rejection(self):
        """Test rejection of spreads with invalid width"""
        test_data = self.test_data['spread_selection_tests']['invalid_width_test']
        
        contracts = self._create_test_contracts(test_data['expected_spread'])
        snapshots = {
            contracts[0].ticker: self._create_snapshot(test_data['expected_spread']['first_leg']),
            contracts[1].ticker: self._create_snapshot(test_data['expected_spread']['second_leg'])
        }

        spread = VerticalSpreadMatcher.match_option(
            snapshots,
            test_data['underlying_ticker'],
            DirectionType(test_data['direction']),
            StrategyType(test_data['strategy']),
            Decimal(str(test_data['previous_close'])),
            datetime.strptime(test_data['expiration'], "%Y-%m-%d").date(),
            contracts
        )

        self.assertFalse(spread.matched)

    def test_credit_spread_match(self):
        """Test credit spread matching with actual test data"""
        test_data = self.test_data['credit_spread']
        
        # Create contracts from the test data
        short_contract = Contract(
            ticker=test_data['short_contract']['ticker'],
            strike_price=Decimal(str(test_data['short_contract']['strike_price'])),
            contract_type=ContractType(test_data['short_contract']['contract_type']),
            expiration_date=datetime.strptime(test_data['expiration_date'], "%Y-%m-%d").date()
        )
        long_contract = Contract(
            ticker=test_data['long_contract']['ticker'],
            strike_price=Decimal(str(test_data['long_contract']['strike_price'])),
            contract_type=ContractType(test_data['long_contract']['contract_type']),
            expiration_date=datetime.strptime(test_data['expiration_date'], "%Y-%m-%d").date()
        )

        # Create snapshots from entry data
        snapshots = {
            short_contract.ticker: self._create_snapshot(test_data['snapshots']['entry']['short']),
            long_contract.ticker: self._create_snapshot(test_data['snapshots']['entry']['long'])
        }

        spread = VerticalSpreadMatcher.match_option(
            snapshots,
            test_data['underlying_ticker'],
            DirectionType(test_data['direction']),
            StrategyType(test_data['strategy']),
            Decimal(str(test_data['entry_price'])),
            datetime.strptime(test_data['expiration_date'], "%Y-%m-%d").date(),
            [short_contract, long_contract]
        )

        self.assertTrue(spread.matched)
        self.assertEqual(spread.distance_between_strikes, Decimal(str(test_data['distance_between_strikes'])))
        self.assertEqual(spread.contract_type, ContractType(test_data['contract_type']))

    def test_debit_spread_match(self):
        """Test debit spread matching with actual test data"""
        test_data = self.test_data['debit_spread']
        
        # Create contracts from the test data
        long_contract = Contract(
            ticker=test_data['long_contract']['ticker'],
            strike_price=Decimal(str(test_data['long_contract']['strike_price'])),
            contract_type=ContractType(test_data['long_contract']['contract_type']),
            expiration_date=datetime.strptime(test_data['expiration_date'], "%Y-%m-%d").date()
        )
        short_contract = Contract(
            ticker=test_data['short_contract']['ticker'],
            strike_price=Decimal(str(test_data['short_contract']['strike_price'])),
            contract_type=ContractType(test_data['short_contract']['contract_type']),
            expiration_date=datetime.strptime(test_data['expiration_date'], "%Y-%m-%d").date()
        )

        # Create snapshots from entry data
        snapshots = {
            long_contract.ticker: self._create_snapshot(test_data['snapshots']['entry']['long']),
            short_contract.ticker: self._create_snapshot(test_data['snapshots']['entry']['short'])
        }

        spread = VerticalSpreadMatcher.match_option(
            snapshots,
            test_data['underlying_ticker'],
            DirectionType(test_data['direction']),
            StrategyType(test_data['strategy']),
            Decimal(str(test_data['entry_price'])),
            datetime.strptime(test_data['expiration_date'], "%Y-%m-%d").date(),
            [long_contract, short_contract]
        )

        self.assertTrue(spread.matched)
        self.assertEqual(spread.distance_between_strikes, Decimal(str(test_data['distance_between_strikes'])))
        self.assertEqual(spread.contract_type, ContractType(test_data['contract_type']))

if __name__ == '__main__':
    unittest.main()