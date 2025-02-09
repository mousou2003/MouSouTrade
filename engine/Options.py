import calendar
import datetime
import logging

logger = logging.getLogger(__name__)

class Option:
    """Helper class for calculating option expiration dates."""
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
    def get_third_friday_of_current_month():
        """Calculates the date of the third Friday of the current month."""
        today = datetime.datetime.today()
        year = today.year
        month = today.month
        return Option.get_third_friday_of_month(year, month)

    @staticmethod
    def get_following_third_friday():
        """Calculates the date of the third Friday of the next month."""
        today = datetime.datetime.today()
        year = today.year
        month = today.month + 1
        return Option.get_third_friday_of_month(year, month)