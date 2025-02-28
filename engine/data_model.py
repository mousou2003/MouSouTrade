from pydantic import BaseModel
from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Optional, Dict, Any, List, Union, ClassVar
from datetime import date, datetime

from marketdata_clients.BaseMarketDataClient import IMarketDataClient

ASC = 'asc'
BEARISH = 'bearish'
BULLISH = 'bullish'
CREDIT = 'credit'
DEBIT = 'debit'
DESC = 'desc'
SPREAD_TYPE = {
    CREDIT: {BULLISH: 'put', BEARISH: 'call'},
    DEBIT: {BULLISH: 'call', BEARISH: 'put'}
}

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
        
        attributes = {
            key: self._process_value(value)
            for key, value in self.__dict__.items()
            if key not in exclude and value is not None
        }
        return attributes

    def _process_value(self, value: Any) -> Any:
        if isinstance(value, date):
            return value.strftime(self.DATE_FORMAT)
        elif isinstance(value, (Decimal, float)):
            return self._format_decimal(value)
        elif isinstance(value, BaseModel):
            return self._process_nested_dict(value.__dict__)
        elif isinstance(value, dict):
            return self._process_nested_dict(value)
        elif isinstance(value, list):
            return [self._process_value(item) for item in value]
        return value
    
    def _process_nested_dict(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {key: self._process_value(value) for key, value in item.items()}

    def _format_decimal(self, value: Union[Decimal, float]) -> str:
        return str(Decimal(value).quantize(Decimal('0.00000'), rounding=ROUND_HALF_UP))
    
    @classmethod
    def _convert_field_to_model(cls, field: str) -> Any:
        field_type = cls.__annotations__.get(field)
        if field_type == Optional[date]:
            return lambda value: datetime.strptime(value, cls.DATE_FORMAT).date() if value else None
        elif field_type == Optional[Decimal]:
            return lambda value: Decimal(value) if value else Decimal('0')
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
        contract_type (str): The type of the contract.
        exercise_style (str): The exercise style of the contract.
        expiration_date (date): The expiration date of the contract.
        primary_exchange (str): The primary exchange where the contract is traded.
        shares_per_contract (int): The number of shares per contract.
        strike_price (Decimal): The strike price of the contract.
        ticker (str): The ticker symbol of the contract.
        underlying_ticker (str): The ticker symbol of the underlying asset.
    """
    cfi: str
    contract_type: str
    exercise_style: str
    expiration_date: date
    primary_exchange: str
    shares_per_contract: int
    strike_price: Decimal
    ticker: str
    underlying_ticker: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Contract':
        return cls(**data)

class SpreadDataModel(DataModelBase):
    class Config:
        arbitrary_types_allowed = True
    datetime: Optional[date] = None
    strategy: Optional[str] = None
    underlying_ticker: Optional[str] =None
    previous_close: Optional[Decimal] = None
    contract_type: Optional[str] = None
    direction: Optional[str] = None
    distance_between_strikes: Optional[Decimal] = None
    short_contract: Optional[Contract] = None
    long_contract: Optional[Contract] = None
    contracts: Optional[List[Dict[str, Any]]] = None
    daily_bars: Optional[List[Dict[str, Any]]] = None
    client: Optional[str] = None
    long_premium: Optional[Decimal] = None
    short_premium: Optional[Decimal] = None
    max_risk: Optional[Decimal] = None
    max_reward: Optional[Decimal] = None
    breakeven: Optional[Decimal] = None
    entry_price: Optional[Decimal] = None
    target_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    expiration_date: Optional[date] = None
    second_leg_depth: Optional[int] = None
    exit_date: Optional[date] = None
    description: Optional[str] = None
    net_premium: Optional[Decimal] = None
    probability_of_profit: Optional[Decimal] = None
    first_leg_snapshot: Optional[Dict[str, Any]] = None
    second_leg_snapshot: Optional[Dict[str, Any]] = None
    update_date: Optional[date] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpreadDataModel':
        return SpreadDataModel(**data)
