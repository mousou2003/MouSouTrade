
import json

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


class SpreadDataModel:
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

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=False, indent=4)
