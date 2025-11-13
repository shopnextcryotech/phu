"""
CTO Cross-Exchange BTC/USDC Arbitrage Strategy
============================================

Strategy: Buy BTC on MEXC (limit order), Sell BTC on BingX (market order)

Algorithm:
1. Continuously monitor order books on both MEXC and BingX exchanges
2. Calculate volume-weighted average price (VWAP) for market sell on BingX
3. Determine breakeven price considering order book depth
4. Verify profitability: MEXC buy price < BingX VWAP sell price
5. Re-verify order books before placing orders to ensure conditions are still favorable
6. Execute limit buy on MEXC followed by market sell on BingX
7. Handle partial fills and log all operations

Key Features:
- Zero fees assumed (as per requirement)
- Order book depth analysis for accurate VWAP calculation
- Pre-execution verification to prevent unprofitable trades
- Comprehensive error handling and logging
- Support for partial order fills

Author: CTO Bot
Date: 2024
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from decimal import Decimal
from enum import Enum


class OrderSide(Enum):
    """Order side enumeration"""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type enumeration"""
    LIMIT = "limit"
    MARKET = "market"


@dataclass
class OrderBookLevel:
    """Represents a single level in the order book"""
    price: Decimal
    amount: Decimal
    
    def __post_init__(self):
        self.price = Decimal(str(self.price))
        self.amount = Decimal(str(self.amount))


@dataclass
class OrderBook:
    """Order book structure with bids and asks"""
    symbol: str
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    timestamp: float


@dataclass
class VWAPResult:
    """Result of VWAP calculation"""
    filled_amount: Decimal
    total_cost: Decimal
    vwap_price: Decimal
    worst_price: Decimal
    levels_used: int


@dataclass
class ArbitrageOpportunity:
    """Represents a detected arbitrage opportunity"""
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: Decimal
    sell_vwap: Decimal
    amount: Decimal
    expected_profit: Decimal
    profit_percentage: Decimal
    timestamp: float


@dataclass
class TradeResult:
    """Result of executed trade"""
    success: bool
    buy_order_id: Optional[str]
    sell_order_id: Optional[str]
    buy_filled: Decimal
    sell_filled: Decimal
    actual_profit: Optional[Decimal]
    error_message: Optional[str]


