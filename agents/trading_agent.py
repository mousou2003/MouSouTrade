from datetime import datetime, date
import logging
from decimal import Decimal
from typing import List, Dict, Optional, Set
from pydantic import BaseModel

from engine.VerticalSpread import VerticalSpread 
from engine.data_model import DirectionType, StrategyType, TradeOutcome, TradeState

logger = logging.getLogger(__name__)

class TradingAgent(BaseModel):
    """Trading agent model for handling spread trades"""
    class Config:
        arbitrary_types_allowed = True

    # Trading state
    active_spreads: List[VerticalSpread] = []
    completed_spreads: List[VerticalSpread] = []
    processed_trades: Set[str] = set()
    spread_states: Dict[str, TradeState] = {}  # Track states by spread GUID
    current_date: datetime = datetime.now()
    
    # Performance tracking
    total_trades: int = 0
    winning_trades: int = 0
    total_pnl: Decimal = Decimal('0')

    def __init__(self, **data):
        super().__init__(**data)

    def get_daily_performance(self) -> Dict:
        """Get daily performance metrics for reporting"""
        return {
            "date": date.today().strftime('%Y-%m-%d'),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "active_trades": len(self.active_spreads),
            "completed_trades": len(self.completed_spreads),
            "total_pnl": self.total_pnl,  # Keep as Decimal
            "win_rate": self.win_rate     # Keep as Decimal
        }

    def run(self, spreads: List[VerticalSpread], current_date: datetime = None) -> List[VerticalSpread]:
        """Process list of spreads and return any spread that had a state change."""
        modified_spreads = []
        if current_date:
            self.current_date = current_date
        
        for spread in spreads:
            try:
                # Skip already completed trades
                if spread.agent_status == TradeState.COMPLETED:
                    continue
                
                # Process trade
                previous_state = spread.agent_status
                self._process_trade(spread)
                
                # Track state changes
                if spread.agent_status != previous_state:
                    modified_spreads.append(spread)
                    self._update_agent_metrics(spread)
                
            except Exception as e:
                raise
        
        return modified_spreads

    def _update_agent_metrics(self, spread: VerticalSpread) -> None:
        """Update agent metrics when spread state changes"""
        if spread.agent_status == TradeState.COMPLETED:
            # Move from active to completed
            self.active_spreads = [s for s in self.active_spreads if s.spread_guid != spread.spread_guid]
            self.completed_spreads.append(spread)
            self.total_trades += 1
            
            # Update P&L and win count
            if spread.realized_pnl:
                self.total_pnl += spread.realized_pnl
            if spread.trade_outcome == TradeOutcome.PROFIT:
                self.winning_trades += 1
                
        elif spread.agent_status == TradeState.ACTIVE:
            self.active_spreads.append(spread)

    def _process_trade(self, spread: VerticalSpread) -> None:
        """Process trade state transitions"""
        try:
            if not spread.stock:
                return

            # Handle active trades
            if spread.agent_status == TradeState.ACTIVE:
                if self._should_exit_trade(spread):
                    self._handle_exit(spread)
                return

            # Handle new trades
            if spread.agent_status == TradeState.NONE:
                valid_prices = self._get_valid_entry_prices(spread, self._get_current_prices(spread))
                if valid_prices:
                    self._handle_entry(spread, valid_prices)
                return

        except Exception as e:
            raise

    def _get_current_prices(self, spread: VerticalSpread) -> List[Decimal]:
        """Get list of current valid prices"""
        return [p for p in [spread.stock.open, spread.stock.high, 
                          spread.stock.low, spread.stock.close] 
                if p is not None]

    def _can_enter_trade(self, spread: VerticalSpread) -> bool:
        """Check if trade can be entered"""
        if not spread.stock or not spread.entry_price:
            return False
            
        prices = [p for p in [spread.stock.open, spread.stock.high, 
                          spread.stock.low, spread.stock.close] if p is not None]
        
        valid_prices = self._get_valid_entry_prices(spread, prices)
        return bool(valid_prices)

    def _should_exit_trade(self, spread: VerticalSpread) -> bool:
        """Determine if a trade should be exited based on time and price conditions."""
        logger.debug(f"Checking exit conditions for {spread.spread_guid}")
        
        # Check exit by date
        date_exit = (self.current_date >= spread.expiration_date if isinstance(self.current_date, datetime) 
                    else self.current_date >= spread.expiration_date)

        # Check profit target and stop loss
        current_profit = VerticalSpread.get_current_profit(spread)
        
        target_exit = current_profit >= spread.target_reward if spread.target_reward else False
        stop_exit = current_profit <= -spread.target_stop if spread.target_stop else False
        
        should_exit = date_exit or target_exit or stop_exit
        
        if should_exit:
            logger.debug(f"Exit conditions met: date_exit={date_exit}, target_exit={target_exit}, stop_exit={stop_exit}")
        
        return should_exit

    def _handle_entry(self, spread: VerticalSpread, valid_prices: List[Decimal]) -> None:
        """Handle trade entry setup"""
        entry_price = min(valid_prices) if spread.direction == DirectionType.BULLISH else max(valid_prices)
        spread.agent_status = TradeState.ACTIVE
        spread.entry_timestamp = datetime.now()
        spread.actual_entry_price = entry_price

        if spread.strategy == StrategyType.CREDIT:
            spread.short_contract.actual_entry_price = spread.first_leg_snapshot.day.bid
            spread.long_contract.actual_entry_price = spread.second_leg_snapshot.day.ask
        else:  # DEBIT
            spread.long_contract.actual_entry_price = spread.first_leg_snapshot.day.ask
            spread.short_contract.actual_entry_price = spread.second_leg_snapshot.day.bid
        
        logger.debug(f"Spread {spread.spread_guid} entered at {spread.actual_entry_price}")

    def _handle_exit(self, spread: VerticalSpread) -> None:
        """Handle trade exit setup"""
        # Set exit state
        spread.agent_status = TradeState.COMPLETED
        spread.exit_timestamp = datetime.now()
        spread.actual_exit_price = spread.stock.close

        # Set contract exit prices based on strategy
        if spread.strategy == StrategyType.CREDIT:
            spread.short_contract.actual_exit_price = spread.first_leg_snapshot.day.ask
            spread.long_contract.actual_exit_price = spread.second_leg_snapshot.day.bid
        else:  # DEBIT
            spread.long_contract.actual_exit_price = spread.first_leg_snapshot.day.bid
            spread.short_contract.actual_exit_price = spread.second_leg_snapshot.day.ask
        
        # Calculate final PnL and set outcome
        spread.realized_pnl = VerticalSpread.get_current_profit(spread)
        spread.trade_outcome = TradeOutcome.PROFIT if spread.realized_pnl > 0 else TradeOutcome.LOSS
        spread.is_processed = True
        
        logger.info(f"Exiting {spread.spread_guid} with {spread.trade_outcome} at {spread.actual_exit_price}")

    def _get_valid_entry_prices(self, spread: VerticalSpread, prices: List[Decimal]) -> List[Decimal]:
        """Get valid prices for entry based on direction"""
        if spread.direction == DirectionType.BULLISH:
            return [p for p in prices if p >= spread.entry_price]
        return [p for p in prices if p <= spread.entry_price]

    def _get_valid_exit_prices(self, spread: VerticalSpread, prices: List[Decimal]) -> List[Decimal]:
        """Get valid prices for exit based on direction"""
        if spread.direction == DirectionType.BULLISH:
            return [p for p in prices if p >= spread.target_price or p <= spread.stop_price]
        return [p for p in prices if p <= spread.target_price or p >= spread.stop_price]

    def _load_portfolio(self) -> List[Dict]:
        """Load current portfolio positions"""
        return list(self.portfolio.values())

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
