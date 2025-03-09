import pandas as pd
import numpy as np
from typing import Dict, Any

class StrategyCorrector:
    """Corrects inconsistent option strategy parameters."""
    
    @staticmethod
    def correct_debit_spread_direction(row: pd.Series) -> str:
        """
        Determines the correct direction for a debit spread based on the option strikes.
        
        Parameters:
        -----------
        row : pandas Series
            Row containing strategy parameters
            
        Returns:
        --------
        str
            Corrected direction ('bullish' or 'bearish')
        """
        short_contract = row.get('Short Contract', '')
        long_contract = row.get('Long Contract', '')
        
        try:
            short_strike = float(short_contract.split('P')[-1][:8]) if 'P' in short_contract else float(short_contract.split('C')[-1][:8])
            long_strike = float(long_contract.split('P')[-1][:8]) if 'P' in long_contract else float(long_contract.split('C')[-1][:8])
            is_put = 'P' in short_contract and 'P' in long_contract
            is_call = 'C' in short_contract and 'C' in long_contract
        except (ValueError, AttributeError, IndexError):
            return row.get('Direction', '')  # Return existing direction if parsing fails
        
        if is_put:
            # For puts: 
            # - Bullish: Buy higher strike, sell lower strike
            # - Bearish: Buy lower strike, sell higher strike
            return 'bullish' if long_strike > short_strike else 'bearish'
        elif is_call:
            # For calls: 
            # - Bullish: Buy lower strike, sell higher strike
            # - Bearish: Buy higher strike, sell lower strike
            return 'bullish' if long_strike < short_strike else 'bearish'
        
        return row.get('Direction', '')
    
    @staticmethod
    def correct_credit_spread_direction(row: pd.Series) -> str:
        """
        Determines the correct direction for a credit spread based on the option strikes.
        
        Parameters:
        -----------
        row : pandas Series
            Row containing strategy parameters
            
        Returns:
        --------
        str
            Corrected direction ('bullish' or 'bearish')
        """
        short_contract = row.get('Short Contract', '')
        long_contract = row.get('Long Contract', '')
        
        try:
            short_strike = float(short_contract.split('P')[-1][:8]) if 'P' in short_contract else float(short_contract.split('C')[-1][:8])
            long_strike = float(long_contract.split('P')[-1][:8]) if 'P' in long_contract else float(long_contract.split('C')[-1][:8])
            is_put = 'P' in short_contract and 'P' in long_contract
            is_call = 'C' in short_contract and 'C' in long_contract
        except (ValueError, AttributeError, IndexError):
            return row.get('Direction', '')  # Return existing direction if parsing fails
        
        if is_put:
            # For puts: 
            # - Bullish: Sell higher strike, buy lower strike
            # - Bearish: Sell lower strike, buy higher strike
            return 'bullish' if short_strike > long_strike else 'bearish'
        elif is_call:
            # For calls: 
            # - Bullish: Sell lower strike, buy higher strike
            # - Bearish: Sell higher strike, buy lower strike
            return 'bullish' if short_strike < long_strike else 'bearish'
        
        return row.get('Direction', '')
    
    @staticmethod
    def correct_strategy(df: pd.DataFrame) -> pd.DataFrame:
        """
        Corrects inconsistent strategy parameters in the DataFrame.
        
        Parameters:
        -----------
        df : pandas DataFrame
            DataFrame containing strategy parameters
            
        Returns:
        --------
        pandas DataFrame
            DataFrame with corrected strategy parameters
        """
        corrected_df = df.copy()
        
        for idx, row in df.iterrows():
            strategy_type = row.get('Strategy', '').lower()
            
            if strategy_type == 'debit':
                corrected_direction = StrategyCorrector.correct_debit_spread_direction(row)
                
                if corrected_direction != row.get('Direction', '').lower():
                    corrected_df.loc[idx, 'Direction'] = corrected_direction
                    print(f"Corrected row {idx}: Direction changed from '{row.get('Direction')}' to '{corrected_direction}'")
            
            elif strategy_type == 'credit':
                corrected_direction = StrategyCorrector.correct_credit_spread_direction(row)
                
                if corrected_direction != row.get('Direction', '').lower():
                    corrected_df.loc[idx, 'Direction'] = corrected_direction
                    print(f"Corrected row {idx}: Direction changed from '{row.get('Direction')}' to '{corrected_direction}'")
        
        return corrected_df
