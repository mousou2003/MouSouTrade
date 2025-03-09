"""
Strategy Validator
=================
This module provides functionality to validate option spread strategies against established 
trading principles. It ensures that spreads have the correct:

1. Strike price relationships based on strategy type:
   - Bull Call Debit: Long lower strike, short higher strike
   - Bull Put Credit: Short higher strike, long lower strike  
   - Bear Put Debit: Long higher strike, short lower strike
   - Bear Call Credit: Short higher strike, long lower strike

2. Price target consistency with market direction:
   - Bullish strategies: Target price > Entry price, Stop price < Entry price
   - Bearish strategies: Target price < Entry price, Stop price > Entry price

3. Contract type consistency (calls with calls, puts with puts)

The validator also provides utility functions to extract information from option contract strings 
and convert between different data formats.

This module is crucial for ensuring that spread strategies meet the requirements for proper
risk management and directional exposure.
"""

import logging
import re
from typing import List, Dict, Any, Union, Optional
from decimal import Decimal, InvalidOperation, ConversionSyntax
from engine.data_model import SpreadDataModel, Contract, StrategyType, DirectionType, ContractType

logger = logging.getLogger(__name__)

class StrategyValidator:
    """Validates option strategy parameters for consistency."""
    
    @staticmethod
    def extract_strike_price(contract_str: str) -> Optional[Decimal]:
        """
        Extract strike price from an option contract string using regex.
        
        Format expected: O:SYMBOL{YYMMDD}{C/P}{STRIKE*10000}
        Example: O:AAPL250117C00210000 -> 21.0 (Call option on AAPL)
        
        Args:
            contract_str: String representation of the option contract
            
        Returns:
            Decimal: Strike price if successfully parsed, None otherwise
        """
        try:
            # Pattern to match option contract format and extract strike price digits
            pattern = r'O:[A-Z]+\d+[CP](\d+)'
            match = re.search(pattern, contract_str)
            
            if match:
                # Extract the strike price digits
                strike_digits = match.group(1)
                # Convert to integer to remove leading zeros
                strike_int = int(strike_digits)
                # Convert to Decimal and divide by 10000
                return Decimal(strike_int) / Decimal(10000)
            else:
                logger.warning(f"Contract string '{contract_str}' does not match the expected format")
                return None
        except (ValueError, AttributeError, IndexError, InvalidOperation, ConversionSyntax) as e:
            logger.error(f"Failed to extract strike price from {contract_str}: {str(e)}")
            return None
    
    @staticmethod
    def extract_option_type(contract_str: str) -> Optional[str]:
        """
        Extract option type (call/put) from an option contract string using regex.
        
        Args:
            contract_str: String representation of the option contract
            
        Returns:
            str: 'call' or 'put' if successfully parsed, None otherwise
        """
        try:
            pattern = r'O:[A-Z]+\d+([CP])\d+'
            match = re.search(pattern, contract_str)
            
            if match:
                option_type = match.group(1)
                return 'call' if option_type == 'C' else 'put'
            else:
                logger.warning(f"Contract string '{contract_str}' does not match the expected format")
                return None
        except Exception as e:
            logger.error(f"Failed to extract option type from {contract_str}: {str(e)}")
            return None
    
    @staticmethod
    def validate_debit_spread(spreads: List[SpreadDataModel]) -> List[str]:
        """
        Validates debit spread strategy parameters for consistency.
        
        Parameters:
        -----------
        spreads : List of SpreadDataModel objects
            List containing spread data
            
        Returns:
        --------
        list of str
            List of validation errors, empty if no errors
        """
        errors = []
        
        for idx, spread in enumerate(spreads):
            if not spread.strategy or spread.strategy != StrategyType.DEBIT:
                continue
                
            direction = spread.direction.value if spread.direction else ''
            short_contract = spread.short_contract
            long_contract = spread.long_contract
            
            # Create a descriptive name for the spread
            spread_name = f"{direction.capitalize()} {short_contract.contract_type.value} {spread.strategy.value} spread"
            
            if not short_contract or not long_contract:
                errors.append(f"{spread_name}: Missing contract information")
                continue
                
            short_strike = short_contract.strike_price if short_contract.strike_price else None
            long_strike = long_contract.strike_price if long_contract.strike_price else None
            
            if not short_strike or not long_strike:
                errors.append(f"{spread_name}: Missing strike price information")
                continue
            
            short_type = short_contract.contract_type
            long_type = long_contract.contract_type
            
            if short_type != long_type:
                errors.append(f"{spread_name}: Contract types don't match: {short_type} vs {long_type}")
                continue
            
            is_put = short_type == ContractType.PUT
            is_call = short_type == ContractType.CALL
            
            # Check direction consistency
            if direction == 'bullish':
                # Bullish spread: target > entry, stop < entry
                if spread.target_price <= spread.entry_price:
                    errors.append(f"{spread_name}: Bullish strategy has target price ({spread.target_price}) <= entry price ({spread.entry_price})")
                if spread.stop_price >= spread.entry_price:
                    errors.append(f"{spread_name}: Bullish strategy has stop price ({spread.stop_price}) >= entry price ({spread.entry_price})")
                
                # For call debit spread (bullish): buy lower strike, sell higher strike
                if is_call and long_strike >= short_strike:
                    errors.append(f"{spread_name}: Bullish call debit spread should buy lower strike and sell higher strike")
                
            elif direction == 'bearish':
                # Bearish spread: target < entry, stop > entry
                if spread.target_price >= spread.entry_price:
                    errors.append(f"{spread_name}: Bearish strategy has target price ({spread.target_price}) >= entry price ({spread.entry_price})")
                if spread.stop_price <= spread.entry_price:
                    errors.append(f"{spread_name}: Bearish strategy has stop price ({spread.stop_price}) <= entry price ({spread.entry_price})")
                
                # For put debit spread (bearish): buy higher strike, sell lower strike
                if is_put and long_strike <= short_strike:
                    errors.append(f"{spread_name}: Bearish put debit spread should buy higher strike and sell lower strike")
        
        return errors
    
    @staticmethod
    def validate_credit_spread(spreads: List[SpreadDataModel]) -> List[str]:
        """
        Validates credit spread strategy parameters for consistency.
        
        Parameters:
        -----------
        spreads : List of SpreadDataModel objects
            List containing spread data
            
        Returns:
        --------
        list of str
            List of validation errors, empty if no errors
        """
        errors = []
        
        for idx, spread in enumerate(spreads):
            if not spread.strategy or spread.strategy != StrategyType.CREDIT:
                continue
                
            direction = spread.direction.value if spread.direction else ''
            short_contract = spread.short_contract
            long_contract = spread.long_contract
            
            # Create a descriptive name for the spread
            spread_name = f"{direction.capitalize()} {short_contract.contract_type.value} {spread.strategy.value} spread"
            
            if not short_contract or not long_contract:
                errors.append(f"{spread_name}: Missing contract information")
                continue
                
            short_strike = short_contract.strike_price if short_contract.strike_price else None
            long_strike = long_contract.strike_price if long_contract.strike_price else None
            
            if not short_strike or not long_strike:
                errors.append(f"{spread_name}: Missing strike price information")
                continue
            
            short_type = short_contract.contract_type
            long_type = long_contract.contract_type
            
            if short_type != long_type:
                errors.append(f"{spread_name}: Contract types don't match: {short_type} vs {long_type}")
                continue
            
            is_put = short_type == ContractType.PUT
            is_call = short_type == ContractType.CALL
            
            # Check direction consistency
            if direction == 'bullish':
                # Bullish spread: target > entry, stop < entry
                if spread.target_price <= spread.entry_price:
                    errors.append(f"{spread_name}: Bullish strategy has target price ({spread.target_price}) <= entry price ({spread.entry_price})")
                if spread.stop_price >= spread.entry_price:
                    errors.append(f"{spread_name}: Bullish strategy has stop price ({spread.stop_price}) >= entry price ({spread.entry_price})")
                
                # For put credit spread (bullish): sell higher strike, buy lower strike
                if is_put and short_strike <= long_strike:
                    errors.append(f"{spread_name}: Bullish put credit spread should sell higher strike and buy lower strike")
                
            elif direction == 'bearish':
                # Bearish spread: target < entry, stop > entry
                if spread.target_price >= spread.entry_price:
                    errors.append(f"{spread_name}: Bearish strategy has target price ({spread.target_price}) >= entry price ({spread.entry_price})")
                if spread.stop_price <= spread.entry_price:
                    errors.append(f"{spread_name}: Bearish strategy has stop price ({spread.stop_price}) <= entry price ({spread.entry_price})")
                
                # For call credit spread (bearish): sell higher strike, buy lower strike
                if is_call and short_strike <= long_strike:
                    errors.append(f"{spread_name}: Bearish call credit spread should sell higher strike and buy lower strike")
        
        return errors
    
    @staticmethod
    def validate_vertical_spread(spreads: List[SpreadDataModel]) -> List[str]:
        """
        Validates both debit and credit vertical spread strategy parameters for consistency.
        
        Parameters:
        -----------
        spreads : List of SpreadDataModel objects
            List containing spread data
            
        Returns:
        --------
        list of str
            List of validation errors, empty if no errors
        """
        errors = []
        
        # Separate debit and credit spreads
        debit_spreads = []
        credit_spreads = []
        
        for spread in spreads:
            if spread.strategy == StrategyType.DEBIT:
                debit_spreads.append(spread)
            elif spread.strategy == StrategyType.CREDIT:
                credit_spreads.append(spread)
            
        # Validate debit spreads
        if debit_spreads:
            errors.extend(StrategyValidator.validate_debit_spread(debit_spreads))
            
        # Validate credit spreads
        if credit_spreads:
            errors.extend(StrategyValidator.validate_credit_spread(credit_spreads))
            
        return errors
    
    @staticmethod
    def validate_spread_model(spread_model: SpreadDataModel) -> List[str]:
        """
        Validates a single SpreadDataModel object.
        
        Parameters:
        -----------
        spread_model : SpreadDataModel
            The spread data model to validate
            
        Returns:
        --------
        list of str
            List of validation errors, empty if no errors
        """
        return StrategyValidator.validate_vertical_spread([spread_model])
    
    @staticmethod
    def create_spread_model_from_dict(spread_dict: Dict[str, Any]) -> SpreadDataModel:
        """
        Create a SpreadDataModel from a dictionary representation.
        
        Parameters:
        -----------
        spread_dict : Dict
            Dictionary containing spread information
            
        Returns:
        --------
        SpreadDataModel
            A SpreadDataModel object created from the dictionary
        """
        # Extract values from the dictionary
        short_contract_str = spread_dict.get('Short Contract', '')
        long_contract_str = spread_dict.get('Long Contract', '')
        
        # Extract strike prices
        short_strike = StrategyValidator.extract_strike_price(short_contract_str)
        long_strike = StrategyValidator.extract_strike_price(long_contract_str)
        
        # Get option types using regex
        short_type_str = StrategyValidator.extract_option_type(short_contract_str)
        long_type_str = StrategyValidator.extract_option_type(long_contract_str)
        
        # Create Contract objects directly
        short_contract = Contract()
        short_contract.ticker = short_contract_str
        short_contract.contract_type = ContractType.CALL if short_type_str == 'call' else ContractType.PUT
        short_contract.strike_price = short_strike if short_strike is not None else Decimal('0')
        
        long_contract = Contract()
        long_contract.ticker = long_contract_str
        long_contract.contract_type = ContractType.CALL if long_type_str == 'call' else ContractType.PUT
        long_contract.strike_price = long_strike if long_strike is not None else Decimal('0')
        
        # Convert prices to Decimal
        try:
            entry_price = Decimal(spread_dict.get('Entry Price', '0'))
            target_price = Decimal(spread_dict.get('Target Price', '0'))
            stop_price = Decimal(spread_dict.get('Stop Price', '0'))
        except (InvalidOperation, ValueError) as e:
            logger.error(f"Failed to convert price to Decimal: {str(e)}")
            entry_price = Decimal('0')
            target_price = Decimal('0')
            stop_price = Decimal('0')
        
        # Create the SpreadDataModel instance and set properties directly
        spread_model = SpreadDataModel()
        spread_model.strategy = StrategyType.CREDIT if spread_dict.get('Strategy', '').lower() == 'credit' else StrategyType.DEBIT
        spread_model.direction = DirectionType.BULLISH if spread_dict.get('Direction', '').lower() == 'bullish' else DirectionType.BEARISH
        spread_model.short_contract = short_contract
        spread_model.long_contract = long_contract
        spread_model.entry_price = entry_price
        spread_model.target_price = target_price
        spread_model.stop_price = stop_price
        spread_model.underlying_ticker = spread_dict.get('Ticker', '')
        
        return spread_model
