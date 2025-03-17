from datetime import datetime, date
import logging
from decimal import Decimal
from typing import List, Dict, Optional, Set
from pydantic import BaseModel

from engine.VerticalSpread import VerticalSpread 
from engine.data_model import DirectionType, StrategyType

logger = logging.getLogger(__name__)

class TradingAgent(BaseModel):
    """Trading agent model for handling spread trades"""
    class Config:
        arbitrary_types_allowed = True

    # Trading state
    active_spreads: List[VerticalSpread] = []
    completed_spreads: List[VerticalSpread] = []
    processed_trades: Set[str] = set()
    
    # Performance tracking
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: Decimal = Decimal('0')

    def run(self, spreads: List[VerticalSpread]) -> None:
        """Process list of spreads for trading decisions"""
        try:
            for spread in spreads:
                if spread.is_processed:
                    continue
                    
                trade_state = self._process_trade(spread)
                if trade_state == "entered":
                    self.active_spreads.append(spread)
                    self.total_trades += 1
                elif trade_state == "exited":
                    self.active_spreads.remove(spread)
                    self.completed_spreads.append(spread)
                    if spread.trade_outcome == "profit":
                        self.winning_trades += 1
                    self.total_pnl += spread.realized_pnl
                    
        except Exception as e:
            logger.error(f"Error in trading loop: {e}")

    def _process_trade(self, spread: VerticalSpread) -> Optional[str]:
        """Process trade state transitions and returns new state if changed"""
        try:
            if not spread.stock:  # Renamed from stock_data
                return None

            prices = [
                (spread.stock.open, 'open'),  # Renamed from stock_data
                (spread.stock.high, 'high'),
                (spread.stock.low, 'low'),
                (spread.stock.close, 'close')
            ]
            prices = [(Decimal(str(p)), t) for p, t in prices if p is not None]
            
            if not prices:
                return None

            # Check state transitions
            if spread.agent_status is None:
                # Try to enter trade
                valid_prices = []
                if spread.direction == DirectionType.BULLISH:
                    valid_prices = [p for p, _ in prices if p >= spread.entry_price]
                    if valid_prices:
                        entry_price = min(valid_prices)  # Use lowest valid price
                else:
                    valid_prices = [p for p, _ in prices if p <= spread.entry_price]
                    if valid_prices:
                        entry_price = max(valid_prices)  # Use highest valid price

                if valid_prices:
                    spread.agent_status = "active"
                    spread.entry_timestamp = datetime.now()
                    spread.actual_entry_price = spread.entry_price
                    return "entered"

            elif spread.agent_status == "active":
                # Check exit conditions
                stop_hit = target_hit = False
                if spread.direction == DirectionType.BULLISH:
                    stop_hit = any(p <= spread.stop_price for p, _ in prices)
                    target_hit = any(p >= spread.target_price for p, _ in prices)
                else:
                    stop_hit = any(p >= spread.stop_price for p, _ in prices)
                    target_hit = any(p <= spread.target_price for p, _ in prices)

                if stop_hit or target_hit:
                    is_profit = target_hit
                    exit_price = spread.target_price if is_profit else spread.stop_price
                    pnl = (exit_price - spread.actual_entry_price) * 100

                    if spread.strategy == StrategyType.CREDIT:
                        pnl = -pnl

                    spread.agent_status = "completed"
                    spread.exit_timestamp = datetime.now()
                    spread.actual_exit_price = exit_price
                    spread.realized_pnl = pnl
                    spread.trade_outcome = "profit" if is_profit else "loss"
                    spread.is_processed = True
                    return "exited"

            return None
                
        except Exception as e:
            logger.error(f"Error processing trade: {e}")
            return None

    def _load_portfolio(self) -> List[Dict]:
        """Load current portfolio positions"""
        return list(self.portfolio.values())

    def _update_performance(self):
        """Calculate and store daily performance metrics"""
        try:
            today = date.today()
            daily_pnl = sum(p["pnl"] for p in self.performance.values() 
                          if p["spread_id"] in self.portfolio)
            
        except Exception as e:
            logger.error(f"Error updating performance: {e}")

    def _calculate_win_rate(self) -> Decimal:
        """Calculate win rate from closed trades"""
        if not self.performance:
            return Decimal('0')
        winners = sum(1 for p in self.performance.values() if p["pnl"] > 0)
        return Decimal(str(winners / len(self.performance)))

    @property
    def win_rate(self) -> Decimal:
        """Calculate current win rate"""
        if self.total_trades == 0:
            return Decimal('0')
        return Decimal(str(self.winning_trades / self.total_trades))

    @property
    def performance_metrics(self) -> Dict:
        """Get current performance metrics"""
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "active_positions": len(self.active_spreads),
            "completed_positions": len(self.completed_spreads)
        }
