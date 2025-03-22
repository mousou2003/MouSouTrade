import unittest
import json
import os
from datetime import datetime, date
from decimal import Decimal
from engine.data_model import *
from engine.VerticalSpread import VerticalSpread, CreditSpread, DebitSpread
from agents.trading_agent import TradingAgent

class TestTradingAgent(unittest.TestCase):
    """
    Trade Entry/Exit Math:
    ---------------------
    Credit Spread Math:
        Entry:
        - Net credit = short bid - long ask
        - Example: 1.50 - 0.80 = 0.70 credit received
        - Max profit = credit received * 100 = 70.00
        - Max loss = (width - credit) * 100 = (5.00 - 0.70) * 100 = 430.00
        
        Profitable Exit:
        - Exit net debit = short ask - long bid
        - Example: 0.30 - 0.10 = 0.20 debit paid
        - P&L = (entry credit - exit debit) * 100
        - P&L = (0.70 - 0.20) * 100 = 50.00 profit
        
    Debit Spread Math:
        Entry:
        - Net debit = long ask - short bid
        - Example: 5.00 - 2.40 = 2.60 debit paid
        - Max profit = (width - debit) * 100 = (5.00 - 2.60) * 100 = 240.00
        - Max loss = debit paid * 100 = 260.00
        
        Loss Exit:
        - Exit net credit = long bid - short ask
        - Example: 1.90 - 1.00 = 0.90 credit received
        - P&L = (exit credit - entry debit) * 100
        - P&L = (0.90 - 2.60) * 100 = -170.00 loss
    """
    def setUp(self):
        # Load test data
        data_file = os.path.join(os.path.dirname(__file__), 'data', 'test_spread_data.json')
        with open(data_file, 'r') as f:
            self.test_data = json.load(f)
        
        # Initialize agent
        self.agent = TradingAgent()

    def _create_stock(self, data: dict) -> Stock:
        return Stock(**{
            "ticker": "SPY",
            "date": date.today(),
            "open": Decimal(str(data['open'])),
            "high": Decimal(str(data['high'])),
            "low": Decimal(str(data['low'])),
            "close": Decimal(str(data['close'])),
            "volume": None  # Optional field
        })

    def _create_snapshot(self, data: dict) -> Snapshot:
        return Snapshot(
            day=DayData(**{
                "bid": Decimal(str(data['bid'])),
                "ask": Decimal(str(data['ask'])),
                "volume": data['volume'],
                "open_interest": data['open_interest']
            }),
            implied_volatility=Decimal(str(data['implied_volatility']))
        )

    def _create_test_spread(self, spread_type: str, scenario: str) -> VerticalSpread:
        spread_data = self.test_data[spread_type]
        # Determine spread class based on strategy field
        spread_class = CreditSpread if spread_data['strategy'] == "credit" else DebitSpread
        
        # Create spread from data
        spread = spread_class.from_dict(spread_data)
        
        # Map snapshot legs based on spread type
        if spread_data['strategy'] == "credit":
            first_leg, second_leg = 'short', 'long'
        else:  # debit spread
            first_leg, second_leg = 'long', 'short'
            
        # Create snapshots directly from json data
        snapshot_data = spread_data['snapshots'][scenario]
        spread.first_leg_snapshot = Snapshot.from_dict({
            "day": snapshot_data[first_leg],
            "implied_volatility": snapshot_data[first_leg]['implied_volatility']
        })
        spread.second_leg_snapshot = Snapshot.from_dict({
            "day": snapshot_data[second_leg],
            "implied_volatility": snapshot_data[second_leg]['implied_volatility']
        })
        
        return spread

    def test_credit_spread_entry(self):
        """Test credit spread entry execution"""
        spread = self._create_test_spread("credit_spread", "entry")
        spread.stock = self._create_stock(self.test_data['stock_data']['entry'])
        
        # Process spread through agent with current date
        test_date = datetime.strptime(self.test_data["test_dates"]["normal_trading"], "%Y-%m-%d")
        modified_spreads = self.agent.run([spread], current_date=test_date)
        
        # Verify spread was activated
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.ACTIVE)
        self.assertIsNotNone(modified.entry_timestamp)
        self.assertIsNotNone(modified.actual_entry_price)
        
        # Verify contract prices were set
        self.assertEqual(modified.short_contract.actual_entry_price, 
                        spread.first_leg_snapshot.day.bid)
        self.assertEqual(modified.long_contract.actual_entry_price, 
                        spread.second_leg_snapshot.day.ask)
        
        # Verify agent metrics
        self.assertEqual(self.agent.total_trades, 0)  # Entry doesn't count as completed trade
        self.assertEqual(len(self.agent.active_spreads), 1)
        self.assertEqual(len(self.agent.completed_spreads), 0)
        self.assertEqual(self.agent.total_pnl, Decimal('0'))

    def test_expiration_date_exit(self):
        """Test automatic exit on expiration date"""
        spread = self._create_test_spread("credit_spread", "entry")
        spread.stock = self._create_stock(self.test_data['stock_data']['entry'])
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime(2024, 1, 1)
        spread.actual_entry_price = Decimal('430.00')
        
        # Set entry prices
        entry_data = self.test_data["credit_spread"]["snapshots"]["entry"]
        spread.short_contract.actual_entry_price = Decimal(str(entry_data["short"]["bid"]))
        spread.long_contract.actual_entry_price = Decimal(str(entry_data["long"]["ask"]))
        
        # Process spread at expiration
        expiration_date = datetime(2024, 4, 19)  # Match JSON expiration
        modified_spreads = self.agent.run([spread], current_date=expiration_date)
        
        # Verify spread was closed due to expiration
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.COMPLETED)
        self.assertIsNotNone(modified.exit_timestamp)
        self.assertTrue(modified.is_processed)

    def test_credit_spread_profit_exit(self):
        """Test credit spread profit target exit"""
        spread = self._create_test_spread("credit_spread", "exit_profit")
        spread.stock = self._create_stock(self.test_data['stock_data']['profit_target'])
        
        # Set required entry state from test data
        test_scenarios = self.test_data["credit_spread"]["test_scenarios"]["exit_profit"]
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime.strptime(test_scenarios["entry_timestamp"], "%Y-%m-%d")
        spread.actual_entry_price = Decimal(str(test_scenarios["actual_entry_price"]))
        
        # Set entry prices from entry snapshot data
        entry_data = self.test_data["credit_spread"]["snapshots"]["entry"]
        spread.short_contract.actual_entry_price = Decimal(str(entry_data["short"]["bid"]))
        spread.long_contract.actual_entry_price = Decimal(str(entry_data["long"]["ask"]))
        
        # Set current snapshots to exit prices
        exit_data = self.test_data["credit_spread"]["snapshots"]["exit_profit"]
        spread.first_leg_snapshot = Snapshot.from_dict({
            "day": exit_data["short"],
            "implied_volatility": exit_data["short"]["implied_volatility"]
        })
        spread.second_leg_snapshot = Snapshot.from_dict({
            "day": exit_data["long"],
            "implied_volatility": exit_data["long"]["implied_volatility"]
        })
        
        # Get expected P&L from test data
        expected_pnl = Decimal(str(self.test_data["credit_spread"]["test_scenarios"]["exit_profit"]["expected_pnl"]))
        
        # Process spread through agent using test date
        test_date = datetime.strptime(test_scenarios["exit_timestamp"], "%Y-%m-%d")
        modified_spreads = self.agent.run([spread], current_date=test_date)
        
        # Verify spread was completed with profit
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.COMPLETED)
        self.assertEqual(modified.trade_outcome, TradeOutcome.PROFIT)
        self.assertIsNotNone(modified.exit_timestamp)
        self.assertIsNotNone(modified.actual_exit_price)
        self.assertEqual(modified.realized_pnl, expected_pnl)
        
        # Verify agent metrics
        metrics = self.agent.get_daily_performance()
        self.assertEqual(metrics["total_trades"], 1)
        self.assertEqual(metrics["winning_trades"], 1)
        self.assertEqual(metrics["active_trades"], 0)
        self.assertEqual(metrics["completed_trades"], 1)
        self.assertEqual(metrics["total_pnl"], expected_pnl)
        self.assertEqual(metrics["win_rate"], Decimal('1.0'))

    def test_debit_spread_stop_loss(self):
        """
        Test debit spread stop loss exit
        Math:
        - Entry: Long 5.00 ask - Short 2.40 bid = 2.60 net debit
        - Exit: Long 1.90 bid - Short 1.00 ask = 0.90 net credit
        - P&L: (0.90 - 2.60) * 100 = -170.00 loss
        """
        spread = self._create_test_spread("debit_spread", "exit_loss")
        spread.stock = self._create_stock(self.test_data['stock_data']['stop_loss'])
        
        # Set entry state with prices from test data
        test_scenarios = self.test_data["debit_spread"]["test_scenarios"]["exit_loss"]
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime.strptime(test_scenarios["entry_timestamp"], "%Y-%m-%d")
        spread.actual_entry_price = Decimal(str(test_scenarios["actual_entry_price"]))
        
        # Entry prices - Set up for a losing trade
        entry_data = self.test_data["debit_spread"]["snapshots"]["entry"]
        spread.long_contract.actual_entry_price = Decimal(str(entry_data["long"]["ask"]))     # 5.00
        spread.short_contract.actual_entry_price = Decimal(str(entry_data["short"]["bid"]))   # 2.40
        
        # Set current snapshots to loss exit prices
        exit_data = self.test_data["debit_spread"]["snapshots"]["exit_loss"]
        spread.first_leg_snapshot = Snapshot.from_dict({
            "day": exit_data["long"],  # First leg for debit is long
            "implied_volatility": exit_data["long"]["implied_volatility"]
        })
        spread.second_leg_snapshot = Snapshot.from_dict({
            "day": exit_data["short"],  # Second leg for debit is short
            "implied_volatility": exit_data["short"]["implied_volatility"]
        })
        
        # Get expected P&L from test data
        expected_pnl = Decimal(str(self.test_data["debit_spread"]["test_scenarios"]["exit_loss"]["expected_pnl"]))
        
        # Process spread through agent
        test_date = datetime(2024, 1, 1)
        modified_spreads = self.agent.run([spread], current_date=test_date)
        
        # Verify spread was stopped out with expected loss
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.COMPLETED)
        self.assertEqual(modified.trade_outcome, TradeOutcome.LOSS)
        self.assertIsNotNone(modified.exit_timestamp)
        self.assertIsNotNone(modified.actual_exit_price)
        self.assertEqual(modified.realized_pnl, expected_pnl)
        
        # Verify agent metrics
        metrics = self.agent.get_daily_performance()
        self.assertEqual(metrics["total_trades"], 1)
        self.assertEqual(metrics["winning_trades"], 0)
        self.assertEqual(metrics["active_trades"], 0)
        self.assertEqual(metrics["completed_trades"], 1)
        self.assertEqual(metrics["total_pnl"], expected_pnl)
        self.assertEqual(metrics["win_rate"], Decimal('0'))

    def test_credit_spread_large_move(self):
        """
        Test credit spread with large price movement
        - Entry: Short 1.50 bid - Long 0.80 ask = 0.70 net credit
        - Large Move Exit: Short 3.55 ask - Long 2.00 bid = 1.55 net debit
        - P&L: (0.70 - 1.55) * 100 = -85.00 loss
        """
        spread = self._create_test_spread("credit_spread", "exit_loss")
        spread.stock = self._create_stock(self.test_data['stock_data']['large_down_move'])
        
        # Set entry state with prices from test data
        test_scenarios = self.test_data["credit_spread"]["test_scenarios"]["exit_loss"]
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime.strptime(test_scenarios["entry_timestamp"], "%Y-%m-%d")
        spread.actual_entry_price = Decimal(str(test_scenarios["actual_entry_price"]))
        
        # Set entry prices from entry snapshot data
        entry_data = self.test_data["credit_spread"]["snapshots"]["entry"]
        spread.short_contract.actual_entry_price = Decimal(str(entry_data["short"]["bid"]))   # 1.50
        spread.long_contract.actual_entry_price = Decimal(str(entry_data["long"]["ask"]))     # 0.80
        
        # Process spread through agent
        test_date = datetime(2024, 1, 1)
        modified_spreads = self.agent.run([spread], current_date=test_date)
        
        # Verify spread was stopped out due to large move
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.COMPLETED)
        self.assertEqual(modified.trade_outcome, TradeOutcome.LOSS)
        self.assertIsNotNone(modified.exit_timestamp)
        
        # Verify the loss amount
        expected_loss = Decimal(str(self.test_data["credit_spread"]["test_scenarios"]["exit_loss"]["expected_pnl"]))
        self.assertEqual(modified.realized_pnl, expected_loss)

    def test_bearish_credit_spread_profit(self):
        """Test bearish credit spread profit exit"""
        spread = self._create_test_spread("bearish_credit_spread", "exit_profit")
        spread.stock = self._create_stock(self.test_data['stock_data']['bearish_profit'])
        
        # Set entry state with prices from test data
        test_scenarios = self.test_data["bearish_credit_spread"]["test_scenarios"]["exit_profit"]
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime.strptime(test_scenarios["entry_timestamp"], "%Y-%m-%d")
        spread.actual_entry_price = Decimal(str(test_scenarios["actual_entry_price"]))
        
        # Set entry prices
        entry_data = self.test_data["bearish_credit_spread"]["snapshots"]["entry"]
        spread.short_contract.actual_entry_price = Decimal(str(entry_data["short"]["bid"]))
        spread.long_contract.actual_entry_price = Decimal(str(entry_data["long"]["ask"]))
        
        # Set current snapshots to profit exit prices
        exit_data = self.test_data["bearish_credit_spread"]["snapshots"]["exit_profit"]
        spread.first_leg_snapshot = Snapshot.from_dict({
            "day": exit_data["short"],
            "implied_volatility": exit_data["short"]["implied_volatility"]
        })
        spread.second_leg_snapshot = Snapshot.from_dict({
            "day": exit_data["long"],
            "implied_volatility": exit_data["long"]["implied_volatility"]
        })
        
        # Process spread
        test_date = datetime.strptime(test_scenarios["exit_timestamp"], "%Y-%m-%d")
        modified_spreads = self.agent.run([spread], current_date=test_date)
        
        # Verify profitable exit
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.COMPLETED)
        self.assertEqual(modified.trade_outcome, TradeOutcome.PROFIT)
        self.assertEqual(modified.realized_pnl, 
                        Decimal(str(test_scenarios["expected_pnl"])))

    def test_bearish_debit_spread_profit(self):
        """
        Test bearish debit spread profit exit
        Math:
        - Entry: Long 4.00 ask - Short 1.90 bid = 2.10 net debit
        - Exit: Long 7.00 bid - Short 4.00 ask = 3.00 net credit
        - P&L: (3.00 - 2.10) * 100 = 90.00 profit
        """
        spread = self._create_test_spread("bearish_debit_spread", "exit_profit")
        spread.stock = self._create_stock(self.test_data['stock_data']['large_down_move'])
        
        # Set entry state with prices
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime.now()
        spread.actual_entry_price = Decimal('430.00')
        
        # Set entry prices
        entry_data = self.test_data["bearish_debit_spread"]["snapshots"]["entry"]
        spread.long_contract.actual_entry_price = Decimal(str(entry_data["long"]["ask"]))     # 4.00
        spread.short_contract.actual_entry_price = Decimal(str(entry_data["short"]["bid"]))   # 1.90
        
        # Set current snapshots to profit exit prices
        exit_data = self.test_data["bearish_debit_spread"]["snapshots"]["exit_profit"]
        spread.first_leg_snapshot = Snapshot.from_dict({
            "day": exit_data["long"],
            "implied_volatility": exit_data["long"]["implied_volatility"]
        })
        spread.second_leg_snapshot = Snapshot.from_dict({
            "day": exit_data["short"],
            "implied_volatility": exit_data["short"]["implied_volatility"]
        })
        
        # Process spread
        test_date = datetime(2024, 1, 1)
        modified_spreads = self.agent.run([spread], current_date=test_date)
        
        # Verify profitable exit
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.COMPLETED)
        self.assertEqual(modified.trade_outcome, TradeOutcome.PROFIT)
        self.assertEqual(modified.realized_pnl, 
                        Decimal(str(self.test_data["bearish_debit_spread"]["test_scenarios"]["exit_profit"]["expected_pnl"])))

    def test_early_assignment_risk(self):
        """
        Test detection of early assignment risk due to extreme price movement
        - Initial stock price: 430.00
        - Large move up to: 444.00 
        - Credit spread becomes deep ITM, increasing assignment risk
        """
        spread = self._create_test_spread("credit_spread", "entry")
        spread.stock = self._create_stock(self.test_data['stock_data']['large_up_move'])
        
        # Set active state with prices from test data
        test_scenarios = self.test_data["credit_spread"]["test_scenarios"]["entry"]
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime.strptime(test_scenarios["entry_timestamp"], "%Y-%m-%d")
        spread.actual_entry_price = Decimal(str(test_scenarios["actual_entry_price"]))
        
        # Set entry prices from snapshot data
        entry_data = self.test_data["credit_spread"]["snapshots"]["entry"]
        spread.short_contract.actual_entry_price = Decimal(str(entry_data["short"]["bid"]))   # 1.50
        spread.long_contract.actual_entry_price = Decimal(str(entry_data["long"]["ask"]))     # 0.80
        
        # Process spread
        test_date = datetime(2024, 1, 1)
        modified_spreads = self.agent.run([spread], current_date=test_date)
        
        # Verify spread was closed to avoid assignment risk
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.COMPLETED)
        self.assertEqual(modified.trade_outcome, TradeOutcome.LOSS)
        self.assertIsNotNone(modified.exit_timestamp)
        self.assertIsNotNone(modified.actual_exit_price)

if __name__ == '__main__':
    unittest.main()
