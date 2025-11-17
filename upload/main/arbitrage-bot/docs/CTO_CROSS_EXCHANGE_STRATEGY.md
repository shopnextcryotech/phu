# Cross-Exchange BTC/USDC Arbitrage Strategy (MEXC -> BingX)

## Overview

The `CrossExchangeUSDCBTCStrategy` implements a spatial arbitrage strategy that exploits price differences between MEXC and BingX exchanges for BTC/USDC trading pair. The strategy buys Bitcoin on MEXC using limit orders and sells it on BingX using market orders, capturing the price differential as profit.

**Location:** `src/strategies/cto_cross_exchange_usdcbtc.py`

---

## Algorithm Flow

### Phase 1: Opportunity Identification

```
┌─────────────────────────────────────────────────────────────┐
│                    Opportunity Identification                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │ Fetch Order Books from Exchanges │
         │ MEXC (ask prices)                │
         │ BingX (bid prices)               │
         └──────────────────────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │ Get Best Buy Price on MEXC       │
         │ (lowest ask)                     │
         └──────────────────────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │ Aggregate BingX Bids             │
         │ Calculate Volume-Weighted        │
         │ Average Sell Price               │
         └──────────────────────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │ Calculate Trade Volume           │
         │ min(available_balance,           │
         │     available_liquidity_on_bingx)│
         └──────────────────────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────┐
         │ Validate Profitability           │
         │ profit >= min_profit_usdc AND    │
         │ profit_pct >= min_profit_pct     │
         └──────────────────────────────────┘
                            │
                            ▼
                  ┌─────────────────┐
                  │ Return Opportunity
                  │ or None         │
                  └─────────────────┘
```

### Phase 2: Execution

```
┌──────────────────────────────────────────────────────────┐
│              Trade Execution Workflow                    │
└──────────────────────────────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ Pre-Execution Validation       │
        │ - Recheck balance              │
        │ - Recheck price movement       │
        │ - Verify still profitable      │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ Place Limit Buy Order on MEXC  │
        │ Price: best_ask                │
        │ Amount: calculated_btc         │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ Monitor Buy Order Fill         │
        │ Wait up to 30 seconds          │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ Place Market Sell Order on     │
        │ BingX for filled BTC amount    │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ Monitor Sell Order Fill        │
        │ Calculate Final P&L            │
        └────────────────────────────────┘
```

---

## Core Components

### 1. OrderBookLevel Dataclass
Represents a single price level in the order book:
```python
@dataclass
class OrderBookLevel:
    price: Decimal      # Price level
    volume: Decimal     # Available volume at this price
```

### 2. OrderBook Dataclass
Complete order book snapshot:
```python
@dataclass
class OrderBook:
    bids: List[OrderBookLevel]      # Buyers' orders (highest prices first)
    asks: List[OrderBookLevel]      # Sellers' orders (lowest prices first)
    timestamp: datetime             # When snapshot was taken
    symbol: str                     # Trading pair (e.g., "BTCUSDC")
```

### 3. TradeOpportunity Dataclass
Represents a calculated profitable trade:
```python
@dataclass
class TradeOpportunity:
    btc_amount: Decimal             # BTC volume to trade
    buy_price: Decimal              # Buy price on MEXC
    sell_price_avg: Decimal         # Volume-weighted average sell price on BingX
    usdc_cost: Decimal              # Total USDC to spend
    usdc_received: Decimal          # Expected USDC to receive
    expected_profit: Decimal        # Profit in USDC
    profit_percentage: Decimal      # Profit as percentage
    sell_volume_breakdown: List     # Detailed breakdown of sell levels
```

### 4. ExecutionResult Dataclass
Tracks actual trade execution results:
```python
@dataclass
class ExecutionResult:
    success: bool                   # Whether trade succeeded
    buy_order_id: Optional[str]     # MEXC order ID
    sell_order_id: Optional[str]    # BingX order ID
    btc_bought: Decimal             # Actual BTC purchased
    usdc_paid: Decimal              # Actual USDC spent
    btc_sold: Decimal               # Actual BTC sold
    usdc_received: Decimal          # Actual USDC received
    actual_profit: Decimal          # Realized profit
    actual_profit_percentage: Decimal  # Realized profit %
    errors: List[str]               # Any errors encountered
```

---

## Key Methods

### find_opportunities() -> Optional[TradeOpportunity]
Main entry point for opportunity scanning. Continuously scans both exchanges and returns the first identified profitable opportunity.

**Process:**
1. Fetch current order books from both exchanges
2. Call `_evaluate_opportunity()` to analyze
3. Store result in `self.last_opportunity`
4. Return opportunity or None

**Returns:** `TradeOpportunity` if profitable trade found, else `None`

---

### _evaluate_opportunity(mexc_ob, bingx_ob) -> Optional[TradeOpportunity]
Analyzes current market conditions and determines if a profitable trade exists.

