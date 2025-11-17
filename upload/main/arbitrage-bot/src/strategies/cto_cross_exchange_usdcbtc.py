"""
Cross-Exchange BTC/USDC Arbitrage Strategy (MEXC -> BingX)

Algorithm Overview:
1. Monitor order books on MEXC (asks) and BingX (bids)
2. Evaluate profitability: can we buy on MEXC and sell on BingX with profit?
3. Calculate volume-weighted average sell price on BingX considering order book depth
4. Determine trade volume as min(available balance / buy price, available volume on BingX)
5. Pre-check order books and validate profitability before placing buy order on MEXC
6. If profitable: place limit buy order on MEXC, then market sell on BingX
7. Handle partial fills, calculate final P&L, and log results

Key Features:
- Continuous order book monitoring with bid/ask tracking
- Volume-weighted average price calculation for slippage estimation
- Profitability validation before order placement
- Error handling and comprehensive logging
- Support for partial fills and order status tracking
"""

import logging
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime


logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """Represents a single level in order book (price + volume)"""
    price: Decimal
    volume: Decimal


@dataclass
class OrderBook:
    """Represents order book snapshot for a trading pair"""
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    timestamp: datetime
    symbol: str


@dataclass
class TradeOpportunity:
    """Represents a profitable arbitrage opportunity"""
    btc_amount: Decimal
    buy_price: Decimal
    sell_price_avg: Decimal
    usdc_cost: Decimal
    usdc_received: Decimal
    expected_profit: Decimal
    profit_percentage: Decimal
    sell_volume_breakdown: List[Dict[str, Any]]


@dataclass
class ExecutionResult:
    """Result of trade execution"""
    success: bool
    buy_order_id: Optional[str]
    sell_order_id: Optional[str]
    btc_bought: Decimal
    usdc_paid: Decimal
    btc_sold: Decimal
    usdc_received: Decimal
    actual_profit: Decimal
    actual_profit_percentage: Decimal
    errors: List[str]


