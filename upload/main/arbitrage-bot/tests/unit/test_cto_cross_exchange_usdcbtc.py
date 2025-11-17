"""
Unit tests for the CrossExchangeUSDCBTCStrategy class.

Tests cover:
- Order book fetching and parsing
- Opportunity identification and profitability calculation
- Volume-weighted average price aggregation
- Slippage calculations
- Pre-execution validation
- Trade execution workflow
"""

import unittest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch, call

from src.strategies.cto_cross_exchange_usdcbtc import (
    CrossExchangeUSDCBTCStrategy,
    OrderBook,
    OrderBookLevel,
    TradeOpportunity,
)


class TestCrossExchangeUSDCBTCStrategy(unittest.TestCase):
    """Test cases for cross-exchange arbitrage strategy."""

    def setUp(self):
        """Set up test fixtures."""
        self.mexc_api = Mock()
        self.bingx_api = Mock()
        
        self.strategy = CrossExchangeUSDCBTCStrategy(
            mexc_api=self.mexc_api,
            bingx_api=self.bingx_api,
            usdc_balance=Decimal("10000"),
            min_profit_usdc=Decimal("50"),
            min_profit_percentage=Decimal("0.5"),
            max_btc_per_trade=Decimal("1.0"),
            max_slippage_bps=100,
        )

    def _create_orderbook(self, symbol, bids, asks):
        """Helper to create OrderBook objects."""
        bid_levels = [
            OrderBookLevel(price=Decimal(str(b[0])), volume=Decimal(str(b[1])))
            for b in bids
        ]
        ask_levels = [
            OrderBookLevel(price=Decimal(str(a[0])), volume=Decimal(str(a[1])))
            for a in asks
        ]
        return OrderBook(
            bids=bid_levels,
            asks=ask_levels,
            timestamp=datetime.now(),
            symbol=symbol,
        )

    def test_initialization(self):
        """Test strategy initialization with correct parameters."""
        self.assertEqual(self.strategy.usdc_balance, Decimal("10000"))
        self.assertEqual(self.strategy.min_profit_usdc, Decimal("50"))
        self.assertEqual(self.strategy.min_profit_percentage, Decimal("0.5"))
        self.assertEqual(self.strategy.max_btc_per_trade, Decimal("1.0"))
        self.assertEqual(self.strategy.max_slippage_bps, 100)

    def test_fetch_orderbook_success(self):
        """Test successful order book fetching and parsing."""
        raw_orderbook = {
            "bids": [[40000, 0.5], [39900, 1.0]],
            "asks": [[40100, 0.5], [40200, 1.0]],
        }
        self.mexc_api.get_orderbook.return_value = raw_orderbook

        ob = self.strategy._fetch_orderbook(self.mexc_api, "BTCUSDC")

        self.assertIsNotNone(ob)
        self.assertEqual(len(ob.bids), 2)
        self.assertEqual(len(ob.asks), 2)
        self.assertEqual(ob.bids[0].price, Decimal("40000"))
        self.assertEqual(ob.bids[0].volume, Decimal("0.5"))
        self.assertEqual(ob.asks[0].price, Decimal("40100"))

    def test_fetch_orderbook_failure(self):
        """Test order book fetching failure handling."""
        self.mexc_api.get_orderbook.side_effect = Exception("Connection error")

        ob = self.strategy._fetch_orderbook(self.mexc_api, "BTCUSDC")

        self.assertIsNone(ob)

    def test_aggregate_bingx_sells_basic(self):
        """Test aggregation of BingX bid levels for market sell."""
        bids = [
            OrderBookLevel(price=Decimal("40000"), volume=Decimal("0.5")),
            OrderBookLevel(price=Decimal("39900"), volume=Decimal("1.0")),
            OrderBookLevel(price=Decimal("39800"), volume=Decimal("1.5")),
        ]

        result = self.strategy._aggregate_bingx_sells(bids)

        self.assertIsNotNone(result)
        self.assertEqual(result["btc_volume"], Decimal("3.0"))
        self.assertEqual(result["total_usdc"], Decimal("119700"))
        self.assertAlmostEqual(
            float(result["avg_price"]),
            119700 / 3.0,
            places=2
        )

    def test_aggregate_bingx_sells_empty(self):
        """Test aggregation with empty bid list."""
        result = self.strategy._aggregate_bingx_sells([])
        self.assertIsNone(result)

    def test_calculate_slippage_bps_positive(self):
        """Test slippage calculation when sell price is lower than buy price."""
        buy_price = Decimal("40000")
        sell_price = Decimal("39960")

        slippage = self.strategy._calculate_slippage_bps(buy_price, sell_price)

        self.assertEqual(slippage, -10.0)

    def test_calculate_slippage_bps_negative(self):
        """Test slippage calculation when sell price is higher than buy price."""
        buy_price = Decimal("40000")
        sell_price = Decimal("40040")

        slippage = self.strategy._calculate_slippage_bps(buy_price, sell_price)

        self.assertEqual(slippage, 10.0)

    def test_evaluate_opportunity_profitable(self):
        """Test identification of profitable opportunity."""
        mexc_ob = self._create_orderbook(
            "BTCUSDC",
            bids=[[39900, 1.0]],
            asks=[[40000, 1.0], [40100, 1.0]],
        )
        bingx_ob = self._create_orderbook(
            "BTCUSDC",
            bids=[[40100, 0.3], [40000, 0.3], [39900, 0.5]],
            asks=[[40200, 1.0]],
        )

        opportunity = self.strategy._evaluate_opportunity(mexc_ob, bingx_ob)

        self.assertIsNotNone(opportunity)
        self.assertGreater(opportunity.expected_profit, 0)

    def test_evaluate_opportunity_insufficient_profit(self):
        """Test rejection of opportunity with insufficient profit."""
        mexc_ob = self._create_orderbook(
            "BTCUSDC",
            bids=[[39900, 1.0]],
            asks=[[40000, 1.0]],
        )
        bingx_ob = self._create_orderbook(
            "BTCUSDC",
            bids=[[40001, 1.0]],
            asks=[[40100, 1.0]],
        )

        opportunity = self.strategy._evaluate_opportunity(mexc_ob, bingx_ob)

        self.assertIsNone(opportunity)

    def test_evaluate_opportunity_insufficient_liquidity_bingx(self):
        """Test rejection when BingX lacks sufficient liquidity."""
        mexc_ob = self._create_orderbook(
            "BTCUSDC",
            bids=[[39900, 1.0]],
            asks=[[40000, 5.0]],
        )
        bingx_ob = self._create_orderbook(
            "BTCUSDC",
            bids=[[40100, 0.01]],
            asks=[[40200, 1.0]],
        )

        opportunity = self.strategy._evaluate_opportunity(mexc_ob, bingx_ob)

        self.assertIsNone(opportunity)

    def test_find_opportunities_with_profitable_case(self):
        """Test finding opportunities end-to-end."""
        mexc_raw = {
            "bids": [[39900, 1.0]],
            "asks": [[40000, 1.0], [40100, 1.0]],
        }
        bingx_raw = {
            "bids": [[40500, 0.3], [40400, 0.3], [40300, 0.5]],
            "asks": [[40600, 1.0]],
        }

        self.mexc_api.get_orderbook.return_value = mexc_raw
        self.bingx_api.get_orderbook.return_value = bingx_raw

        opportunity = self.strategy.find_opportunities()

        self.assertIsNotNone(opportunity)
        self.assertEqual(self.strategy.last_opportunity, opportunity)

    def test_pre_execution_validation_sufficient_balance(self):
        """Test validation passes with sufficient balance."""
        opportunity = TradeOpportunity(
            btc_amount=Decimal("0.1"),
            buy_price=Decimal("40000"),
            sell_price_avg=Decimal("40100"),
            usdc_cost=Decimal("4000"),
            usdc_received=Decimal("4010"),
            expected_profit=Decimal("10"),
            profit_percentage=Decimal("0.25"),
            sell_volume_breakdown=[],
        )

        self.mexc_api.get_orderbook.return_value = {
            "bids": [[39900, 1.0]],
            "asks": [[40000, 1.0]],
        }

        is_valid = self.strategy._pre_execution_validation(opportunity)

        self.assertTrue(is_valid)

    def test_pre_execution_validation_insufficient_balance(self):
        """Test validation fails with insufficient balance."""
        opportunity = TradeOpportunity(
            btc_amount=Decimal("1.0"),
            buy_price=Decimal("40000"),
            sell_price_avg=Decimal("40100"),
            usdc_cost=Decimal("40000"),
            usdc_received=Decimal("40100"),
            expected_profit=Decimal("100"),
            profit_percentage=Decimal("0.25"),
            sell_volume_breakdown=[],
        )

        is_valid = self.strategy._pre_execution_validation(opportunity)

        self.assertFalse(is_valid)

    def test_pre_execution_validation_price_moved_too_much(self):
        """Test validation fails when price moves significantly."""
        opportunity = TradeOpportunity(
            btc_amount=Decimal("0.1"),
            buy_price=Decimal("40000"),
            sell_price_avg=Decimal("40100"),
            usdc_cost=Decimal("4000"),
            usdc_received=Decimal("4010"),
            expected_profit=Decimal("10"),
            profit_percentage=Decimal("0.25"),
            sell_volume_breakdown=[],
        )

        self.mexc_api.get_orderbook.return_value = {
            "bids": [[39900, 1.0]],
            "asks": [[41000, 1.0]],
        }

        is_valid = self.strategy._pre_execution_validation(opportunity)

        self.assertFalse(is_valid)

    def test_execute_trade_success(self):
        """Test successful trade execution workflow."""
        opportunity = TradeOpportunity(
            btc_amount=Decimal("0.1"),
            buy_price=Decimal("40000"),
            sell_price_avg=Decimal("40100"),
            usdc_cost=Decimal("4000"),
            usdc_received=Decimal("4010"),
            expected_profit=Decimal("10"),
            profit_percentage=Decimal("0.25"),
            sell_volume_breakdown=[],
        )

        self.mexc_api.get_orderbook.return_value = {
            "bids": [[39900, 1.0]],
            "asks": [[40000, 1.0]],
        }
        self.mexc_api.place_limit_buy.return_value = {"order_id": "buy_001"}
        self.mexc_api.get_order_status.return_value = {
            "status": "filled",
            "filled_amount": 0.1,
            "filled_cost": 4000,
        }
        self.bingx_api.place_market_sell.return_value = {"order_id": "sell_001"}
        self.bingx_api.get_order_status.return_value = {
            "status": "filled",
            "filled_amount": 0.1,
            "received_amount": 4010,
        }

        result = self.strategy.execute_trade(opportunity)

        self.assertTrue(result.success)
        self.assertEqual(result.buy_order_id, "buy_001")
        self.assertEqual(result.sell_order_id, "sell_001")
        self.assertEqual(result.btc_bought, Decimal("0.1"))
        self.assertEqual(result.usdc_paid, Decimal("4000"))
        self.assertEqual(result.btc_sold, Decimal("0.1"))
        self.assertEqual(result.usdc_received, Decimal("4010"))
        self.assertEqual(result.actual_profit, Decimal("10"))

    def test_execute_trade_pre_validation_fails(self):
        """Test trade execution fails at pre-validation stage."""
        opportunity = TradeOpportunity(
            btc_amount=Decimal("1.0"),
            buy_price=Decimal("40000"),
            sell_price_avg=Decimal("40100"),
            usdc_cost=Decimal("40000"),
            usdc_received=Decimal("40100"),
            expected_profit=Decimal("100"),
            profit_percentage=Decimal("0.25"),
            sell_volume_breakdown=[],
        )

        result = self.strategy.execute_trade(opportunity)

        self.assertFalse(result.success)
        self.assertIn("Pre-execution validation failed", result.errors)

    def test_execute_trade_buy_order_fails(self):
        """Test trade execution fails when buy order placement fails."""
        opportunity = TradeOpportunity(
            btc_amount=Decimal("0.1"),
            buy_price=Decimal("40000"),
            sell_price_avg=Decimal("40100"),
            usdc_cost=Decimal("4000"),
            usdc_received=Decimal("4010"),
            expected_profit=Decimal("10"),
            profit_percentage=Decimal("0.25"),
            sell_volume_breakdown=[],
        )

        self.mexc_api.get_orderbook.return_value = {
            "bids": [[39900, 1.0]],
            "asks": [[40000, 1.0]],
        }
        self.mexc_api.place_limit_buy.side_effect = Exception("API error")

        result = self.strategy.execute_trade(opportunity)

        self.assertFalse(result.success)
        self.assertIn("Failed to place buy order", result.errors[0])

    def test_get_strategy_status(self):
        """Test strategy status reporting."""
        status = self.strategy.get_strategy_status()

        self.assertEqual(status["usdc_balance"], 10000.0)
        self.assertEqual(status["min_profit_usdc"], 50.0)
        self.assertEqual(status["min_profit_percentage"], 0.5)
        self.assertEqual(status["max_btc_per_trade"], 1.0)
        self.assertEqual(status["max_slippage_bps"], 100)
        self.assertIsNone(status["last_opportunity"])
        self.assertIsNone(status["last_execution"])


class TestOrderBookLevel(unittest.TestCase):
    """Test cases for OrderBookLevel dataclass."""

    def test_orderbook_level_creation(self):
        """Test OrderBookLevel creation with Decimal values."""
        level = OrderBookLevel(
            price=Decimal("40000"),
            volume=Decimal("0.5"),
        )
        self.assertEqual(level.price, Decimal("40000"))
        self.assertEqual(level.volume, Decimal("0.5"))


class TestOrderBook(unittest.TestCase):
    """Test cases for OrderBook dataclass."""

    def test_orderbook_creation(self):
        """Test OrderBook creation with bid/ask levels."""
        bids = [OrderBookLevel(price=Decimal("40000"), volume=Decimal("0.5"))]
        asks = [OrderBookLevel(price=Decimal("40100"), volume=Decimal("0.5"))]

        ob = OrderBook(
            bids=bids,
            asks=asks,
            timestamp=datetime.now(),
            symbol="BTCUSDC",
        )

        self.assertEqual(len(ob.bids), 1)
        self.assertEqual(len(ob.asks), 1)
        self.assertEqual(ob.symbol, "BTCUSDC")


if __name__ == "__main__":
    unittest.main()