**Algorithm:**
```
1. Get best ask price on MEXC (lowest price sellers will accept)
2. Aggregate BingX bids to create a cumulative liquidity curve
3. Calculate maximum tradeable volume:
   - Limited by USDC balance: balance / best_ask_price
   - Limited by BingX liquidity: total volume in order book
   - Limited by max_btc_per_trade config parameter
4. For this volume:
   - Calculate total USDC cost: volume * best_ask_price
   - Lookup total USDC received from aggregated bids
   - Calculate profit: received - cost
5. Validate against profitability thresholds:
   - profit >= min_profit_usdc
   - profit_percentage >= min_profit_percentage (if set)
6. Calculate implied slippage in basis points
7. Reject if slippage exceeds max_slippage_bps
```

**Returns:** `TradeOpportunity` if all criteria met, else `None`

---

### _aggregate_bingx_sells(bids) -> Optional[Dict]
Core calculation for volume-weighted average sell price on BingX.

**Purpose:** When we place a market sell order, we'll consume bid levels from best (highest price) to worst (lowest price). This method simulates that process to calculate:
- How much USDC we'd receive for different BTC volumes
- The volume-weighted average price

**Algorithm:**
```
total_btc = 0
total_usdc = 0
usdc_for_volume = {}  # Maps BTC volume -> USDC received

For each bid level (sorted best price first):
    total_btc += level.volume
    total_usdc += level.volume * level.price
    usdc_for_volume[total_btc] = total_usdc

avg_price = total_usdc / total_btc
```

**Example:**
```
BingX Bids:
  Price 40,100 | Volume 0.5 BTC
  Price 40,000 | Volume 1.0 BTC
  Price 39,900 | Volume 0.5 BTC

Aggregation:
  At 0.5 BTC:   20,050 USDC  (avg: 40,100)
  At 1.5 BTC:   60,050 USDC  (avg: 40,033)
  At 2.0 BTC:   79,950 USDC  (avg: 39,975)
```

---

### _calculate_slippage_bps(buy_price, sell_price_avg) -> float
Calculates implied slippage between buy and sell prices.

**Formula:**
```
slippage_bps = ((sell_price_avg - buy_price) / buy_price) * 10,000
```

- **Negative slippage:** sell price is lower than buy price (loss)
- **Positive slippage:** sell price is higher than buy price (loss due to spread)
- **Zero slippage:** Perfect arbitrage (rare)

**Purpose:** Validates that the calculated volumes and prices actually represent profit opportunity.

---

### _pre_execution_validation(opportunity) -> bool
Final validation before placing orders to ensure market conditions haven't changed.

**Checks:**
1. **Balance Validation:** Confirm we still have sufficient USDC
2. **Price Movement:** Check if MEXC best ask hasn't moved more than 2%
3. **Market Data:** Recheck MEXC order book can be fetched
4. **Early Exit:** Cancel if conditions have degraded

**Purpose:** Prevents executing outdated opportunities due to market volatility.

---

### execute_trade(opportunity) -> ExecutionResult
Executes the complete arbitrage trade.

**Workflow:**
```
1. Pre-execution validation
   └─> Return failed result if invalid

2. Place limit buy on MEXC
   └─> Record order_id
   └─> Return failed result if failed

3. Monitor buy order (up to 30s)
   └─> Track filled amount and cost
   └─> Return failed result if not filled

4. Place market sell on BingX
   └─> Use filled BTC amount
   └─> Record order_id
   └─> Return failed result if failed

5. Monitor sell order (up to 30s)
   └─> Track filled amount and proceeds
   └─> Calculate actual profit

6. Return ExecutionResult with full details
```

**Error Handling:**
- All API calls wrapped in try-catch
- Partial fills are detected and reported
- All errors logged with context

---

## Configuration Parameters

### Required
- **mexc_api:** Exchange API connector for MEXC
- **bingx_api:** Exchange API connector for BingX
- **usdc_balance:** Available USDC funds (Decimal for precision)
- **min_profit_usdc:** Minimum profit in USDC to consider trade

### Optional
- **min_profit_percentage:** Minimum profit as percentage (overrides USD minimum if higher)
- **max_btc_per_trade:** Cap on single trade size (protects against liquidity risks)
- **max_slippage_bps:** Maximum slippage in basis points (default: 100 bps)

### Example Initialization
```python
strategy = CrossExchangeUSDCBTCStrategy(
    mexc_api=mexc_connector,
    bingx_api=bingx_connector,
    usdc_balance=Decimal("10000"),
    min_profit_usdc=Decimal("50"),
    min_profit_percentage=Decimal("0.5"),    # 0.5%
    max_btc_per_trade=Decimal("1.0"),
    max_slippage_bps=100,
)
```

---

## Usage Example

