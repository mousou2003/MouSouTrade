from pydantic import BaseModel, Field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List
import datetime
from datetime import date

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

class SpreadDataModel(BaseModel):
    datetime: Optional[date] = None
    strategy: Optional[str]
    underlying_ticker: Optional[str]
    previous_close: Optional[Decimal] = None
    contract_type: Optional[str] = None
    direction: Optional[str]
    distance_between_strikes: Optional[Decimal] = None
    short_contract: Optional[Dict[str, Any]] = None
    long_contract: Optional[Dict[str, Any]] = None
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

    @classmethod
    def from_dynamodb(cls, record: Dict[str, Any]):
        """Convert types of the record to match SpreadDataModel."""
        return cls(
            datetime=record.get('datetime'),
            strategy=record.get('strategy', ''),
            underlying_ticker=record.get('underlying_ticker', ''),
            previous_close=Decimal(record.get('previous_close', '0')),
            contract_type=record.get('contract_type', ''),
            direction=record.get('direction', ''),
            distance_between_strikes=Decimal(record.get('distance_between_strikes', '0')),
            short_contract=record.get('short_contract', {}),
            long_contract=record.get('long_contract', {}),
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
            expiration_date=record.get('expiration_date'),
            second_leg_depth=int(float(record.get('second_leg_depth', 0))),  # Convert to float first, then to int
            exit_date=record.get('exit_date'),
            description=record.get('description', '')  # Add description field
        )

    def to_dict(self, exclude=None):
        if exclude is None:
            exclude = ['client', 'contracts']
        
        # Collect initial attributes
        attributes = {
            key: (
                value.strftime('%Y-%m-%d') if isinstance(value, datetime.date) else
                self.round_decimal(value) if isinstance(value, (Decimal, int, float)) else 
                value
            )
            for key, value in self.__dict__.items()
            if key not in exclude and not key.startswith('_') and value is not None  # Exclude private and specified attributes
        }

        if self.long_contract is not None:
            attributes['long_contract'] = {
                key: self.round_decimal(value) if isinstance(value, (Decimal, int, float)) else value
                for key, value in self.long_contract.items()
            }

        if self.short_contract is not None:
            attributes['short_contract'] = {
                key: self.round_decimal(value) if isinstance(value, (Decimal, int, float)) else value
                for key, value in self.short_contract.items()
            }

        return attributes

    def round_decimal(self, value):
        """Converts to Decimal and rounds it to five decimal places, then converts to string."""
        return str(Decimal(value).quantize(Decimal('0.00000'), rounding=ROUND_HALF_UP))

    def to_json(self, exclude=None):
        return self.model_dump_json(exclude=exclude)