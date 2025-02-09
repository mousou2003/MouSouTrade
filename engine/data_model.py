# Conclusion on this class:
# Next time I will use Libraries like Pydantic and Marshmallow provide powerful mechanisms for serialization and validation, 
# making it easier to handle complex data types, such as fixed-point decimals, while ensuring data integrity. 
# These libraries offer a concise way to deal with the serialization process rather than managing it manually, 
# helping to avoid common pitfalls associated with floating-point representation in databases like DynamoDB.

import json
from decimal import Decimal, ROUND_HALF_UP
import datetime

ASC = 'asc'
BEARISH = 'bearish'
BULLISH = 'bullish'
CREDIT = 'credit'
DEBIT = 'debit'
DESC = 'desc'
SPREAD_TYPE = {
    CREDIT: {BULLISH: 'call', BEARISH: 'put'},
    DEBIT: {BULLISH: 'call', BEARISH: 'put'}
}

class SpreadDataModel:
    datetime = None
    strategy = None
    underlying_ticker = None
    previous_close = None
    contract_type = None
    direction = None
    distance_between_strikes = None
    short_contract = None
    long_contract = None
    contracts = None
    daily_bars = None
    client = None
    long_premium = None
    short_premium = None
    max_risk = None
    max_reward = None
    breakeven = None
    entry_price = None
    target_price = None
    stop_price = None
    exit_date_str = None
    expiration_date = None
    second_leg_depth = None

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
        """Converts to Decimal and rounds it, then converts to string."""
        return str(Decimal(value).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP))
    
    def to_json(self, exclude=None):
        return json.dumps(self.to_dict(), default=str)  # Convert dictionary to JSON