### Basic Opportunity Scanning
```python
# Continuous scanning loop
while True:
    opportunity = strategy.find_opportunities()
    
    if opportunity:
        logger.info(f"Found opportunity: {opportunity.expected_profit} USDC profit")
        
        # Execute the trade
        result = strategy.execute_trade(opportunity)
        
        if result.success:
            logger.info(f"Trade succeeded: {result.actual_profit} USDC profit")
        else:
            logger.error(f"Trade failed: {result.errors}")
    
    time.sleep(1)  # Rescan every second
```

### Status Monitoring
```python
# Get current strategy status
status = strategy.get_strategy_status()

print(f"USDC Balance: ${status['usdc_balance']}")
print(f"Last Opportunity: {status['last_opportunity']}")
print(f"Last Execution: {status['last_execution']}")
```

---

## Error Handling & Logging

### Logging Levels Used
- **DEBUG:** Order book data, aggregation details, validation steps
- **INFO:** Opportunities found, orders placed, trades executed
- **WARNING:** Prices moved too much, partial fills, order not filled
- **ERROR:** API failures, execution failures, balance validation failures

### Exception Handling Strategy
1. **Order Book Fetching:** Logs warning and returns None
2. **Opportunity Evaluation:** Logs debug and returns None
3. **Pre-Execution Validation:** Logs error and returns failed result
4. **Order Placement:** Logs error, records in result.errors
5. **Order Monitoring:** Logs warning, attempts recovery

---

## Risk Considerations

### 1. Market Volatility
- Prices can change between opportunity identification and execution
- Mitigation: Pre-execution validation with 2% price move threshold

### 2. Liquidity Risk
- Insufficient BingX liquidity could require market orders across multiple levels
- Mitigation: Algorithm aggregates full order book depth before committing

### 3. Execution Risk
- Buy order might not fill on MEXC
- Sell order might not fill on BingX
- Mitigation: Order monitoring with timeout, partial fill detection

### 4. Slippage Risk
- Market orders on BingX consume liquidity at varying prices
- Mitigation: Volume-weighted average price calculation accounts for this

### 5. Balance Risk
- Insufficient USDC to complete buy order
- Mitigation: Pre-validation checks balance before order placement

---

## Performance Characteristics

### Time Complexity
- **find_opportunities():** O(n) where n = total order book depth
- **_aggregate_bingx_sells():** O(n) where n = number of bid levels
- **_evaluate_opportunity():** O(n) dominated by aggregation
- **execute_trade():** O(1) + I/O waits for order fills

### Space Complexity
- **Order Book Storage:** O(n) where n = order book depth
- **Aggregation Results:** O(n) for complete breakdown

### Typical Execution Time
- **Opportunity Identification:** ~100-500ms (network dependent)
- **Pre-Execution Validation:** ~100-300ms
- **Order Placement:** ~50-200ms per exchange
- **Order Monitoring:** ~30 seconds timeout per order
- **Total Trade Time:** ~1-2 minutes including monitoring

---

## Testing

Comprehensive unit tests included in `tests/unit/test_cto_cross_exchange_usdcbtc.py`:

### Test Coverage
- Order book parsing and validation
- Opportunity identification with various market conditions
- Volume-weighted average price calculations
- Profitability validation
- Slippage calculations
- Pre-execution validation
- Complete trade execution workflow
- Error handling and recovery

### Running Tests
```bash
cd /path/to/arbitrage-bot
python3 -m pytest tests/unit/test_cto_cross_exchange_usdcbtc.py -v
```

---

## Dependencies

### External (Python Standard Library)
- `logging` - For comprehensive logging
- `typing` - Type hints for IDE support
- `dataclasses` - Data structure definitions
- `decimal` - Precise decimal arithmetic (critical for financial calculations)
- `datetime` - Timestamp tracking

### Internal (Project Modules)
- Exchange connectors (mexc_api, bingx_api) must implement:
  - `get_orderbook(symbol)` -> dict with 'bids' and 'asks'
  - `place_limit_buy(symbol, amount, price)` -> order dict
  - `place_market_sell(symbol, amount)` -> order dict
  - `get_order_status(symbol, order_id)` -> status dict

---

## Future Enhancements

1. **Async Order Monitoring:** Use asyncio for concurrent order monitoring
2. **Dynamic Slippage Adjustment:** Learn slippage patterns from historical fills
3. **Multi-Level Spreads:** Consider different fee structures at different VIP levels
4. **Order Book Snapshots:** Keep historical order books for analysis
5. **Partial Fill Recovery:** Automatically retry remaining fill if partial
6. **Real-Time Rebalancing:** Adjust position if market moves while trading
7. **Performance Metrics:** Track hit rate, average profit per trade, max drawdown

---

## References

- Spatial Arbitrage: https://en.wikipedia.org/wiki/Arbitrage#Spatial_arbitrage
- Order Book Dynamics: https://en.wikipedia.org/wiki/Order_book
- Volume-Weighted Average Price: https://en.wikipedia.org/wiki/Volume-weighted_average_price
