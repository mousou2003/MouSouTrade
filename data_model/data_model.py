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
    Datetime = None
    Strategy = None
    UnderlyingTicker = None
    PreviousClose = None
    ContractType = None
    Direction = None
    DistanceBetweenStrikes = None
    ShortContract = None
    LongContract = None
    Contracts = None
    DailyBars = None
    Client = None
    LongPremium = None
    ShortPremium = None
    MaxRisk = None
    MaxReward = None
    Breakeven = None
    EntryPrice = None
    TargetPrice = None
    StopPrice = None
    ExitDateStr = None
    ExpirationDate = None
    ExitDateStr = None
    SecondLegDepth = None

    def to_dict(self, exclude=None):
        if exclude is None:
            exclude = ['client', 'contracts']
        
        # Collect initial attributes
        attributes = {
            key: (
                value.strftime('%Y-%m-%d') if isinstance(value, datetime.date) else
                self.round_decimal(value) if isinstance(value, float) else 
                value
            )
            for key, value in self.__dict__.items()
            if key not in exclude and not key.startswith('_') and value is not None  # Exclude private and specified attributes
        }

        if self.LongContract is not None:
            attributes['LongContract'] = {
                key: self.round_decimal(value) if isinstance(value, (Decimal, int)) else value
                for key, value in self.LongContract.items()
            }

        if self.ShortContract is not None:
            attributes['ShortContract'] = {
                key: self.round_decimal(value) if isinstance(value, (Decimal, int)) else value
                for key, value in self.ShortContract.items()
            }
        return attributes

    def round_decimal(self, value):
        """Converts float to Decimal and rounds it to 5 decimal places, then converts to string."""
        return str(Decimal(value).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP))
    
    def to_json(self, exclude=None):
        return json.dumps(self.to_dict(), default=str)  # Convert dictionary to JSON