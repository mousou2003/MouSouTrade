"""
Data Models for Options Trading
==============================
This module defines the core data models used throughout the options trading system.
It provides structured representations of:

1. Core trading concepts:
   - Direction types (bullish/bearish)
   - Strategy types (credit/debit)
   - Contract types (call/put)
   - Strike price types (ITM/ATM/OTM)

2. Data structures for options contracts and market data:
   - Contract: Represents an options contract with strike, expiration, etc.
   - Greeks: Delta, gamma, theta, vega and rho for options pricing
   - DayData: Daily market data including OHLC, volume, etc.
   - Snapshot: Complete market snapshot including contract details and Greeks

3. Spread model for vertical options spreads:
   - SpreadDataModel: Comprehensive model of an options spread
   - Contract relationships (long/short positions)
   - Price targets and risk parameters

The module uses Pydantic for data validation and provides serialization/deserialization
capabilities to support data persistence and API communications.
"""

import logging
from pydantic import BaseModel
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional, Dict, Any, List, Union, ClassVar, Literal
from datetime import date, datetime
logger = logging.getLogger(__name__)

OrderType = Literal['asc', 'desc']
ASC: OrderType = 'asc'
DESC: OrderType = 'desc'

class DirectionType(Enum):
    BEARISH = 'bearish'
    BULLISH = 'bullish'

class StrategyType(Enum):
    CREDIT = 'credit'
    DEBIT = 'debit'
class ContractType(Enum):
    CALL = 'call'
    PUT = 'put'

SPREAD_TYPE = {
    StrategyType.CREDIT: {DirectionType.BULLISH: ContractType.PUT, DirectionType.BEARISH: ContractType.CALL},
    StrategyType.DEBIT: {DirectionType.BULLISH: ContractType.CALL, DirectionType.BEARISH: ContractType.PUT}
}

class StrikePriceType(Enum):
    ITM = 'ITM'
    ATM = 'ATM'
    OTM = 'OTM'
    EXCLUDED = 'EXCLUDED'  # Added for strikes too far from current price

