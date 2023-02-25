import calendar
import datetime
import logging
import operator
from MarketDataClients.MarketDataClient import MarketDataStrikeNotFoundException, MarketDataException, MarketDataClient

class Option:

    def get_thirdFridayOfMonth(year,month):
        c = calendar.Calendar(firstweekday=calendar.SUNDAY)
        monthcal = c.monthdatescalendar(year,month)
        third_friday = [day for week in monthcal for day in week if \
                day.weekday() == calendar.FRIDAY and \
                day.month == month][2]
        return third_friday
    
    def get_thirdFridayOfCurrentMonth():
        today = datetime.datetime.today()
        year = today.year; month = today.month
        return Option.get_thirdFridayOfMonth(year,month)
        
    def get_followingThirdFriday():
        today = datetime.datetime.today()
        year = today.year; month = today.month + 1
        return Option.get_thirdFridayOfMonth(year,month)


# Class definition:
# This class is a generic class to be used for a Blulish or Bearish vertical spread.
#
# Theory behind:
# Credit spread are profitable if the underlying stock price make movement in the direction
# predicted. Its a forgiving strategy because even if the stock make a slight movement 
# in the oposite direction it can still be profitable.
class VerticalSpread:
    BEARISH='bearish'
    BULLISH='bullish'
    CALL='call'
    PUT='put'
    CREDIT = 'credit'
    DEBIT='debit'
    ASC='asc'
    DESC='desc'
    SPREAD_TYPE={CREDIT:{BULLISH:PUT, BEARISH:CALL},DEBIT:{BULLISH:CALL, BEARISH:PUT}}
    REQUEST_ORDER={CREDIT:{BULLISH:DESC, BEARISH:ASC},DEBIT:{BULLISH:ASC, BEARISH:DESC}}
    SEARCH_OPS={CREDIT:{BULLISH:operator.ge, BEARISH:operator.le},DEBIT:{BULLISH:operator.le, BEARISH:operator.ge}}
    WRONG_DIRECTION_ADJ_OPS={CREDIT:{BULLISH:operator.sub, BEARISH:operator.add},DEBIT:{BULLISH:operator.add, BEARISH:operator.sub}}
    GOOD_DIRECTION_ADJ_OPS={CREDIT:{BULLISH:operator.add, BEARISH:operator.sub},DEBIT:{BULLISH:operator.sub, BEARISH:operator.add}}
    MAX_STRIKES = 20 # we limit the number of strike to improve performance
    MIN_DELTA =0.26 # no benefit to sell or buy an option under this delta

    underlying_ticker = None
    sell_symbol = None
    buy_symbol = None
    short_contract = None
    short_premium = None
    long_contract = None
    long_premium = None
    previous_close = None
    contract_type = None
    direction = None
    strategy = None
    order = None
    distance_between_Strikes = None

    client = None

    def __init__(self, underlying_ticker, direction, strategy, client):
        logging.info("processing %s"%underlying_ticker)
        self.underlying_ticker = underlying_ticker
        self.client = MarketDataClient()
        self.previous_close = self.client.get_previous_stock_close(self.underlying_ticker)
        logging.info("%s last close price :%s"% (self.underlying_ticker, self.previous_close))
        self.contract_type = self.SPREAD_TYPE[strategy][direction]
        self.order = self.REQUEST_ORDER[strategy][direction]
        self.direction = direction
        self.strategy = strategy


    def calculateAbsDelta(self, previous_premium, premium, previous_price, price):
        premium_delta =  previous_premium - premium
        price_delta = previous_price -price
        return abs(premium_delta/price_delta)

    def matchOption(self, expiration_date_gte, expiration_date_lte):
        previous_premium = None
        previous_contract = None
 
        n_strikes = 0
        for contract in self.client.get_option_contracts( underlying_ticker=self.underlying_ticker, 
            expiration_date_gte=expiration_date_gte, 
            expiration_date_lte=expiration_date_lte,
            contract_type=self.contract_type,
            order=self.order):

            try:
                # We take the first strike above the previous close. This could be improve by looking for the 50 delta
                if self.SEARCH_OPS[self.strategy][self.direction](self.previous_close,round(float(contract['strike_price']),1))  and \
                    n_strikes < self.MAX_STRIKES:
                    n_strikes += 1
                    premium = None
                    logging.debug("procesing %s"%contract['ticker'])
                    if  self.short_contract == None:
                        premium= self.client.get_option_previous_close(contract['ticker'])
                        #previous_premium = MarketDataClients().get_option_previous_close(previous_contract['ticker'])
                        #delta = self.calculateAbsDelta(float(previous_premium), float(premium),float(contract['strike_price']), float(previous_contract['strike_price']))
                        # if delta < 0.5:
                        #     self.short_contract = previous_contract
                        #     self.short_premium = previous_premium
                        # else:    
                        self.short_contract = contract
                        self.short_premium = premium
                        contract['premium'] = premium
                        self.sell_symbol = contract
                        logging.info("Found a SHORT with :%s for a premium of %.2f"% (self.short_contract['ticker'],premium ))
                        logging.debug(contract)
                    else:
                        if self.short_contract['expiration_date'] != contract['expiration_date']:
                            logging.warning("Exit as we are going vertical")
                            break
                        self.distance_between_Strikes = abs(float(float(contract['strike_price']-self.short_contract['strike_price'])))
                        premium= self.client.get_option_previous_close(contract['ticker'])
                        delta = self.calculateAbsDelta(previous_premium=float(previous_premium), premium=float(premium), previous_price=previous_contract['strike_price'] , price=float(contract['strike_price']))
                        logging.debug('delta %s, self.distance_between_Strikes %s'%(delta , self.distance_between_Strikes))
                        if delta <= self.MIN_DELTA:
                            spread_premium = abs(float(self.short_premium) -float(premium))
                            logging.debug('spread_premium %s',spread_premium)
                            if spread_premium >= self.distance_between_Strikes/3:
                                contract['premium'] = premium
                                self.long_contract = contract
                                self.long_premium = premium
                                self.buy_symbol = contract
                                logging.info("Found a LONG with :%s for a premium of %.2f with short delta of %.2f"% (contract['ticker'],premium, delta))
                                logging.debug(contract)
                            # We stop searching for match when we reach the MIN_DELTA
                            break        
                    previous_premium = premium
            except MarketDataStrikeNotFoundException as err:
                logging.info(err)
            except ZeroDivisionError as err:
                logging.warning('Division by zero when calculating delta, for %s \n with %s'%(contract,self.short_contract),err)

            previous_contract = contract
        return self.short_contract !=None and self.long_contract !=None

    def get_Long(self):
        return self.buy_symbol
    
    def get_short(self):
        return self.sell_symbol

    def get_max_risk(self):
        pass

    def get_breakeven_price(self):
        pass

    def get_close_price(self):
        return self.previous_close

    def get_target_price(self):
        pass

    def get_stop_price(self):
        pass

    def get_exit_date(self):
        pass



