import calendar
import datetime
import logging
from marketdata_clients.PolygonOptionsClient import PolygonOptionsClient

logger = logging.getLogger(__name__)

class Options:
    """Helper class for calculating option expiration dates and fetching option contracts."""
    def __init__(self, underlying_ticker, expiration_date_gte, expiration_date_lte, contract_type, order):
        self.client = PolygonOptionsClient()
        self.underlying_ticker = underlying_ticker
        self.expiration_date_gte = expiration_date_gte
        self.expiration_date_lte = expiration_date_lte
        self.contract_type = contract_type
        self.order = order

    def get_option_contracts(self):
        return self.client.get_option_contracts(
            underlying_ticker=self.underlying_ticker,
            expiration_date_gte=self.expiration_date_gte,
            expiration_date_lte=self.expiration_date_lte,
            contract_type=self.contract_type,
            order=self.order
        )

    def get_option_previous_close(self, ticker):
        return self.client.get_option_previous_close(ticker)

    def get_snapshot(
        self,
        option_symbol: str = None
    ):
        return self.client.get_snapshot(
            underlying_symbol=self.underlying_ticker,
            option_symbol=option_symbol
        )
    
    @staticmethod
    def get_third_friday_of_month(year, month):
        """Calculates the date of the third Friday of a given month and year."""
        c = calendar.Calendar(firstweekday=calendar.SUNDAY)
        monthcal = c.monthdatescalendar(year, month)
        third_friday = [day for week in monthcal for day in week if
                        day.weekday() == calendar.FRIDAY and
                        day.month == month][2]
        return third_friday

    @staticmethod
    def get_next_friday(date):
        """Calculates the date of the next Friday after a given date."""
        days_ahead = 4 - date.weekday()  # Friday is the 4th day of the week (0-indexed)
        if days_ahead <= 0:  # Target day already passed this week
            days_ahead += 7
        next_friday = date + datetime.timedelta(days=days_ahead)
        return next_friday

    @staticmethod
    def get_third_friday_of_current_month():
        """Calculates the date of the third Friday of the current month."""
        today = datetime.datetime.today()
        year = today.year
        month = today.month
        return Options.get_third_friday_of_month(year, month)

    @staticmethod
    def get_following_third_friday():
        """Calculates the date of the third Friday of the next month."""
        today = datetime.datetime.today()
        year = today.year
        month = today.month + 1
        return Options.get_third_friday_of_month(year, month)
    