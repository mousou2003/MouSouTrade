from datetime import datetime, date
import logging
from decimal import Decimal
from typing import List, Dict, Optional, Set
from pydantic import BaseModel

from engine.VerticalSpread import VerticalSpread 
from engine.data_model import DirectionType, StrategyType, TradeState

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
    active_spread_guids: Set[str] = set()  # Track active spreads by GUID
    
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

    def run(self, spreads: List[VerticalSpread]) -> List[VerticalSpread]:
        """
        Process list of spreads and return modified spreads.
        
        Flow:
        1. For each spread:
           - Check current state from our state tracker
           - Process the spread through trade logic
           - If state changed:
             * Update our state tracking
             * Update spread collections (active/completed)
             * Mark for DB update if needed
        
        Returns modified spreads that need persisting.
        """
        modified_spreads = []
        try:
            for spread in spreads:
                logger.debug(f"Processing spread {spread.spread_guid} - Current agent_status: {spread.agent_status}")
                
                # Get current tracked state (or NONE if new)
                current_state = self.spread_states.get(spread.spread_guid, TradeState.NONE)
                # Ensure agent_status is a TradeState
                if isinstance(spread.agent_status, str):
                    spread.agent_status = current_state
                elif spread.agent_status is None:
                    spread.agent_status = TradeState.NONE
                    logger.debug(f"Current tracked state: {current_state}")
                
                # Process completed trades into our stats
                if current_state == TradeState.COMPLETED:
                    if spread.spread_guid not in self.active_spread_guids:
                        self.completed_spreads.append(spread)
                        if spread.trade_outcome == "profit":
                            self.winning_trades += 1
                        self.total_pnl += spread.realized_pnl
                    logger.debug(f"Skipping completed spread {spread.spread_guid}")
                    self.completed_spreads.append(spread)
                    continue

                # Process trade and get new state
                new_state = self._process_trade(spread)
                
                # Handle error cases
                if new_state == TradeState.NONE:
                    logger.error(f"Error processing spread {spread.spread_guid}: Invalid state transition")
                    # Reset spread state to avoid getting stuck
                    if spread.agent_status != TradeState.COMPLETED:
                        spread.agent_status = TradeState.NONE
                    modified_spreads.append(spread)
                    continue

                # Handle state transitions if state changed
                if new_state != current_state:
                    logger.info(f"State change for {spread.spread_guid}: {current_state} -> {new_state}")
                    self.spread_states[spread.spread_guid] = new_state
                    
                    if new_state == TradeState.ACTIVE:
                        # New active trade
                        if spread.spread_guid not in self.active_spread_guids:
                            logger.info(f"Adding new active spread {spread.spread_guid}")
                            self.active_spreads.append(spread)
                            self.active_spread_guids.add(spread.spread_guid)
                            self.total_trades += 1
                            modified_spreads.append(spread)
                            
                    elif new_state == TradeState.COMPLETED:
                        # Trade completed - move to completed list
                        if spread.spread_guid in self.active_spread_guids:
                            logger.info(f"Completing spread {spread.spread_guid}")
                            self.active_spreads = [s for s in self.active_spreads if s.spread_guid != spread.spread_guid]
                            self.active_spread_guids.remove(spread.spread_guid)
                            self.completed_spreads.append(spread)
                            
                            # Update performance metrics
                            if spread.trade_outcome == "profit":
                                self.winning_trades += 1
                            self.total_pnl += spread.realized_pnl
                            
                            modified_spreads.append(spread)
                            
        except Exception as e:
            logger.error(f"Error in trading loop: {e}", exc_info=True)
        
        # Update processed trades at end of run
        self.processed_trades.update(
            spread.spread_guid for spread in spreads 
            if spread.agent_status == TradeState.COMPLETED
        )
        
        logger.info(f"Processed {len(spreads)} spreads, {len(modified_spreads)} modified")
        logger.debug(f"Active: {len(self.active_spreads)}, Completed: {len(self.completed_spreads)}")
        return modified_spreads

    def _process_trade(self, spread: VerticalSpread) -> TradeState:
        """Process trade state transitions and returns new state"""
        try:
            if not spread.stock:
                return TradeState.NONE

            # Check if spread has reached exit date
            if spread.exit_date and spread.exit_date <= date.today():
                logger.info(f"Spread {spread.spread_guid} reached exit date {spread.exit_date}")
                if spread.agent_status == TradeState.ACTIVE:
                    # Force exit at current price
                    spread.agent_status = TradeState.COMPLETED
                    spread.exit_timestamp = datetime.now()
                    spread.actual_exit_price = spread.stock.close
                    spread.realized_pnl = (spread.actual_exit_price - spread.actual_entry_price) * 100
                    if spread.strategy == StrategyType.CREDIT:
                        spread.realized_pnl = -spread.realized_pnl
                    spread.trade_outcome = "profit" if spread.realized_pnl > 0 else "loss"
                    spread.is_processed = True
                    return TradeState.COMPLETED

            prices = [
                (spread.stock.open, 'open'),
                (spread.stock.high, 'high'),
                (spread.stock.low, 'low'),
                (spread.stock.close, 'close')
            ]
            prices = [(Decimal(str(p)), t) for p, t in prices if p is not None]
            
            if not prices:
                return TradeState.NONE

            # Check state transitions
            if spread.agent_status == TradeState.NONE:
                valid_prices = []
                if spread.direction == DirectionType.BULLISH:
                    valid_prices = [p for p, _ in prices if p >= spread.entry_price]
                    if valid_prices:
                        entry_price = min(valid_prices)
                else:
                    valid_prices = [p for p, _ in prices if p <= spread.entry_price]
                    if valid_prices:
                        entry_price = max(valid_prices)

                if valid_prices:
                    spread.agent_status = TradeState.ACTIVE
                    spread.entry_timestamp = datetime.now()
                    spread.actual_entry_price = entry_price
                    logger.debug(f"Spread {spread.spread_guid} entered at {spread.actual_entry_price}")
                    return TradeState.ACTIVE

            elif spread.agent_status == TradeState.ACTIVE:
                # Check exit conditions
                stop_hit = target_hit = False

                # Calculate actual profit/loss percentage relative to max potential
                current_pnl = (spread.stock.close - spread.actual_entry_price) * 100
                if spread.strategy == StrategyType.CREDIT:
                    current_pnl = -current_pnl
                    
                # Default target reward is 80% of max profit if not set
                target_reward = spread.target_reward or Decimal('0.8')
                # Default stop loss is 120% of credit received if not set
                target_stop = spread.target_stop or Decimal('1.2')

                if spread.direction == DirectionType.BULLISH:
                    stop_hit = current_pnl <= -spread.max_risk * target_stop
                    target_hit = current_pnl >= spread.max_reward * target_reward
                else:
                    stop_hit = current_pnl <= -spread.max_risk * target_stop
                    target_hit = current_pnl >= spread.max_reward * target_reward

                if stop_hit or target_hit:
                    is_profit = target_hit
                    spread.agent_status = TradeState.COMPLETED
                    spread.exit_timestamp = datetime.now()
                    spread.actual_exit_price = spread.stock.close
                    spread.realized_pnl = current_pnl
                    spread.trade_outcome = "profit" if is_profit else "loss"
                    spread.is_processed = True
                    return TradeState.COMPLETED

            return self.spread_states.get(spread.spread_guid, TradeState.NONE)
                
        except Exception as e:
            logger.error(f"Error processing trade: {e}")
            return TradeState.NONE

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
