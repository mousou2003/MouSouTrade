
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

    def to_dict(self, exclude=None):
        if exclude is None:
            exclude = ['client']
        
        # Collect initial attributes
        attributes = {
            key: self.round_decimal(value) if isinstance(value, float) else value
            for key, value in self.__dict__.items()
            if key not in exclude and not key.startswith('_')  # Exclude private and specified attributes
        }
        
        # Process contracts to convert any nested dict floats to Decimal
        attributes['contracts'] = self.convert_all_floats_to_decimal_in_list(attributes['contracts'])

        return attributes

    def convert_all_floats_to_decimal_in_list(self, attr_list):
        """Convert all float values in a list of dictionaries to Decimal."""
        for item in attr_list:
            if isinstance(item, dict):
                for key, value in item.items():
                    if isinstance(value, (float, int)):
                        item[key] = self.round_decimal(value=value)
        return attr_list
    
    def round_decimal(self, value):
        """Converts float to Decimal and rounds it to 5 decimal places, then converts to string."""
        return str(Decimal(value).quantize(Decimal('0.00000'), rounding=ROUND_HALF_UP))
    
    def to_json(self, exclude=None):
        return json.dumps(self.to_dict(), default=str)  # Convert dictionary to JSON
