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
        """Process list of spreads and return modified spreads."""
        modified_spreads = []
        try:
            for spread in spreads:
                logger.debug(f"Processing spread {spread.spread_guid} - Current agent_status: {spread.agent_status}")
                
                # Ensure agent_status is a TradeState
                if spread.agent_status is None:
                    spread.agent_status = TradeState.NONE
                    logger.warning(f"State not defined for: {spread.spread_guid}")
                
                # Get current tracked state
                if spread.spread_guid not in self.spread_states:
                    self.spread_states[spread.spread_guid] = spread.agent_status
                current_state = self.spread_states.get(spread.spread_guid)

                
                # Process completed trades into our stats
                if current_state == TradeState.COMPLETED:
                    if not any(s.spread_guid == spread.spread_guid for s in self.completed_spreads):
                        self.completed_spreads.append(spread)
                        self.total_trades += 1
                        if spread.trade_outcome == "profit":
                            self.winning_trades += 1
                        # Update total_pnl for both profits and losses
                        if spread.realized_pnl:  # Only add if there's a value
                            self.total_pnl = self.total_pnl + spread.realized_pnl
                    logger.debug(f"Skipping completed spread {spread.spread_guid}")
                    continue

                # Process trade and get new state
                new_state = self._process_trade(spread)
                
                # Handle error cases
                if new_state == TradeState.NONE:
                    # Reset spread state to avoid getting stuck
                    if spread.is_processed:
                        spread.agent_status = TradeState.COMPLETED
                    elif spread.entry_price is not None:
                        spread.agent_status = TradeState.ACTIVE
                    else:
                        logger.warning(f"Error processing spread {spread.spread_guid}: Invalid state transition")
                    modified_spreads.append(spread)
                    continue

                # Handle state transitions if state changed
                if new_state != current_state:
                    logger.info(f"State change for {spread.spread_guid}: {current_state} -> {new_state}")
                    self.spread_states[spread.spread_guid] = new_state
                    modified_spreads.append(spread)
                    
                    if new_state == TradeState.ACTIVE:
                        logger.info(f"Adding new active spread {spread.spread_guid}")
                        self.active_spreads.append(spread)
                    elif new_state == TradeState.COMPLETED:
                        logger.info(f"Completing spread {spread.spread_guid}")
                        self.active_spreads = [s for s in self.active_spreads if s.spread_guid != spread.spread_guid]
                        self.completed_spreads.append(spread)
                        self.total_trades += 1
                        if spread.trade_outcome == "profit":
                            self.winning_trades += 1
                        # Update total_pnl for both profits and losses
                        if spread.realized_pnl:  # Only add if there's a value
                            self.total_pnl = self.total_pnl + spread.realized_pnl
                    else:
                        logger.error(f"Error processing spread {spread.spread_guid}: Invalid state transition")

        except Exception as e:
            logger.error(f"Error in trading loop: {e}", exc_info=True)
            raise
        
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
                raise ValueError("Stock data not available for spread")
            if spread.agent_status == TradeState.COMPLETED:
                raise ValueError("Spread already completed")
            # Simplified price handling
            prices = [
                price for price in [
                    spread.stock.open,
                    spread.stock.high, 
                    spread.stock.low,
                    spread.stock.close
                ] if price is not None
            ]
            if not prices:
                raise ValueError("No valid prices available for spread")

            # Check if spread has reached exit date
            if spread.exit_date and spread.exit_date <= date.today() and spread.agent_status == TradeState.ACTIVE:
                    # Force exit at current price
                    spread.agent_status = TradeState.COMPLETED
                    spread.exit_timestamp = datetime.now()
                    spread.actual_exit_price = spread.stock.close
                    spread.is_processed = True
            elif spread.agent_status == TradeState.NONE:
                valid_prices = []
                entry_price = spread.entry_price
                if spread.direction == DirectionType.BULLISH:
                    valid_prices = [p for p in prices if p >= spread.entry_price]
                    if valid_prices:
                        entry_price = min(valid_prices)
                else:
                    valid_prices = [p for p in prices if p <= spread.entry_price]
                    if valid_prices:
                        entry_price = max(valid_prices)

                if valid_prices:
                    # Set spread and contract entry prices
                    spread.agent_status = TradeState.ACTIVE
                    spread.entry_timestamp = datetime.now()
                    spread.actual_entry_price = entry_price
                    
                    # Set contract entry prices based on entry snapshots
                    if spread.strategy == StrategyType.CREDIT:
                        spread.short_contract.actual_entry_price = spread.first_leg_snapshot.day.bid
                        spread.long_contract.actual_entry_price = spread.second_leg_snapshot.day.ask
                    else:  # DEBIT
                        spread.long_contract.actual_entry_price = spread.first_leg_snapshot.day.ask
                        spread.short_contract.actual_entry_price = spread.second_leg_snapshot.day.bid
                    
                    logger.debug(f"Spread {spread.spread_guid} entered at {spread.actual_entry_price}")

            elif spread.agent_status == TradeState.ACTIVE:   
                valid_prices = []
                exit_price = spread.stop_price
                if spread.direction == DirectionType.BULLISH:
                    valid_prices = [p for p in prices if p >= spread.target_price or p <= spread.stop_price]
                    if valid_prices:
                        exit_price = max(valid_prices)
                else:
                    valid_prices = [p for p in prices if p <= spread.target_price or p >= spread.stop_price]
                    if valid_prices:
                        exit_price = min(valid_prices)        

                # Calculate realized PnL before checking exit conditions
                spread.realized_pnl = VerticalSpread.get_current_profit(spread)

                if spread.realized_pnl >= spread.target_reward or spread.realized_pnl <= -spread.target_stop:
                    spread.agent_status = TradeState.COMPLETED
                    spread.exit_timestamp = datetime.now()
                    spread.actual_exit_price = exit_price
                    
                    # Set contract exit prices based on current snapshots
                    if spread.strategy == StrategyType.CREDIT:
                        spread.short_contract.actual_exit_price = spread.first_leg_snapshot.day.ask
                        spread.long_contract.actual_exit_price = spread.second_leg_snapshot.day.bid
                    else:  # DEBIT
                        spread.long_contract.actual_exit_price = spread.first_leg_snapshot.day.bid
                        spread.short_contract.actual_exit_price = spread.second_leg_snapshot.day.ask
                    
                    spread.is_processed = True
            
            spread.realized_pnl = VerticalSpread.get_current_profit(spread)            
            spread.trade_outcome = "profit" if spread.realized_pnl > 0 else "loss"
            return spread.agent_status
                
        except Exception as e:
            logger.error(f"Error processing trade: {e}")
            raise

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
