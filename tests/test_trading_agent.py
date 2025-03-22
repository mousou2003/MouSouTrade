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
        spread_class = CreditSpread if spread_type == "credit_spread" else DebitSpread
        
        # Create spread from data
        spread = spread_class.from_dict(spread_data)
        
        # Map snapshot legs based on spread type
        if spread_type == "credit_spread":
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
        
        # Process spread through agent
        modified_spreads = self.agent.run([spread])
        
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

    def test_credit_spread_profit_exit(self):
        """
        Test credit spread profit target exit
        Math:
        - Entry: Short 1.50 bid - Long 0.80 ask = 0.70 net credit
        - Exit: Short 0.30 ask - Long 0.10 bid = 0.20 net debit
        - P&L: (0.70 - 0.20) * 100 = 50.00 profit
        """
        spread = self._create_test_spread("credit_spread", "exit_profit")
        spread.stock = self._create_stock(self.test_data['stock_data']['profit_target'])
        
        # Set required entry state
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime.now()
        spread.actual_entry_price = Decimal('430.00')
        
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
        
        # Process spread through agent
        modified_spreads = self.agent.run([spread])
        
        # Verify spread was completed with profit
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.COMPLETED)
        self.assertEqual(modified.trade_outcome, "profit")
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
        
        # Set entry state with prices
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime.now()
        spread.actual_entry_price = Decimal('430.00')
        
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
        modified_spreads = self.agent.run([spread])
        
        # Verify spread was stopped out with expected loss
        self.assertEqual(len(modified_spreads), 1)
        modified = modified_spreads[0]
        self.assertEqual(modified.agent_status, TradeState.COMPLETED)
        self.assertEqual(modified.trade_outcome, "loss")
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

if __name__ == '__main__':
    unittest.main()
