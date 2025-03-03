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

SPREAD_TYPE = {
    StrategyType.CREDIT: {DirectionType.BULLISH: 'put', DirectionType.BEARISH: 'call'},
    StrategyType.DEBIT: {DirectionType.BULLISH: 'call', DirectionType.BEARISH: 'put'}
}

class ContractType(Enum):
    CALL = 'call'
    PUT = 'put'

class StrikePriceType(Enum):
    ITM = 'ITM'
    ATM = 'ATM'
    OTM = 'OTM'

class DataModelBase(BaseModel):
    EXCLUDE_FIELDS: ClassVar[List[str]] = ['market_data_client']
    DATE_FORMAT: ClassVar[str] = '%Y-%m-%d'

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
        if isinstance(value, date):
            return value.strftime(cls.DATE_FORMAT)
        elif isinstance(value, (Decimal, float)):
            return cls._format_decimal(value)
        elif isinstance(value, BaseModel):
            return cls._process_nested_dict(value.__dict__)
        elif isinstance(value, dict):
            return cls._process_nested_dict(value)
        elif isinstance(value, list):
            return [cls._process_value(item) for item in value]
        elif isinstance(value, (ContractType, DirectionType, StrategyType)):
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
            return lambda value: datetime.strptime(value, cls.DATE_FORMAT).date() if value else None
        elif field_type == Optional[datetime]:
            return lambda value: datetime.strptime(value) if value else None
        elif field_type == Optional[Decimal]:
            return lambda value: Decimal(value) if value else None
        elif field_type == Optional[int]:
            return lambda value: int(value) if value else 0
        elif field_type == Optional[str]:
            return lambda value: value if value else ''
        elif field_type == Optional[List[Dict[str, Any]]]:
            return lambda value: value if value else []
        elif field_type == Optional[Contract]:
            return lambda value: Contract.from_dict(value) if value else None
        else:
            return lambda value: value

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
    """
    Represents daily market data with various attributes such as
    timestamp, open price, high price, low price, close price, and volume.

    Attributes:
        timestamp (datetime): The timestamp of the data.
        open (Decimal): The opening price at the timestamp.
        high (Decimal): The highest price at the timestamp.
        low (Decimal): The lowest price at the timestamp.
        close (Decimal): The closing price at the timestamp.
        volume (int): The trading volume at the timestamp.
    """
    timestamp: Optional[datetime] = None
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    close: Optional[Decimal] = None
    volume: Optional[int] = 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DayData':
        return cls(**data)

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

    breakeven: Optional[Decimal] = None
    client: Optional[str] = None
    contract_type: Optional[ContractType] = None
    daily_bars: Optional[List[DayData]] = None
    datetime: Optional[date] = None
    description: Optional[str] = None
    direction: Optional[DirectionType] = None
    distance_between_strikes: Optional[Decimal] = None
    entry_price: Optional[Decimal] = None
    exit_date: Optional[date] = None
    expiration_date: Optional[date] = None
    first_leg_contract: Optional[Contract] = None
    first_leg_contract_position: Optional[int] = None
    first_leg_snapshot: Optional[Snapshot] = None
    long_contract: Optional[Contract] = None
    long_premium: Optional[Decimal] = None
    max_reward: Optional[Decimal] = None
    max_risk: Optional[Decimal] = None
    net_premium: Optional[Decimal] = None
    previous_close: Optional[Decimal] = None
    probability_of_profit: Optional[Decimal] = None
    second_leg_contract: Optional[Contract] = None
    second_leg_contract_position: Optional[int] = None
    second_leg_depth: Optional[int] = None
    second_leg_snapshot: Optional[Snapshot] = None
    short_contract: Optional[Contract] = None
    short_premium: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    strategy: Optional[StrategyType] = None
    target_price: Optional[Decimal] = None
    underlying_ticker: Optional[str] = None
    update_date: Optional[date] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpreadDataModel':
        return cls(**data)
