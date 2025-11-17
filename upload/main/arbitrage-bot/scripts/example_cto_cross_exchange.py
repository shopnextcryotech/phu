"""
Example usage of the CrossExchangeUSDCBTCStrategy.

This script demonstrates how to:
1. Initialize the strategy with API connectors
2. Continuously scan for opportunities
3. Execute profitable trades
4. Handle results and errors
5. Monitor performance

Note: This is a demonstration. In production, you'd integrate with real exchange APIs.
"""

import logging
import time
import json
from decimal import Decimal
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("arbitrage_bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class MockExchangeAPI:
    """
    Mock exchange API for demonstration.
    In production, replace with real API connectors.
    """

    def __init__(self, name: str, static_prices: Optional[dict] = None):
        self.name = name
        self.static_prices = static_prices or {}

    def get_orderbook(self, symbol: str) -> dict:
        """
        Mock order book fetching.
        Returns static test data.
        """
        if self.name == "MEXC":
            return {
                "bids": [[39900, 5.0]],
                "asks": [
                    [40000, 1.0],
                    [40100, 2.0],
                    [40200, 3.0],
                ],
            }
        elif self.name == "BingX":
            return {
                "bids": [
                    [40500, 0.3],
                    [40400, 0.5],
                    [40300, 1.0],
                    [40200, 2.0],
                    [40100, 5.0],
                ],
                "asks": [[40600, 10.0]],
            }

    def place_limit_buy(
        self, symbol: str, amount: float, price: float
    ) -> dict:
        """Mock limit buy order placement."""
        logger.info(
            "%s: Placing limit buy for %.8f %s at %.2f",
            self.name,
            amount,
            symbol,
            price,
        )
        return {
            "order_id": f"{self.name}_BUY_12345",
            "symbol": symbol,
            "amount": amount,
            "price": price,
            "status": "placed",
        }

    def place_market_sell(self, symbol: str, amount: float) -> dict:
        """Mock market sell order placement."""
        logger.info(
            "%s: Placing market sell for %.8f %s",
            self.name,
            amount,
            symbol,
        )
        return {
            "order_id": f"{self.name}_SELL_12345",
            "symbol": symbol,
            "amount": amount,
            "status": "placed",
        }

    def get_order_status(self, symbol: str, order_id: str) -> dict:
        """Mock order status checking."""
        logger.debug("%s: Checking order %s", self.name, order_id)

        # Simulate successful fill after slight delay
        time.sleep(0.1)

        if "BUY" in order_id:
            return {
                "order_id": order_id,
                "status": "filled",
                "filled_amount": 0.1,
                "filled_cost": 4000.0,
            }
        elif "SELL" in order_id:
            return {
                "order_id": order_id,
                "status": "filled",
                "filled_amount": 0.1,
                "received_amount": 4050.0,
            }


def example_basic_scanning():
    """
    Example 1: Basic opportunity scanning.
    Continuously scans order books and reports opportunities.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE 1: Basic Opportunity Scanning")
    logger.info("=" * 70)

    # Import here to avoid issues if strategy module not installed
    try:
        from src.strategies.cto_cross_exchange_usdcbtc import (
            CrossExchangeUSDCBTCStrategy,
        )
    except ImportError:
        logger.error("Failed to import strategy. Ensure src/strategies is in PYTHONPATH")
        return

    # Create mock APIs
    mexc_api = MockExchangeAPI("MEXC")
    bingx_api = MockExchangeAPI("BingX")

    # Initialize strategy
    strategy = CrossExchangeUSDCBTCStrategy(
        mexc_api=mexc_api,
        bingx_api=bingx_api,
        usdc_balance=Decimal("10000"),
        min_profit_usdc=Decimal("50"),
        min_profit_percentage=Decimal("0.5"),
        max_btc_per_trade=Decimal("1.0"),
        max_slippage_bps=100,
    )

    logger.info("Strategy initialized")
    logger.info("Scanning for opportunities...")

    # Scan a few times
    for i in range(3):
        logger.info(f"\nScan #{i + 1}:")
        opportunity = strategy.find_opportunities()

        if opportunity:
            logger.info("✓ Opportunity found!")
            logger.info(f"  BTC Amount: {opportunity.btc_amount:.8f}")
            logger.info(f"  Buy Price (MEXC): {opportunity.buy_price:.2f} USDC")
            logger.info(
                f"  Sell Price Avg (BingX): {opportunity.sell_price_avg:.2f} USDC"
            )
            logger.info(f"  Expected Profit: {opportunity.expected_profit:.2f} USDC")
            logger.info(f"  Profit %: {opportunity.profit_percentage:.4f}%")
        else:
            logger.info("✗ No opportunity found (conditions not met)")

        time.sleep(0.5)


def example_trade_execution():
    """
    Example 2: Full trade execution.
    Finds opportunity and executes the complete trade workflow.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE 2: Complete Trade Execution")
    logger.info("=" * 70)

    try:
        from src.strategies.cto_cross_exchange_usdcbtc import (
            CrossExchangeUSDCBTCStrategy,
        )
    except ImportError:
        logger.error("Failed to import strategy")
        return

    mexc_api = MockExchangeAPI("MEXC")
    bingx_api = MockExchangeAPI("BingX")

    strategy = CrossExchangeUSDCBTCStrategy(
        mexc_api=mexc_api,
        bingx_api=bingx_api,
        usdc_balance=Decimal("10000"),
        min_profit_usdc=Decimal("50"),
        min_profit_percentage=Decimal("0.5"),
    )

    logger.info("Searching for opportunity...")
    opportunity = strategy.find_opportunities()

    if not opportunity:
        logger.warning("No opportunity found. Exiting.")
        return

    logger.info("✓ Opportunity found, executing trade...")

    result = strategy.execute_trade(opportunity)

    logger.info("\n" + "=" * 70)
    logger.info("EXECUTION RESULT:")
    logger.info("=" * 70)
    logger.info(f"Success: {result.success}")
    logger.info(f"Buy Order ID: {result.buy_order_id}")
    logger.info(f"Sell Order ID: {result.sell_order_id}")
    logger.info(f"BTC Bought: {result.btc_bought:.8f}")
    logger.info(f"USDC Paid: {result.usdc_paid:.2f}")
    logger.info(f"BTC Sold: {result.btc_sold:.8f}")
    logger.info(f"USDC Received: {result.usdc_received:.2f}")
    logger.info(f"Actual Profit: {result.actual_profit:.2f} USDC")
    logger.info(f"Profit %: {result.actual_profit_percentage:.4f}%")

    if result.errors:
        logger.error("Errors encountered:")
        for error in result.errors:
            logger.error(f"  - {error}")


def example_status_monitoring():
    """
    Example 3: Strategy status monitoring.
    Demonstrates how to retrieve and report strategy status.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE 3: Strategy Status Monitoring")
    logger.info("=" * 70)

    try:
        from src.strategies.cto_cross_exchange_usdcbtc import (
            CrossExchangeUSDCBTCStrategy,
        )
    except ImportError:
        logger.error("Failed to import strategy")
        return

    mexc_api = MockExchangeAPI("MEXC")
    bingx_api = MockExchangeAPI("BingX")

    strategy = CrossExchangeUSDCBTCStrategy(
        mexc_api=mexc_api,
        bingx_api=bingx_api,
        usdc_balance=Decimal("10000"),
        min_profit_usdc=Decimal("50"),
        min_profit_percentage=Decimal("1.0"),
    )

    # Get initial status
    status = strategy.get_strategy_status()
    logger.info("\nInitial Status:")
    logger.info(json.dumps(status, indent=2, default=str))

    # Run an opportunity scan
    opportunity = strategy.find_opportunities()

    # Get updated status
    status = strategy.get_strategy_status()
    logger.info("\nStatus After Opportunity Scan:")
    logger.info(json.dumps(status, indent=2, default=str))

    # Execute trade
    if opportunity:
        result = strategy.execute_trade(opportunity)

    # Get final status
    status = strategy.get_strategy_status()
    logger.info("\nFinal Status:")
    logger.info(json.dumps(status, indent=2, default=str))


def example_error_handling():
    """
    Example 4: Error handling scenarios.
    Demonstrates how strategy handles various error conditions.
    """
    logger.info("=" * 70)
    logger.info("EXAMPLE 4: Error Handling")
    logger.info("=" * 70)

    try:
        from src.strategies.cto_cross_exchange_usdcbtc import (
            CrossExchangeUSDCBTCStrategy,
        )
    except ImportError:
        logger.error("Failed to import strategy")
        return

    mexc_api = MockExchangeAPI("MEXC")
    bingx_api = MockExchangeAPI("BingX")

    # Scenario 1: Insufficient balance
    logger.info("\nScenario 1: Insufficient USDC Balance")
    strategy = CrossExchangeUSDCBTCStrategy(
        mexc_api=mexc_api,
        bingx_api=bingx_api,
        usdc_balance=Decimal("100"),  # Too low
        min_profit_usdc=Decimal("50"),
    )

    opportunity = strategy.find_opportunities()
    logger.info(f"Found opportunity: {opportunity is not None}")

    # Scenario 2: Insufficient profit threshold
    logger.info("\nScenario 2: Minimum Profit Threshold Not Met")
    strategy = CrossExchangeUSDCBTCStrategy(
        mexc_api=mexc_api,
        bingx_api=bingx_api,
        usdc_balance=Decimal("10000"),
        min_profit_usdc=Decimal("10000"),  # Very high threshold
        min_profit_percentage=Decimal("10.0"),  # 10% minimum
    )

    opportunity = strategy.find_opportunities()
    logger.info(f"Found opportunity: {opportunity is not None}")

    # Scenario 3: Exchange API failure
    logger.info("\nScenario 3: Exchange API Failure")

    class FailingExchangeAPI:
        def get_orderbook(self, symbol: str):
            raise Exception("Connection timeout")

    failing_api = FailingExchangeAPI()
    strategy = CrossExchangeUSDCBTCStrategy(
        mexc_api=failing_api,
        bingx_api=bingx_api,
        usdc_balance=Decimal("10000"),
        min_profit_usdc=Decimal("50"),
    )

    opportunity = strategy.find_opportunities()
    logger.info(f"Found opportunity: {opportunity is not None}")
    logger.info("(Strategy handled API failure gracefully)")


def main():
    """Run all examples."""
    logger.info("\n")
    logger.info("╔" + "═" * 68 + "╗")
    logger.info("║" + " " * 68 + "║")
    logger.info("║" + "CrossExchangeUSDCBTCStrategy - Usage Examples".center(68) + "║")
    logger.info("║" + " " * 68 + "║")
    logger.info("╚" + "═" * 68 + "╝")

    # Run examples
    example_basic_scanning()
    print("\n" * 2)

    example_trade_execution()
    print("\n" * 2)

    example_status_monitoring()
    print("\n" * 2)

    example_error_handling()

    logger.info("\n")
    logger.info("╔" + "═" * 68 + "╗")
    logger.info("║" + "All examples completed".center(68) + "║")
    logger.info("╚" + "═" * 68 + "╝")


if __name__ == "__main__":
    main()
