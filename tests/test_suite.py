"""
Test Suite Runner
================
This module provides functionality to run all tests for the MouSouTrade system.
It automatically discovers and collects all test cases from the test files, allowing
comprehensive test coverage evaluation in a single run.

The test suite includes:
1. Strategy validation tests - Ensuring correct option spread configurations
2. Vertical spread selection tests - Verifying proper contract selection algorithms
3. Any other test classes added to the imports

This file can be run directly to execute all tests or can be used by CI/CD 
pipelines for automated testing.
"""

import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all test cases
from tests.test_vertical_spread_selection import TestVerticalSpreadStrikeSelection
from tests.test_strategy_validator import TestStrategyValidator

def create_test_suite():
    """Create a test suite that includes all tests."""
    # Create a test suite using the newer loader approach instead of makeSuite
    loader = unittest.TestLoader()
    test_suite = unittest.TestSuite()
    
    # Add tests from TestVerticalSpreadStrikeSelection
    test_suite.addTest(loader.loadTestsFromTestCase(TestVerticalSpreadStrikeSelection))
    
    # Add tests from TestStrategyValidator
    test_suite.addTest(loader.loadTestsFromTestCase(TestStrategyValidator))
    
    return test_suite

def run_all_tests():
    """Run all tests and return the test result."""
    runner = unittest.TextTestRunner(verbosity=2)
    test_suite = create_test_suite()
    return runner.run(test_suite)

if __name__ == '__main__':
    """Run all tests in the test suite."""
    result = run_all_tests()
    # Exit with non-zero code if tests failed, for CI integration
    sys.exit(0 if result.wasSuccessful() else 1)