class CrossExchangeUSDCBTCStrategy:
    """
    BTC/USDC cross-exchange arbitrage between MEXC (buy) and BingX (sell).
    
    Buys BTC on MEXC using limit orders and sells on BingX using market orders.
    Accounts for order book depth and slippage in profitability calculations.
    """

    def __init__(
        self,
        mexc_api,
        bingx_api,
        usdc_balance: Decimal,
        min_profit_usdc: Decimal,
        min_profit_percentage: Optional[Decimal] = None,
        max_btc_per_trade: Optional[Decimal] = None,
        max_slippage_bps: int = 100,
    ):
        """
        Initialize the cross-exchange arbitrage strategy.

        Args:
            mexc_api: MEXC exchange connector (must support get_orderbook, place_limit_buy, etc.)
            bingx_api: BingX exchange connector (must support get_orderbook, place_market_sell, etc.)
            usdc_balance: Available USDC balance (Decimal for precision)
            min_profit_usdc: Minimum profit in USDC to consider trade
            min_profit_percentage: Minimum profit percentage (optional alternative to min_profit_usdc)
            max_btc_per_trade: Maximum BTC to trade in single transaction
            max_slippage_bps: Maximum acceptable slippage in basis points (1 bps = 0.01%)
        """
        self.mexc = mexc_api
        self.bingx = bingx_api
        self.usdc_balance = Decimal(str(usdc_balance))
        self.min_profit_usdc = Decimal(str(min_profit_usdc))
        self.min_profit_percentage = (
            Decimal(str(min_profit_percentage)) if min_profit_percentage else None
        )
        self.max_btc_per_trade = (
            Decimal(str(max_btc_per_trade)) if max_btc_per_trade else None
        )
        self.max_slippage_bps = max_slippage_bps

        self.symbol_mexc = "BTCUSDC"
        self.symbol_bingx = "BTCUSDC"
        self.last_opportunity = None
        self.last_execution = None

        logger.info(
            "CrossExchangeUSDCBTCStrategy initialized with USDC balance: %s, "
            "min_profit: %s, max_slippage: %d bps",
            self.usdc_balance,
            self.min_profit_usdc,
            self.max_slippage_bps,
        )

    def find_opportunities(self) -> Optional[TradeOpportunity]:
        """
        Scan order books on both exchanges and identify profitable opportunities.

        Returns:
            TradeOpportunity if profitable trade exists, None otherwise
        """
        try:
            mexc_orderbook = self._fetch_orderbook(self.mexc, self.symbol_mexc)
            bingx_orderbook = self._fetch_orderbook(self.bingx, self.symbol_bingx)

            if not mexc_orderbook or not bingx_orderbook:
                logger.warning("Failed to fetch order books from one or both exchanges")
                return None

            opportunity = self._evaluate_opportunity(mexc_orderbook, bingx_orderbook)
            if opportunity:
                self.last_opportunity = opportunity
                logger.info(
                    "Profitable opportunity found: Buy %.8f BTC @ %s USDC, "
                    "Sell avg @ %s USDC, Expected profit: %s USDC (%.2f%%)",
                    opportunity.btc_amount,
                    opportunity.buy_price,
                    opportunity.sell_price_avg,
                    opportunity.expected_profit,
                    opportunity.profit_percentage,
                )
            return opportunity

        except Exception as e:
            logger.error("Error finding opportunities: %s", str(e), exc_info=True)
            return None

    def _fetch_orderbook(self, exchange_api, symbol: str) -> Optional[OrderBook]:
        """
        Fetch current order book from exchange.

        Args:
            exchange_api: Exchange API connector
            symbol: Trading pair symbol

        Returns:
            OrderBook snapshot or None if fetch failed
        """
        try:
            raw_data = exchange_api.get_orderbook(symbol)
            if not raw_data:
                logger.warning("Empty order book data from %s for %s", exchange_api, symbol)
                return None

            bids = [
                OrderBookLevel(
                    price=Decimal(str(level[0])), volume=Decimal(str(level[1]))
                )
                for level in raw_data.get("bids", [])
            ]
            asks = [
                OrderBookLevel(
                    price=Decimal(str(level[0])), volume=Decimal(str(level[1]))
                )
                for level in raw_data.get("asks", [])
            ]

            return OrderBook(
                bids=bids,
                asks=asks,
                timestamp=datetime.now(),
                symbol=symbol,
            )
        except Exception as e:
            logger.error(
                "Failed to fetch order book from %s for %s: %s",
                exchange_api,
                symbol,
                str(e),
            )
            return None

    def _evaluate_opportunity(
        self, mexc_ob: OrderBook, bingx_ob: OrderBook
    ) -> Optional[TradeOpportunity]:
        """
        Evaluate if current market conditions present a profitable opportunity.

        Algorithm:
        1. Get best ask from MEXC (buy price)
        2. Aggregate BingX bids to calculate weighted average sell price
        3. Calculate maximum tradeable volume
        4. Validate profitability against minimum thresholds

        Args:
            mexc_ob: MEXC order book (we buy from asks)
            bingx_ob: BingX order book (we sell into bids)

        Returns:
            TradeOpportunity if profitable, None otherwise
        """
        if not mexc_ob.asks or not bingx_ob.bids:
            logger.debug("Empty asks on MEXC or empty bids on BingX")
            return None

        best_buy_price = mexc_ob.asks[0].price
        logger.debug("Best buy price on MEXC: %s USDC", best_buy_price)

        sell_info = self._aggregate_bingx_sells(bingx_ob.bids)
        if not sell_info or sell_info["btc_volume"] == 0:
            logger.debug("Insufficient liquidity on BingX for selling")
            return None

        max_btc_by_balance = self.usdc_balance / best_buy_price
        max_btc_available = min(sell_info["btc_volume"], max_btc_by_balance)

        if self.max_btc_per_trade:
            max_btc_available = min(max_btc_available, self.max_btc_per_trade)

        if max_btc_available <= 0:
            logger.debug(
                "Insufficient funds or liquidity: max_btc_by_balance=%s, "
                "max_btc_available_on_bingx=%s",
                max_btc_by_balance,
                sell_info["btc_volume"],
            )
            return None

        usdc_cost = max_btc_available * best_buy_price
        usdc_received = sell_info["usdc_for_volume"].get(
            max_btc_available, sell_info["total_usdc"]
        )
        expected_profit = usdc_received - usdc_cost

        if usdc_cost > self.usdc_balance:
            logger.debug(
                "Insufficient USDC balance: need %s, have %s",
                usdc_cost,
                self.usdc_balance,
            )
            return None

        profit_pct = (
            (expected_profit / usdc_cost * Decimal(100))
            if usdc_cost > 0
            else Decimal(0)
        )

        meets_min_profit = expected_profit >= self.min_profit_usdc
        meets_min_pct = (
            True
            if self.min_profit_percentage is None
            else profit_pct >= self.min_profit_percentage
        )

        if not (meets_min_profit and meets_min_pct):
            logger.debug(
                "Profit threshold not met: expected_profit=%s USDC (%.2f%%), "
                "min_profit=%s USDC, min_pct=%s%%",
                expected_profit,
                profit_pct,
                self.min_profit_usdc,
                self.min_profit_percentage,
            )
            return None

        avg_sell_price = sell_info["avg_price"]
        slippage_bps = self._calculate_slippage_bps(best_buy_price, avg_sell_price)

        if slippage_bps > self.max_slippage_bps:
            logger.debug(
                "Slippage exceeds maximum: %.1f bps > %d bps",
                slippage_bps,
                self.max_slippage_bps,
            )
            return None

        return TradeOpportunity(
            btc_amount=max_btc_available,
            buy_price=best_buy_price,
            sell_price_avg=avg_sell_price,
            usdc_cost=usdc_cost,
            usdc_received=usdc_received,
            expected_profit=expected_profit,
            profit_percentage=profit_pct,
            sell_volume_breakdown=sell_info["breakdown"],
        )

    def _aggregate_bingx_sells(self, bids: List[OrderBookLevel]) -> Optional[Dict]:
        """
        Aggregate BingX bid levels to calculate weighted average sell price.

        Simulates market selling by consuming bid levels in order (best prices first).
        Tracks the relationship between BTC volume and corresponding USDC received.

        Args:
            bids: List of bid levels sorted by price (descending)

        Returns:
            Dict with aggregated sell info or None if insufficient liquidity
        """
        if not bids:
            return None

        total_btc = Decimal(0)
        total_usdc = Decimal(0)
        breakdown = []
        usdc_for_volume = {}

        for bid in bids:
            price = bid.price
            volume = bid.volume

            if total_btc + volume > 0:
                usdc_for_volume[total_btc + volume] = total_usdc + (volume * price)

            total_btc += volume
            total_usdc += volume * price

            breakdown.append(
                {
                    "price": float(price),
                    "volume": float(volume),
                    "cumulative_btc": float(total_btc),
                    "cumulative_usdc": float(total_usdc),
                }
            )

        avg_price = total_usdc / total_btc if total_btc > 0 else Decimal(0)

        return {
            "btc_volume": total_btc,
            "total_usdc": total_usdc,
            "avg_price": avg_price,
            "breakdown": breakdown,
            "usdc_for_volume": usdc_for_volume,
        }

    def _calculate_slippage_bps(self, buy_price: Decimal, sell_price_avg: Decimal) -> float:
        """
        Calculate implied slippage in basis points.

        Positive slippage = sell_price_avg is worse than buy_price
        Used to validate that arbitrage spread is sufficient.

        Args:
            buy_price: Best bid price on buying exchange
            sell_price_avg: Volume-weighted average sell price

        Returns:
            Slippage in basis points
        """
        if buy_price <= 0:
            return float("inf")

        slippage = ((sell_price_avg - buy_price) / buy_price) * Decimal(10000)
        return float(slippage)

    def execute_trade(self, opportunity: TradeOpportunity) -> ExecutionResult:
        """
        Execute the arbitrage trade: buy on MEXC, sell on BingX.

        Workflow:
        1. Re-validate current market conditions
        2. Place limit buy order on MEXC
        3. Monitor fill status with timeout
        4. Upon fill, place market sell order on BingX
        5. Track results and calculate final P&L

        Args:
            opportunity: TradeOpportunity to execute

        Returns:
            ExecutionResult with detailed trade outcome
        """
        errors = []
        result = ExecutionResult(
            success=False,
            buy_order_id=None,
            sell_order_id=None,
            btc_bought=Decimal(0),
            usdc_paid=Decimal(0),
            btc_sold=Decimal(0),
            usdc_received=Decimal(0),
            actual_profit=Decimal(0),
            actual_profit_percentage=Decimal(0),
            errors=errors,
        )

        try:
            logger.info("Starting trade execution: Buy %.8f BTC", opportunity.btc_amount)

            if not self._pre_execution_validation(opportunity):
                errors.append("Pre-execution validation failed")
                logger.error("Pre-execution validation failed")
                return result

            buy_order = self._place_buy_order(opportunity)
            if not buy_order:
                errors.append("Failed to place buy order on MEXC")
                logger.error("Failed to place buy order on MEXC")
                return result

            result.buy_order_id = buy_order.get("order_id")
            logger.info("Buy order placed on MEXC: %s", result.buy_order_id)

            buy_status = self._monitor_buy_order(result.buy_order_id, timeout_seconds=30)
            if not buy_status or buy_status.get("status") != "filled":
                errors.append(f"Buy order not filled or cancelled: {buy_status}")
                logger.warning("Buy order not fully filled: %s", buy_status)
                return result

            result.btc_bought = Decimal(str(buy_status.get("filled_amount", 0)))
            result.usdc_paid = Decimal(str(buy_status.get("filled_cost", 0)))

            if result.btc_bought <= 0:
                errors.append("Buy order executed but no BTC received")
                logger.error("Buy order executed but no BTC received")
                return result

            logger.info(
                "Buy order filled: %.8f BTC for %.2f USDC",
                result.btc_bought,
                result.usdc_paid,
            )

            sell_order = self._place_sell_order(result.btc_bought)
            if not sell_order:
                errors.append("Failed to place sell order on BingX")
                logger.error("Failed to place sell order on BingX")
                return result

            result.sell_order_id = sell_order.get("order_id")
            logger.info("Sell order placed on BingX: %s", result.sell_order_id)

            sell_status = self._monitor_sell_order(result.sell_order_id, timeout_seconds=30)
            if not sell_status or sell_status.get("status") != "filled":
                errors.append(f"Sell order not filled or cancelled: {sell_status}")
                logger.warning("Sell order not fully filled: %s", sell_status)
                return result

            result.btc_sold = Decimal(str(sell_status.get("filled_amount", 0)))
            result.usdc_received = Decimal(str(sell_status.get("received_amount", 0)))

            result.actual_profit = result.usdc_received - result.usdc_paid
            if result.usdc_paid > 0:
                result.actual_profit_percentage = (
                    result.actual_profit / result.usdc_paid * Decimal(100)
                )

            result.success = True
            logger.info(
                "Trade executed successfully: Profit %.2f USDC (%.2f%%)",
                result.actual_profit,
                result.actual_profit_percentage,
            )

        except Exception as e:
            errors.append(f"Execution error: {str(e)}")
            logger.error("Trade execution error: %s", str(e), exc_info=True)

        self.last_execution = result
        return result

    def _pre_execution_validation(self, opportunity: TradeOpportunity) -> bool:
        """
        Re-check market conditions immediately before execution to ensure trade is still valid.

        Validates:
        - Current prices haven't moved too much
        - Sufficient liquidity still available
        - Sufficient balance available

        Args:
            opportunity: Opportunity to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            logger.debug("Running pre-execution validation...")

            if opportunity.usdc_cost > self.usdc_balance:
                logger.error(
                    "Insufficient balance: need %.2f, have %.2f",
                    opportunity.usdc_cost,
                    self.usdc_balance,
                )
                return False

            mexc_ob = self._fetch_orderbook(self.mexc, self.symbol_mexc)
            if not mexc_ob or not mexc_ob.asks:
                logger.error("Failed to fetch MEXC order book")
                return False

            current_best_price = mexc_ob.asks[0].price
            price_change_pct = (
                abs(current_best_price - opportunity.buy_price)
                / opportunity.buy_price
                * Decimal(100)
            )

            if price_change_pct > Decimal(2):
                logger.warning(
                    "Price moved significantly: %.2f%%. Current: %s, Expected: %s",
                    price_change_pct,
                    current_best_price,
                    opportunity.buy_price,
                )
                return False

            logger.debug("Pre-execution validation passed")
            return True

        except Exception as e:
            logger.error("Pre-execution validation error: %s", str(e))
            return False

    def _place_buy_order(self, opportunity: TradeOpportunity) -> Optional[Dict]:
        """
        Place limit buy order on MEXC.

        Args:
            opportunity: Opportunity with buy parameters

        Returns:
            Order response dict or None if failed
        """
        try:
            logger.info(
                "Placing limit buy order on MEXC: %.8f BTC @ %.2f USDC",
                opportunity.btc_amount,
                opportunity.buy_price,
            )

            order = self.mexc.place_limit_buy(
                symbol=self.symbol_mexc,
                amount=float(opportunity.btc_amount),
                price=float(opportunity.buy_price),
            )

            logger.info("Buy order placed: %s", order)
            return order

        except Exception as e:
            logger.error("Failed to place buy order: %s", str(e), exc_info=True)
            return None

    def _monitor_buy_order(
        self, order_id: str, timeout_seconds: int = 30
    ) -> Optional[Dict]:
        """
        Monitor buy order status until filled or timeout.

        Args:
            order_id: Order ID to monitor
            timeout_seconds: Maximum seconds to wait

        Returns:
            Final order status dict or None if failed
        """
        try:
            logger.debug("Monitoring buy order: %s", order_id)

            status = self.mexc.get_order_status(self.symbol_mexc, order_id)
            logger.debug("Buy order status: %s", status)

            return status

        except Exception as e:
            logger.error("Failed to monitor buy order: %s", str(e), exc_info=True)
            return None

    def _place_sell_order(self, btc_amount: Decimal) -> Optional[Dict]:
        """
        Place market sell order on BingX.

        Args:
            btc_amount: Amount of BTC to sell

        Returns:
            Order response dict or None if failed
        """
        try:
            logger.info(
                "Placing market sell order on BingX: %.8f BTC",
                btc_amount,
            )

            order = self.bingx.place_market_sell(
                symbol=self.symbol_bingx,
                amount=float(btc_amount),
            )

            logger.info("Sell order placed: %s", order)
            return order

        except Exception as e:
            logger.error("Failed to place sell order: %s", str(e), exc_info=True)
            return None

    def _monitor_sell_order(
        self, order_id: str, timeout_seconds: int = 30
    ) -> Optional[Dict]:
        """
        Monitor sell order status until filled or timeout.

        Args:
            order_id: Order ID to monitor
            timeout_seconds: Maximum seconds to wait

        Returns:
            Final order status dict or None if failed
        """
        try:
            logger.debug("Monitoring sell order: %s", order_id)

            status = self.bingx.get_order_status(self.symbol_bingx, order_id)
            logger.debug("Sell order status: %s", status)

            return status

        except Exception as e:
            logger.error("Failed to monitor sell order: %s", str(e), exc_info=True)
            return None

    def get_strategy_status(self) -> Dict[str, Any]:
        """
        Get current strategy status and recent activity.

        Returns:
            Status dictionary with metrics
        """
        return {
            "usdc_balance": float(self.usdc_balance),
            "min_profit_usdc": float(self.min_profit_usdc),
            "min_profit_percentage": (
                float(self.min_profit_percentage)
                if self.min_profit_percentage
                else None
            ),
            "max_btc_per_trade": (
                float(self.max_btc_per_trade) if self.max_btc_per_trade else None
            ),
            "max_slippage_bps": self.max_slippage_bps,
            "last_opportunity": (
                {
                    "btc_amount": float(self.last_opportunity.btc_amount),
                    "buy_price": float(self.last_opportunity.buy_price),
                    "sell_price_avg": float(self.last_opportunity.sell_price_avg),
                    "expected_profit": float(self.last_opportunity.expected_profit),
                    "profit_percentage": float(self.last_opportunity.profit_percentage),
                }
                if self.last_opportunity
                else None
            ),
            "last_execution": (
                {
                    "success": self.last_execution.success,
                    "buy_order_id": self.last_execution.buy_order_id,
                    "sell_order_id": self.last_execution.sell_order_id,
                    "btc_bought": float(self.last_execution.btc_bought),
                    "usdc_paid": float(self.last_execution.usdc_paid),
                    "btc_sold": float(self.last_execution.btc_sold),
                    "usdc_received": float(self.last_execution.usdc_received),
                    "actual_profit": float(self.last_execution.actual_profit),
                    "actual_profit_percentage": float(
                        self.last_execution.actual_profit_percentage
                    ),
                    "errors": self.last_execution.errors,
                }
                if self.last_execution
                else None
            ),
        }