class CTOCrossExchangeUSDCBTCStrategy:
    """
    Cross-Exchange Arbitrage Strategy for BTC/USDC
    
    Executes arbitrage between MEXC and BingX by:
    1. Buying BTC with USDC on MEXC (limit order)
    2. Selling BTC for USDC on BingX (market order)
    
    The strategy continuously monitors order books and only executes
    when a profitable opportunity is detected with sufficient depth.
    """
    
    def __init__(
        self,
        mexc_client,
        bingx_client,
        symbol: str = "BTC/USDC",
        min_profit_percentage: float = 0.1,
        max_order_amount_btc: float = 0.1,
        order_book_depth: int = 20,
        recheck_interval_seconds: float = 1.0,
        order_timeout_seconds: float = 30.0,
        enable_logging: bool = True
    ):
        """
        Initialize the CTO Cross-Exchange strategy
        
        Args:
            mexc_client: MEXC exchange API client
            bingx_client: BingX exchange API client
            symbol: Trading pair symbol (default: BTC/USDC)
            min_profit_percentage: Minimum profit percentage to execute trade (default: 0.1%)
            max_order_amount_btc: Maximum BTC amount per order (default: 0.1 BTC)
            order_book_depth: Number of order book levels to fetch (default: 20)
            recheck_interval_seconds: Time between order book checks (default: 1.0s)
            order_timeout_seconds: Timeout for order execution (default: 30s)
            enable_logging: Enable detailed logging (default: True)
        """
        self.mexc = mexc_client
        self.bingx = bingx_client
        self.symbol = symbol
        self.min_profit_percentage = Decimal(str(min_profit_percentage))
        self.max_order_amount_btc = Decimal(str(max_order_amount_btc))
        self.order_book_depth = order_book_depth
        self.recheck_interval = recheck_interval_seconds
        self.order_timeout = order_timeout_seconds
        self.is_running = False
        
        self.logger = logging.getLogger(__name__)
        if enable_logging:
            self._setup_logging()
    
    def _setup_logging(self):
        """Configure logging for the strategy"""
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    async def start(self):
        """Start the arbitrage strategy loop"""
        self.is_running = True
        self.logger.info(f"Starting CTO Cross-Exchange strategy for {self.symbol}")
        self.logger.info(f"Min profit: {self.min_profit_percentage}%, Max amount: {self.max_order_amount_btc} BTC")
        
        while self.is_running:
            try:
                await self._strategy_cycle()
            except Exception as e:
                self.logger.error(f"Error in strategy cycle: {e}", exc_info=True)
            
            await asyncio.sleep(self.recheck_interval)
    
    async def stop(self):
        """Stop the arbitrage strategy"""
        self.is_running = False
        self.logger.info("Stopping CTO Cross-Exchange strategy")
    
    async def _strategy_cycle(self):
        """
        Main strategy cycle:
        1. Fetch order books from both exchanges
        2. Analyze arbitrage opportunity
        3. Verify profitability
        4. Execute trade if conditions are met
        """
        try:
            opportunity = await self.find_arbitrage_opportunity()
            
            if opportunity:
                self.logger.info(
                    f"Opportunity detected: Buy at {opportunity.buy_price} USDC, "
                    f"Sell at {opportunity.sell_vwap} USDC (VWAP), "
                    f"Amount: {opportunity.amount} BTC, "
                    f"Expected profit: {opportunity.expected_profit} USDC "
                    f"({opportunity.profit_percentage}%)"
                )
                
                result = await self.execute_arbitrage(opportunity)
                
                if result.success:
                    self.logger.info(
                        f"Trade executed successfully! "
                        f"Buy order: {result.buy_order_id}, Sell order: {result.sell_order_id}, "
                        f"Actual profit: {result.actual_profit} USDC"
                    )
                else:
                    self.logger.warning(
                        f"Trade execution failed: {result.error_message}"
                    )
            else:
                self.logger.debug("No profitable opportunity found")
                
        except Exception as e:
            self.logger.error(f"Error in strategy cycle: {e}", exc_info=True)
    
    async def find_arbitrage_opportunity(self) -> Optional[ArbitrageOpportunity]:
        """
        Analyze order books and find arbitrage opportunity
        
        Returns:
            ArbitrageOpportunity if found, None otherwise
        """
        try:
            mexc_book, bingx_book = await asyncio.gather(
                self._fetch_order_book("MEXC", self.mexc),
                self._fetch_order_book("BingX", self.bingx)
            )
            
            if not mexc_book or not bingx_book:
                self.logger.warning("Failed to fetch order books")
                return None
            
            if not mexc_book.asks or not bingx_book.bids:
                self.logger.warning("Order books are empty")
                return None
            
            best_ask_mexc = mexc_book.asks[0]
            
            available_amount = min(
                self.max_order_amount_btc,
                self._calculate_available_depth(bingx_book.bids)
            )
            
            if available_amount <= 0:
                self.logger.debug("Insufficient liquidity on BingX")
                return None
            
            vwap_result = self._calculate_vwap(
                bingx_book.bids,
                available_amount
            )
            
            buy_price = best_ask_mexc.price
            sell_price = vwap_result.vwap_price
            
            profit = (sell_price - buy_price) * vwap_result.filled_amount
            profit_percentage = (profit / (buy_price * vwap_result.filled_amount)) * Decimal('100')
            
            self.logger.debug(
                f"Analysis: Buy={buy_price}, Sell VWAP={sell_price}, "
                f"Amount={vwap_result.filled_amount}, Profit={profit} ({profit_percentage}%)"
            )
            
            if profit_percentage >= self.min_profit_percentage:
                return ArbitrageOpportunity(
                    symbol=self.symbol,
                    buy_exchange="MEXC",
                    sell_exchange="BingX",
                    buy_price=buy_price,
                    sell_vwap=sell_price,
                    amount=vwap_result.filled_amount,
                    expected_profit=profit,
                    profit_percentage=profit_percentage,
                    timestamp=bingx_book.timestamp
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding arbitrage opportunity: {e}", exc_info=True)
            return None
    
    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> TradeResult:
        """
        Execute the arbitrage trade
        
        Steps:
        1. Re-verify order books to ensure conditions are still favorable
        2. Place limit buy order on MEXC
        3. Wait for order fill (with timeout)
        4. Place market sell order on BingX
        5. Monitor execution and calculate actual profit
        
        Args:
            opportunity: The arbitrage opportunity to execute
            
        Returns:
            TradeResult with execution details
        """
        try:
            if not await self._reverify_opportunity(opportunity):
                return TradeResult(
                    success=False,
                    buy_order_id=None,
                    sell_order_id=None,
                    buy_filled=Decimal('0'),
                    sell_filled=Decimal('0'),
                    actual_profit=None,
                    error_message="Opportunity no longer valid after re-verification"
                )
            
            self.logger.info("Placing buy order on MEXC...")
            buy_order_id = await self._place_limit_buy(
                exchange=self.mexc,
                symbol=self.symbol,
                price=opportunity.buy_price,
                amount=opportunity.amount
            )
            
            if not buy_order_id:
                return TradeResult(
                    success=False,
                    buy_order_id=None,
                    sell_order_id=None,
                    buy_filled=Decimal('0'),
                    sell_filled=Decimal('0'),
                    actual_profit=None,
                    error_message="Failed to place buy order on MEXC"
                )
            
            self.logger.info(f"Buy order placed: {buy_order_id}, waiting for fill...")
            buy_filled = await self._wait_for_order_fill(
                exchange=self.mexc,
                order_id=buy_order_id,
                timeout=self.order_timeout
            )
            
            if buy_filled <= 0:
                await self._cancel_order(self.mexc, buy_order_id)
                return TradeResult(
                    success=False,
                    buy_order_id=buy_order_id,
                    sell_order_id=None,
                    buy_filled=Decimal('0'),
                    sell_filled=Decimal('0'),
                    actual_profit=None,
                    error_message="Buy order not filled within timeout"
                )
            
            self.logger.info(f"Buy order filled: {buy_filled} BTC, placing sell order on BingX...")
            sell_order_id = await self._place_market_sell(
                exchange=self.bingx,
                symbol=self.symbol,
                amount=buy_filled
            )
            
            if not sell_order_id:
                return TradeResult(
                    success=False,
                    buy_order_id=buy_order_id,
                    sell_order_id=None,
                    buy_filled=buy_filled,
                    sell_filled=Decimal('0'),
                    actual_profit=None,
                    error_message="Failed to place sell order on BingX (BTC stuck on MEXC!)"
                )
            
            self.logger.info(f"Sell order placed: {sell_order_id}, waiting for fill...")
            sell_filled = await self._wait_for_order_fill(
                exchange=self.bingx,
                order_id=sell_order_id,
                timeout=self.order_timeout
            )
            
            actual_profit = None
            if sell_filled > 0:
                sell_info = await self._get_order_info(self.bingx, sell_order_id)
                actual_sell_price = sell_info.get('average_price', opportunity.sell_vwap)
                actual_profit = (Decimal(str(actual_sell_price)) - opportunity.buy_price) * sell_filled
            
            return TradeResult(
                success=True,
                buy_order_id=buy_order_id,
                sell_order_id=sell_order_id,
                buy_filled=buy_filled,
                sell_filled=sell_filled,
                actual_profit=actual_profit,
                error_message=None
            )
            
        except Exception as e:
            self.logger.error(f"Error executing arbitrage: {e}", exc_info=True)
            return TradeResult(
                success=False,
                buy_order_id=None,
                sell_order_id=None,
                buy_filled=Decimal('0'),
                sell_filled=Decimal('0'),
                actual_profit=None,
                error_message=str(e)
            )
    
    async def _reverify_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """
        Re-verify that the arbitrage opportunity is still valid
        
        This is crucial to avoid executing trades when market conditions have changed
        
        Args:
            opportunity: The opportunity to verify
            
        Returns:
            True if opportunity is still valid, False otherwise
        """
        try:
            self.logger.info("Re-verifying order books before execution...")
            
            current_opportunity = await self.find_arbitrage_opportunity()
            
            if not current_opportunity:
                self.logger.warning("Opportunity disappeared during re-verification")
                return False
            
            price_tolerance = Decimal('0.001')
            
            buy_price_diff = abs(current_opportunity.buy_price - opportunity.buy_price)
            sell_price_diff = abs(current_opportunity.sell_vwap - opportunity.sell_vwap)
            
            if buy_price_diff > price_tolerance or sell_price_diff > price_tolerance:
                self.logger.warning(
                    f"Prices changed significantly during re-verification: "
                    f"Buy {opportunity.buy_price} -> {current_opportunity.buy_price}, "
                    f"Sell {opportunity.sell_vwap} -> {current_opportunity.sell_vwap}"
                )
                return False
            
            if current_opportunity.profit_percentage < self.min_profit_percentage:
                self.logger.warning(
                    f"Profit percentage decreased below threshold: "
                    f"{current_opportunity.profit_percentage}% < {self.min_profit_percentage}%"
                )
                return False
            
            self.logger.info("Re-verification successful, opportunity is still valid")
            return True
            
        except Exception as e:
            self.logger.error(f"Error during re-verification: {e}", exc_info=True)
            return False
    
    def _calculate_vwap(self, levels: List[OrderBookLevel], target_amount: Decimal) -> VWAPResult:
        """
        Calculate Volume-Weighted Average Price (VWAP) for market order
        
        This simulates executing a market order through multiple price levels
        to determine the actual average execution price.
        
        Args:
            levels: Order book levels (bids for sell, asks for buy)
            target_amount: Target amount to fill
            
        Returns:
            VWAPResult with filled amount, cost, and VWAP price
        """
        filled = Decimal('0')
        total_cost = Decimal('0')
        worst_price = Decimal('0')
        levels_used = 0
        
        for level in levels:
            if filled >= target_amount:
                break
            
            remaining = target_amount - filled
            take_amount = min(level.amount, remaining)
            
            filled += take_amount
            total_cost += take_amount * level.price
            worst_price = level.price
            levels_used += 1
        
        if filled == 0:
            raise ValueError("No liquidity available in order book")
        
        vwap = total_cost / filled
        
        return VWAPResult(
            filled_amount=filled,
            total_cost=total_cost,
            vwap_price=vwap,
            worst_price=worst_price,
            levels_used=levels_used
        )
    
    def _calculate_available_depth(self, levels: List[OrderBookLevel]) -> Decimal:
        """
        Calculate total available depth in order book
        
        Args:
            levels: Order book levels
            
        Returns:
            Total available amount
        """
        return sum(level.amount for level in levels)
    
    async def _fetch_order_book(self, exchange_name: str, client) -> Optional[OrderBook]:
        """
        Fetch order book from exchange
        
        Args:
            exchange_name: Name of the exchange (for logging)
            client: Exchange API client
            
        Returns:
            OrderBook or None if fetch fails
        """
        try:
            book_data = await client.fetch_order_book(
                symbol=self.symbol,
                limit=self.order_book_depth
            )
            
            bids = [
                OrderBookLevel(price=bid[0], amount=bid[1])
                for bid in book_data.get('bids', [])
            ]
            asks = [
                OrderBookLevel(price=ask[0], amount=ask[1])
                for ask in book_data.get('asks', [])
            ]
            
            return OrderBook(
                symbol=self.symbol,
                bids=bids,
                asks=asks,
                timestamp=book_data.get('timestamp', asyncio.get_event_loop().time())
            )
            
        except Exception as e:
            self.logger.error(f"Error fetching order book from {exchange_name}: {e}")
            return None
    
    async def _place_limit_buy(
        self,
        exchange,
        symbol: str,
        price: Decimal,
        amount: Decimal
    ) -> Optional[str]:
        """
        Place limit buy order
        
        Args:
            exchange: Exchange client
            symbol: Trading symbol
            price: Limit price
            amount: Order amount
            
        Returns:
            Order ID or None if placement fails
        """
        try:
            order = await exchange.create_limit_buy_order(
                symbol=symbol,
                amount=float(amount),
                price=float(price)
            )
            return order.get('id')
        except Exception as e:
            self.logger.error(f"Error placing limit buy order: {e}", exc_info=True)
            return None
    
    async def _place_market_sell(
        self,
        exchange,
        symbol: str,
        amount: Decimal
    ) -> Optional[str]:
        """
        Place market sell order
        
        Args:
            exchange: Exchange client
            symbol: Trading symbol
            amount: Order amount
            
        Returns:
            Order ID or None if placement fails
        """
        try:
            order = await exchange.create_market_sell_order(
                symbol=symbol,
                amount=float(amount)
            )
            return order.get('id')
        except Exception as e:
            self.logger.error(f"Error placing market sell order: {e}", exc_info=True)
            return None
    
    async def _wait_for_order_fill(
        self,
        exchange,
        order_id: str,
        timeout: float
    ) -> Decimal:
        """
        Wait for order to be filled
        
        Args:
            exchange: Exchange client
            order_id: Order ID to monitor
            timeout: Maximum time to wait in seconds
            
        Returns:
            Filled amount (0 if not filled)
        """
        start_time = asyncio.get_event_loop().time()
        poll_interval = 0.5
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                order_info = await self._get_order_info(exchange, order_id)
                
                status = order_info.get('status')
                filled = Decimal(str(order_info.get('filled', 0)))
                
                if status in ['closed', 'filled']:
                    return filled
                elif status in ['canceled', 'rejected', 'expired']:
                    self.logger.warning(f"Order {order_id} ended with status: {status}")
                    return filled
                
                await asyncio.sleep(poll_interval)
                
            except Exception as e:
                self.logger.error(f"Error checking order status: {e}")
                await asyncio.sleep(poll_interval)
        
        self.logger.warning(f"Order {order_id} timed out after {timeout}s")
        return Decimal('0')
    
    async def _get_order_info(self, exchange, order_id: str) -> Dict[str, Any]:
        """
        Get order information from exchange
        
        Args:
            exchange: Exchange client
            order_id: Order ID
            
        Returns:
            Order information dictionary
        """
        try:
            return await exchange.fetch_order(order_id, symbol=self.symbol)
        except Exception as e:
            self.logger.error(f"Error fetching order info: {e}")
            return {}
    
    async def _cancel_order(self, exchange, order_id: str) -> bool:
        """
        Cancel an order
        
        Args:
            exchange: Exchange client
            order_id: Order ID to cancel
            
        Returns:
            True if successful, False otherwise
        """
        try:
            await exchange.cancel_order(order_id, symbol=self.symbol)
            self.logger.info(f"Cancelled order: {order_id}")
            return True
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {e}")
            return False


async def main():
    """
    Example usage of the CTO Cross-Exchange strategy
    """
    from ccxt import mexc, bingx
    
    mexc_client = mexc({
        'apiKey': 'YOUR_MEXC_API_KEY',
        'secret': 'YOUR_MEXC_SECRET',
        'enableRateLimit': True,
    })
    
    bingx_client = bingx({
        'apiKey': 'YOUR_BINGX_API_KEY',
        'secret': 'YOUR_BINGX_SECRET',
        'enableRateLimit': True,
    })
    
    strategy = CTOCrossExchangeUSDCBTCStrategy(
        mexc_client=mexc_client,
        bingx_client=bingx_client,
        symbol="BTC/USDC",
        min_profit_percentage=0.1,
        max_order_amount_btc=0.1,
        order_book_depth=20,
        recheck_interval_seconds=1.0
    )
    
    try:
        await strategy.start()
    except KeyboardInterrupt:
        await strategy.stop()


if __name__ == "__main__":
    asyncio.run(main())
