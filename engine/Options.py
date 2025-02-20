import calendar
import datetime
import logging
from marketdata_clients.PolygonOptionsClient import PolygonOptionsClient
import numpy as np
from scipy.stats import norm
from decimal import Decimal

logger = logging.getLogger(__name__)

class Options:
    """Helper class for calculating option expiration dates and fetching option contracts."""
    def __init__(self, underlying_ticker, expiration_date_gte: datetime.date, expiration_date_lte: datetime.date, contract_type, order, r=0.05, sigma=0.2):
        self.client = PolygonOptionsClient()
        self.underlying_ticker = underlying_ticker
        self.expiration_date_gte = expiration_date_gte
        self.expiration_date_lte = expiration_date_lte
        self.contract_type = contract_type
        self.order = order
        self.r = r  # Risk-free interest rate (5%)
        self.sigma = sigma  # Implied volatility (20%)

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
    
    def estimate_premium(
        self,
        option_symbol: str = None
    ):
        return self.client.estimate_premium(
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
    def get_next_friday(date: datetime.date):
        """Calculates the date of the next Friday after a given date."""
        days_ahead = 4 - date.weekday()  # Friday is the 4th day of the week (0-indexed)
        if days_ahead <= 0:  # Target day already passed this week
            days_ahead += 7
        next_friday = date + datetime.timedelta(days=days_ahead)
        return next_friday

    @staticmethod
    def get_third_friday_of_current_month():
        """Calculates the date of the third Friday of the current month."""
        today = datetime.datetime.today().date()
        year = today.year
        month = today.month
        return Options.get_third_friday_of_month(year, month)

    @staticmethod
    def get_following_third_friday():
        """Calculates the date of the third Friday of the next month."""
        today = datetime.datetime.today().date()
        year = today.year
        month = today.month + 1
        return Options.get_third_friday_of_month(year, month)
    
    @staticmethod
    def black_scholes_call(self, S, K, T):
        """
        Calculate the Black-Scholes call option price.
        
        Parameters:
        S : float : Current stock price
        K : float : Strike price
        T : float : Time to expiration in years
        
        Returns:
        float : Call option price
        """
        d1 = (np.log(S / K) + (self.r + 0.5 * self.sigma ** 2) * T) / (self.sigma * np.sqrt(T))
        d2 = d1 - self.sigma * np.sqrt(T)
        call_price = S * norm.cdf(d1) - K * np.exp(-self.r * T) * norm.cdf(d2)
        return call_price

    @staticmethod
    def black_scholes_put(self, S, K, T):
        """
        Calculate the Black-Scholes put option price.
        
        Parameters:
        S : float : Current stock price
        K : float : Strike price
        T : float : Time to expiration in years
        
        Returns:
        float : Put option price
        """
        d1 = (np.log(S / K) + (self.r + 0.5 * self.sigma ** 2) * T) / (self.sigma * np.sqrt(T))
        d2 = d1 - self.sigma * np.sqrt(T)
        put_price = K * np.exp(-self.r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        return put_price

    @staticmethod
    def calculate_probability_of_profit(current_price: Decimal, breakeven_price: Decimal, days_to_expiration: int, implied_volatility: Decimal) -> Decimal:
        """
        Calculate the Probability of Profit (POP) for an option position.
        
        Parameters:
        current_price : Decimal : Current price of the underlying asset
        breakeven_price : Decimal : Breakeven price of the option position
        days_to_expiration : int : Number of days until the option expires
        implied_volatility : Decimal : Implied volatility of the underlying asset
        
        Returns:
        Decimal : Probability of Profit (POP) as a percentage
        """
        # Calculate standard deviation for the underlying asset price
        annualized_sd = implied_volatility * current_price
        daily_sd = annualized_sd / Decimal(np.sqrt(252))  # 252 trading days in a year
        price_movement_sd = daily_sd * Decimal(np.sqrt(days_to_expiration))

        # Calculate Z-Score for Breakeven
        z_score = (breakeven_price - current_price) / price_movement_sd

        # Calculate Probability of Profit (POP)
        probability_of_profit = Decimal(norm.cdf(float(z_score)))

        return probability_of_profit * Decimal(100)
        """
        Calculate the Probability of Profit (POP) for an option position.
        
        Parameters:
        current_price : float : Current price of the underlying asset
        breakeven_price : float : Breakeven price of the option position
        days_to_expiration : int : Number of days until the option expires
        implied_volatility : float : Implied volatility of the underlying asset
        
        Returns:
        float : Probability of Profit (POP) as a percentage
        """
        # Calculate standard deviation for the underlying asset price
        annualized_sd = implied_volatility * current_price
        daily_sd = annualized_sd / np.sqrt(252)  # 252 trading days in a year
        price_movement_sd = daily_sd * np.sqrt(days_to_expiration)

        # Calculate Z-Score for Breakeven
        z_score = (breakeven_price - current_price) / price_movement_sd

        # Calculate Probability of Profit (POP)
        probability_of_profit = norm.cdf(z_score)

        return probability_of_profit * 100