class DataModelBase(BaseModel):
    EXCLUDE_FIELDS: ClassVar[List[str]] = ['market_data_client','contract_selector']
    DATE_FORMAT: ClassVar[str] = '%Y-%m-%d'
    
    confidence_level: Optional[Decimal] = Decimal(1.0)
    matched: Optional[bool] = False

    def __init__(self, **data: Any):
        converted_data = {
            key: self._convert_field_to_model(key)(value)
            for key, value in data.items()
        }
        super().__init__(**converted_data)
    
    def to_dict(self, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
        if exclude is None:
            exclude = self.EXCLUDE_FIELDS    
        attributes = {}
        for key, value in self.__dict__.items():
            if key not in exclude:
                if value is None:
                    logger.debug(f"The value for '{key}' is None")
                attributes[key] = self._process_value(value)
        return attributes

    @classmethod
    def _process_value(cls, value: Any) -> Any:
        if isinstance(value, (date,datetime)):
            return value.strftime(cls.DATE_FORMAT)
        elif isinstance(value, (Decimal, float)):
            return cls._format_decimal(value)
        elif isinstance(value, BaseModel):
            return cls._process_nested_dict(value.__dict__)
        elif isinstance(value, dict):
            return cls._process_nested_dict(value)
        elif isinstance(value, list):
            return [cls._process_value(item) for item in value]
        elif isinstance(value, (ContractType, DirectionType, StrategyType, StrikePriceType)):
            return value.value
        return value
    
    @classmethod
    def _process_nested_dict(cls, item: Dict[str, Any]) -> Dict[str, Any]:
        return {key: cls._process_value(value) for key, value in item.items()}

    @classmethod
    def _format_decimal(cls, value: Union[Decimal, float]) -> str:
        return str(Decimal(value).quantize(Decimal('0.00000'), rounding=ROUND_HALF_UP))
    
    @classmethod
    def _convert_field_to_model(cls, field: str) -> Any:
        field_type = cls.__annotations__.get(field)
        if field_type == Optional[date]:
            return lambda value: value if isinstance(value, date) else (
                datetime.strptime(value, cls.DATE_FORMAT).date() if value else None
            )
        elif field_type == Optional[datetime]:
            return lambda value: value if isinstance(value, datetime) else (
                datetime.strptime(value, cls.DATE_FORMAT) if value else None
            )
        elif field_type == Optional[Decimal]:
            return lambda value: Decimal(value) if value else None
        elif field_type == Optional[int]:
            return lambda value: int(value) if value not in (None, '') else 0
        elif field_type == Optional[str]:
            return lambda value: value if value else ''
        elif field_type == Optional[List[Dict[str, Any]]]:
            return lambda value: value if value else []
        elif field_type == Optional[Contract]:
            return lambda value: Contract.from_dict(value) if value else None
        else:
            return lambda value: value

    @staticmethod
    def to_decimal(value: Union[int, float, str]) -> Decimal:
        """Convert any numeric type to Decimal safely.
        
        Args:
            value: A numeric value as int, float, or string.
            
        Returns:
            Decimal: The converted decimal value.
            
        Raises:
            ValueError: If value is None or cannot be converted to Decimal.
        """
        if value is None:
            raise ValueError("Cannot convert None to Decimal")
        return Decimal(str(value))

class Contract(DataModelBase):
    """
    Represents a financial contract with various attributes such as
    contract type, exercise style, expiration date, and more.

    Attributes:
        cfi (str): The CFI code of the contract.
        contract_type (ContractType): The type of the contract.
        exercise_style (str): The exercise style of the contract.
        expiration_date (date): The expiration date of the contract.
        primary_exchange (str): The primary exchange where the contract is traded.
        shares_per_contract (int): The number of shares per contract.
        strike_price (Decimal): The strike price of the contract.
        ticker (str): The ticker symbol of the contract.
        underlying_ticker (str): The ticker symbol of the underlying asset.
        strike_price_type (StrikePriceType): The strike price type of the contract.
    """
    cfi: Optional[str] = ''
    contract_type: Optional[ContractType] = None
    exercise_style: Optional[str] = ''
    expiration_date: Optional[date] = None
    primary_exchange: Optional[str] = ''
    shares_per_contract: Optional[int] = 0
    strike_price: Optional[Decimal] = None
    ticker: Optional[str] = ''
    underlying_ticker: Optional[str] = ''
    strike_price_type: Optional[StrikePriceType] = None  # Added field

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Contract':
        return cls(**data)

class Greeks(BaseModel):
    delta: Optional[Decimal] = None
    gamma: Optional[Decimal] = None
    theta: Optional[Decimal] = None
    vega: Optional[Decimal] = None
    rho: Optional[Decimal] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Greeks':
        return cls(**data)

class DayData(BaseModel):
    """Represents daily market data"""
    timestamp: Optional[datetime] = None
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Optional[Decimal] = None
    volume: Optional[int] = 0
    adjusted_flag: Optional[bool] = None
    ask: Optional[Decimal] = None
    ask_size: Optional[int] = None
    ask_time: Optional[datetime] = None
    bid: Optional[Decimal] = None
    bid_exchange: Optional[str] = None
    bid_size: Optional[int] = None
    bid_time: Optional[datetime] = None
    change_close: Optional[Decimal] = None
    change_close_percentage: Optional[Decimal] = None
    company_name: Optional[str] = None
    days_to_expiration: Optional[int] = None
    dir_last: Optional[str] = None
    dividend: Optional[Decimal] = None
    eps: Optional[Decimal] = None
    est_earnings: Optional[Decimal] = None
    ex_dividend_date: Optional[int] = None
    high52: Optional[Decimal] = None
    last_trade: Optional[Decimal] = None
    low52: Optional[Decimal] = None
    open_interest: Optional[int] = None
    option_style: Optional[str] = None
    option_underlier: Optional[str] = None
    option_underlier_exchange: Optional[str] = None
    previous_close: Optional[Decimal] = None
    previous_day_volume: Optional[int] = None
    primary_exchange: Optional[str] = None
    symbol_description: Optional[str] = None
    total_volume: Optional[int] = None
    upc: Optional[int] = None
    cash_deliverable: Optional[Decimal] = None
    market_cap: Optional[Decimal] = None
    shares_outstanding: Optional[int] = None
    next_earning_date: Optional[str] = None
    beta: Optional[Decimal] = None
    yield_: Optional[Decimal] = None
    declared_dividend: Optional[Decimal] = None
    dividend_payable_date: Optional[int] = None
    pe: Optional[Decimal] = None
    week52_low_date: Optional[int] = None
    week52_hi_date: Optional[int] = None
    intrinsic_value: Optional[Decimal] = None
    time_premium: Optional[Decimal] = None
    option_multiplier: Optional[Decimal] = None
    contract_size: Optional[Decimal] = None
    expiration_date: Optional[int] = None
    option_previous_bid_price: Optional[Decimal] = None
    option_previous_ask_price: Optional[Decimal] = None
    osi_key: Optional[str] = None
    time_of_last_trade: Optional[int] = None
    average_volume: Optional[int] = None

    class Config:
        populate_by_name = True  # Updated from allow_population_by_field_name

class Snapshot(DataModelBase):
    """
    Represents a snapshot of market data with various attributes such as
    day data, contract details, greeks, implied volatility, and open interest.

    Attributes:
        day (DayData): The daily market data.
        details (Contract): The contract details.
        greeks (Greeks): The greeks data.
        implied_volatility (Decimal): The implied volatility.
        open_interest (int): The open interest.
    """
    day: Optional[DayData] = None
    details: Optional[Contract] = None
    greeks: Optional[Greeks] = None
    implied_volatility: Optional[Decimal] = None
    open_interest: Optional[int] = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Snapshot':
        return cls(**data)

class SpreadDataModel(DataModelBase):
    class Config:
        arbitrary_types_allowed = True

    # Basic spread information
    spread_guid: Optional[str] = None
    underlying_ticker: Optional[str] = None
    direction: Optional[DirectionType] = None
    strategy: Optional[StrategyType] = None
    contract_type: Optional[ContractType] = None
    description: Optional[str] = None

    # Contract details
    first_leg_contract: Optional[Contract] = None
    first_leg_contract_position: Optional[int] = None
    first_leg_snapshot: Optional[Snapshot] = None
    second_leg_contract: Optional[Contract] = None
    second_leg_contract_position: Optional[int] = None
    second_leg_snapshot: Optional[Snapshot] = None
    long_contract: Optional[Contract] = None
    short_contract: Optional[Contract] = None

    # Premium and price information
    long_premium: Optional[Decimal] = None
    short_premium: Optional[Decimal] = None
    net_premium: Optional[Decimal] = None
    previous_close: Optional[Decimal] = None
    entry_price: Optional[Decimal] = None
    target_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    breakeven: Optional[Decimal] = None
    distance_between_strikes: Optional[Decimal] = None
    optimal_spread_width: Optional[Decimal] = None

    # Risk metrics
    max_reward: Optional[Decimal] = None
    max_risk: Optional[Decimal] = None
    optimal_profit: Optional[Decimal] = None
    optimal_loss: Optional[Decimal] = None
    profit_factor: Optional[Decimal] = None
    probability_of_profit: Optional[Decimal] = None
    reward_risk_ratio: Optional[Decimal] = None

    # Dates
    update_date: Optional[date] = None
    expiration_date: Optional[date] = None
    exit_date: Optional[date] = None

    # Market data
    daily_bars: Optional[List[DayData]] = None

    # Scoring components
    adjusted_score: Optional[Decimal] = None
    score_pop: Optional[Decimal] = None
    score_width: Optional[Decimal] = None
    score_reward_risk: Optional[Decimal] = None
    score_risk: Optional[Decimal] = None
    score_liquidity: Optional[Decimal] = None

    # Raw metrics
    score_pop_raw: Optional[Decimal] = None
    score_width_raw: Optional[Decimal] = None
    score_reward_risk_raw: Optional[Decimal] = None
    score_risk_raw: Optional[Decimal] = None
    score_liquidity_volume: Optional[Decimal] = None
    score_liquidity_oi: Optional[Decimal] = None

    # Agent trading data
    agent_status: Optional[str] = None  # 'pending', 'active', 'completed'
    entry_timestamp: Optional[datetime] = None
    exit_timestamp: Optional[datetime] = None
    trade_outcome: Optional[str] = None  # 'profit', 'loss'
    actual_entry_price: Optional[Decimal] = None
    actual_exit_price: Optional[Decimal] = None
    realized_pnl: Optional[Decimal] = None
    is_processed: Optional[bool] = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpreadDataModel':
        return cls(**data)
