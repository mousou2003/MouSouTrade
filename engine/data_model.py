
#Conclusion on this class:
#Next time I will use Libraries like Pydantic and Marshmallow provide powerful mechanisms for serialization and validation, 
#making it easier to handle complex data types, such as fixed-point decimals, while ensuring data integrity. 
#These libraries offer a concise way to deal with the serialization process rather than managing it manually, 
#helping to avoid common pitfalls associated with floating-point representation in databases like DynamoDB.

   
import json
from decimal import Decimal, ROUND_HALF_UP

BEARISH = 'bearish'
BULLISH = 'bullish'
CALL = 'call'
PUT = 'put'
CREDIT = 'credit'
DEBIT = 'debit'
ASC = 'asc'
DESC = 'desc'
SPREAD_TYPE = {CREDIT: {BULLISH: PUT, BEARISH: CALL},
               DEBIT: {BULLISH: CALL, BEARISH: PUT}}


class SpreadDataModel():
    datetime = None
    strategy = None
    underlying_ticker = None
    previous_close = None
    contract_type = None
    direction = None
    distance_between_Strikes = None
    short_contract = None
    long_contract = None
    contracts = None
    daily_bars = None
    client = None
    long_premium = None
    short_premium = None
    buy_sell = None
    max_risk = None
    max_reward = None
    breakeven = None
    entry_price = None
    target_price = None
    stop_price = None
    exit_date_str = None
    distance_between_Strikes = None
    expiration_date = None
    exit_date_str = None

    def to_dict(self, exclude=None):
        if exclude is None:
            exclude = ['client','contracts']
        
        # Collect initial attributes
        attributes = {
            key: self.round_decimal(value) if isinstance(value, float) else value
            for key, value in self.__dict__.items()
            if key not in exclude and not key.startswith('_')  # Exclude private and specified attributes
        }

        attributes['long_contract'] = {
            key: self.round_decimal(value) if isinstance(value, (Decimal,int)) else value
            for key, value in  self.long_contract.items()
        }
        attributes['short_contract'] = {
            key: self.round_decimal(value) if isinstance(value, (Decimal,int)) else value
            for key, value in  self.short_contract.items()
        }
        return attributes

    
    def round_decimal(self, value):
        """Converts float to Decimal and rounds it to 5 decimal places, then converts to string."""
        return str(Decimal(value).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP))
    
    def to_json(self, exclude=None):
        return json.dumps(self.to_dict(), default=str)  # Convert dictionary to JSON