class CreditSpread(VerticalSpread):

    idealExpiration = 45

    def __init__(self, underlying_ticker, direction, strategy, client):
        super().__init__(underlying_ticker=underlying_ticker, direction=direction, strategy=strategy, client=client)

    def matchOption(self, date=None):
        if date != None:
            return super().matchOption(expiration_date_gte=date, 
            expiration_date_lte=date)
        else:
            return super().matchOption(expiration_date_gte=datetime.date.today() + datetime.timedelta(days = self.idealExpiration-4), 
            expiration_date_lte=datetime.date.today() + datetime.timedelta(days = self.idealExpiration+2))
    
    def get_target_price(self):
        return self.GOOD_DIRECTION_ADJ_OPS[self.strategy][self.direction](self.previous_close, self.get_max_reward())

    def get_stop_price(self):
        return self.WRONG_DIRECTION_ADJ_OPS[self.strategy][self.direction](self.previous_close , 2*self.get_max_reward())

    def get_breakeven_price(self):
        return self.WRONG_DIRECTION_ADJ_OPS[self.strategy][self.direction](float(self.short_contract['strike_price']),self.get_max_reward())

    def get_exit_date(self):
        return datetime.datetime.strptime(self.short_contract['expiration_date'],'%Y-%m-%d') - datetime.timedelta(days = 21)

    def get_max_reward(self):
        return (self.short_premium - self.long_premium)

    def get_max_risk(self):
        return abs(self.distance_between_Strikes - self.get_max_reward())

    def get_plain_English_Result(self):
        return format("%s %s spread: Sell %s, Buy %s; max risk %.2f, max reward %.2f, breakeven %.2f, enter at %.2f, target exit at %.2f, stop loss at %.2f and before %s"%
                    (self.direction, self.strategy, self.get_short()['ticker'], self.get_Long()['ticker'], self.get_max_risk(),
                    self.get_max_reward(), self.get_breakeven_price(), self.get_close_price(),
                    self.get_target_price(), self.get_stop_price(), datetime.datetime.strftime(self.get_exit_date(),'%Y-%m-%d')))
