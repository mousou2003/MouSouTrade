from pydantic import BaseModel
from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Optional, Dict, Any, List
from datetime import date, datetime

from marketdata_clients.BaseMarketDataClient import IMarketDataClient
from typing import ClassVar

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
    EXCLUDE_FIELDS: ClassVar[List[str]] = ['market_data_client', 'contracts']
    DATE_FORMAT: ClassVar[str] = '%Y-%m-%d'

    def to_json(self, exclude=None):
        return json.dumps(self.to_dict(exclude=exclude))

    def to_dict(self, exclude=None):
        if exclude is None:
            exclude = self.EXCLUDE_FIELDS
        
        # Collect initial attributes
        attributes = {
            key: self._process_value(value)
            for key, value in self.__dict__.items()
            if key not in exclude and value is not None  # Exclude specified attributes
        }

        return attributes

    def _process_value(self, value):
        return value.strftime(self.DATE_FORMAT) if isinstance(value, date) else \
            self._round_decimal(value) if isinstance(value, (Decimal, float)) else \
            self._process_nested_dict(value.__dict__) if isinstance(value, (BaseModel)) else \
            self._process_nested_dict(value) if isinstance(value, (dict)) else \
            value
    
    def _process_nested_dict(self, item):
        return {key: self._process_value(value) for key, value in item.items()}

    def _round_decimal(self, value):
        """Converts to Decimal and rounds it to five decimal places, then converts to string."""
        return str(Decimal(value).quantize(Decimal('0.00000'), rounding=ROUND_HALF_UP))
    
    @classmethod
    def _convert_field_to_model(cls, field: str) -> Any:
        """Convert a single field value to match the model field type."""
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
    cfi: str
    contract_type: str
    exercise_style: str
    expiration_date: date
    primary_exchange: str
    shares_per_contract: int
    strike_price: Decimal
    ticker: str
    underlying_ticker: str

    def __init__(self, data: Dict[str, Any]):
        super().__init__(
            cfi=data['cfi'],
            contract_type=data['contract_type'],
            exercise_style=data['exercise_style'],
            expiration_date=datetime.strptime(data['expiration_date'], self.DATE_FORMAT).date(),
            primary_exchange=data['primary_exchange'],
            shares_per_contract=int(data['shares_per_contract']),
            strike_price=Decimal(data['strike_price']),
            ticker=data['ticker'],
            underlying_ticker=data['underlying_ticker']
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Contract':
        return cls(data)

    def to_dict(self, exclude=None):
        attributes = super().to_dict(exclude)
        return attributes

class SpreadDataModel(DataModelBase):
    datetime: Optional[date] = None
    strategy: Optional[str]
    underlying_ticker: Optional[str]
    previous_close: Optional[Decimal] = None
    contract_type: Optional[str] = None
    direction: Optional[str]
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

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            IMarketDataClient: lambda v: None
        }

    @classmethod
    def from_dynamodb(cls, record: Dict[str, Any]):
        """Convert types of the record to match SpreadDataModel."""
        return cls(
            datetime=datetime.strptime(record.get('datetime'), cls.DATE_FORMAT).date() if record.get('datetime') else None,
            strategy=record.get('strategy', ''),
            underlying_ticker=record.get('underlying_ticker', ''),
            previous_close=Decimal(record.get('previous_close', '0')),
            contract_type=record.get('contract_type', ''),
            direction=record.get('direction', ''),
            distance_between_strikes=Decimal(record.get('distance_between_strikes', '0')),
            short_contract=Contract.from_dict(record.get('short_contract', {})) if record.get('short_contract') else None,
            long_contract=Contract.from_dict(record.get('long_contract', {})) if record.get('long_contract') else None,
            contracts=record.get('contracts', []),
            daily_bars=record.get('daily_bars', []),
            client=record.get('client', ''),
            long_premium=Decimal(record.get('long_premium', '0')),
            short_premium=Decimal(record.get('short_premium', '0')),
            max_risk=Decimal(record.get('max_risk', '0')),
            max_reward=Decimal(record.get('max_reward', '0')),
            breakeven=Decimal(record.get('breakeven', '0')),
            entry_price=Decimal(record.get('entry_price', '0')),
            target_price=Decimal(record.get('target_price', '0')),
            stop_price=Decimal(record.get('stop_price', '0')),
            expiration_date=datetime.strptime(record.get('expiration_date'), cls.DATE_FORMAT).date() if record.get('expiration_date') else None,
            second_leg_depth=int(record.get('second_leg_depth', 0)),
            exit_date=datetime.strptime(record.get('exit_date'), cls.DATE_FORMAT).date() if record.get('exit_date') else None,
            description=record.get('description', ''),
            probability_of_profit=Decimal(record.get('probability_of_profit', '0')),
            first_leg_snapshot=record.get('first_leg_snapshot', {}),
            second_leg_snapshot=record.get('second_leg_snapshot', {}),
            update_date=datetime.strptime(record.get('update_date'), cls.DATE_FORMAT).date() if record.get('update_date') else None
        )

    def to_dict(self, exclude=None):
        return super().to_dict(exclude)
