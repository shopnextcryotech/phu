# CTO Cross-Exchange BTC/USDC Arbitrage Strategy

## Overview

The CTO Cross-Exchange strategy (`cto_cross_exchange_usdcbtc.py`) implements a sophisticated arbitrage trading system for BTC/USDC between MEXC and BingX exchanges.

## Strategy Description

**Trading Flow:**
1. **Buy** BTC with USDC on MEXC using **limit orders**
2. **Sell** BTC for USDC on BingX using **market orders**
3. **Profit** from the price difference between exchanges

**Key Assumption:**
- Trading fees are set to 0% (as per requirements)
- Funds are already deposited on both exchanges

## Features

### Core Functionality

1. **Order Book Monitoring**
   - Continuously fetches order books from both MEXC and BingX
   - Configurable depth (default: 20 levels)
   - Real-time price analysis

2. **VWAP Calculation**
   - Calculates Volume-Weighted Average Price for market orders
   - Accounts for order book depth when executing large orders
   - Simulates fill across multiple price levels

3. **Profitability Analysis**
   - Calculates expected profit before execution
   - Compares buy price on MEXC with VWAP sell price on BingX
   - Only executes when profit exceeds minimum threshold (default: 0.1%)

4. **Pre-Execution Verification**
   - Re-checks order books immediately before placing orders
   - Prevents execution if market conditions have changed unfavorably
   - Ensures opportunity is still valid

5. **Partial Fill Handling**
   - Monitors order fill status in real-time
   - Handles partial fills gracefully
   - Reports actual filled amounts

6. **Comprehensive Logging**
   - Detailed logs for every operation
   - Error tracking and debugging information
   - Trade execution history

## Architecture

### Data Structures

- **OrderBookLevel**: Represents a single price level in the order book
- **OrderBook**: Contains bids and asks for a trading pair
- **VWAPResult**: Result of VWAP calculation including filled amount and average price
- **ArbitrageOpportunity**: Detected opportunity with profitability metrics
- **TradeResult**: Execution result with order IDs and actual profit

### Main Class: `CTOCrossExchangeUSDCBTCStrategy`

#### Initialization Parameters

```python
strategy = CTOCrossExchangeUSDCBTCStrategy(
    mexc_client=mexc_api,              # MEXC exchange client
    bingx_client=bingx_api,             # BingX exchange client
    symbol="BTC/USDC",                  # Trading pair
    min_profit_percentage=0.1,          # Minimum profit threshold (%)
    max_order_amount_btc=0.1,           # Maximum order size (BTC)
    order_book_depth=20,                # Number of order book levels
    recheck_interval_seconds=1.0,       # Time between checks
    order_timeout_seconds=30.0,         # Order execution timeout
    enable_logging=True                 # Enable detailed logging
)
```

#### Key Methods

1. **`start()`**: Begins the strategy loop
2. **`stop()`**: Gracefully stops the strategy
3. **`find_arbitrage_opportunity()`**: Analyzes order books for opportunities
4. **`execute_arbitrage()`**: Executes the trade
5. **`_calculate_vwap()`**: Calculates volume-weighted average price
6. **`_reverify_opportunity()`**: Re-verifies conditions before execution

## Algorithm Flow

```
┌─────────────────────────────────────┐
│  1. Fetch Order Books               │
│     - MEXC (asks)                   │
│     - BingX (bids)                  │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│  2. Calculate VWAP                  │
│     - Simulate market sell on BingX │
│     - Account for depth             │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│  3. Check Profitability             │
│     - MEXC buy price < BingX VWAP?  │
│     - Profit > min threshold?       │
└──────────────┬──────────────────────┘
               ▼
         ┌─────┴─────┐
         │ Profitable?│
         └─────┬─────┘
               │ YES
               ▼
┌─────────────────────────────────────┐
│  4. Re-verify Order Books           │
│     - Ensure conditions unchanged   │
│     - Prevent stale opportunities   │
└──────────────┬──────────────────────┘
               ▼
         ┌─────┴─────┐
         │ Still Good?│
         └─────┬─────┘
               │ YES
               ▼
┌─────────────────────────────────────┐
│  5. Execute Buy on MEXC             │
│     - Place limit order             │
│     - Wait for fill (with timeout)  │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│  6. Execute Sell on BingX           │
│     - Place market order            │
│     - Monitor execution             │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│  7. Calculate Actual Profit         │
│     - Log trade results             │
│     - Report to user                │
└─────────────────────────────────────┘
```

## Usage Example

```python
import asyncio
from ccxt import mexc, bingx
from strategies.cto_cross_exchange_usdcbtc import CTOCrossExchangeUSDCBTCStrategy

async def run_strategy():
    # Initialize exchange clients
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
    
    # Create strategy instance
    strategy = CTOCrossExchangeUSDCBTCStrategy(
        mexc_client=mexc_client,
        bingx_client=bingx_client,
        symbol="BTC/USDC",
        min_profit_percentage=0.1,      # 0.1% minimum profit
        max_order_amount_btc=0.1,       # Max 0.1 BTC per trade
        order_book_depth=20,            # Fetch 20 levels
        recheck_interval_seconds=1.0    # Check every second
    )
    
    # Start the strategy
    try:
        await strategy.start()
    except KeyboardInterrupt:
        await strategy.stop()
        print("Strategy stopped by user")

if __name__ == "__main__":
    asyncio.run(run_strategy())
```

## Configuration

### Recommended Settings

| Parameter | Default | Recommended Range | Description |
|-----------|---------|-------------------|-------------|
| `min_profit_percentage` | 0.1% | 0.05% - 0.5% | Minimum profit to execute trade |
| `max_order_amount_btc` | 0.1 BTC | 0.01 - 1.0 BTC | Maximum order size |
| `order_book_depth` | 20 | 10 - 50 | Order book levels to fetch |
| `recheck_interval_seconds` | 1.0s | 0.5 - 5.0s | Time between opportunity checks |
| `order_timeout_seconds` | 30.0s | 15 - 60s | Order execution timeout |

### Risk Management

1. **Position Sizing**
   - Start with small amounts (0.01 BTC)
   - Gradually increase as you verify strategy performance
   - Never risk more than you can afford to lose

2. **Monitoring**
   - Watch logs for any errors or warnings
   - Monitor actual vs expected profits
   - Track order fill rates

3. **Emergency Stops**
   - Use Ctrl+C to stop the strategy gracefully
   - Monitor exchange balances regularly
   - Have a plan for stuck positions

## Error Handling

The strategy includes comprehensive error handling:

1. **Network Errors**: Automatic retry with exponential backoff
2. **Order Rejection**: Logged with detailed error messages
3. **Partial Fills**: Tracked and reported
4. **Timeout Handling**: Orders are cancelled if not filled within timeout
5. **Market Condition Changes**: Trades are cancelled if conditions become unfavorable

## Logging

The strategy provides detailed logging at multiple levels:

- **INFO**: Normal operation, opportunities found, trades executed
- **WARNING**: Opportunities lost, partial fills, timeout events
- **ERROR**: Exchange errors, network issues, execution failures
- **DEBUG**: Detailed order book analysis, VWAP calculations

## Performance Considerations

1. **Latency**: 
   - Low latency connection recommended
   - Co-location near exchange servers ideal
   - WebSocket connections preferred over REST

2. **Frequency**:
   - Default 1-second check interval
   - Can be reduced for more aggressive trading
   - Balance between speed and API rate limits

3. **Order Book Depth**:
   - Deeper books provide better VWAP accuracy
   - Trade-off between accuracy and latency
   - 20 levels is a good balance

## Troubleshooting

### Common Issues

1. **"No profitable opportunity found"**
   - Markets are efficient; opportunities are rare
   - Consider reducing `min_profit_percentage`
   - Ensure both exchanges have good liquidity

2. **"Order not filled within timeout"**
   - Increase `order_timeout_seconds`
   - Check if you're placing orders too far from market
   - Verify exchange connectivity

3. **"Opportunity disappeared during re-verification"**
   - Normal in volatile markets
   - Fast execution environment recommended
   - Consider reducing `recheck_interval_seconds`

4. **"Failed to place sell order on BingX (BTC stuck on MEXC!)"**
   - Manual intervention required
   - Place manual sell order on BingX
   - Check BingX API credentials and permissions

## Limitations

1. **Zero Fees Assumption**: Real exchanges have fees that reduce profitability
2. **Slippage**: Large orders may experience slippage on market orders
3. **Latency**: Network latency can cause opportunities to disappear
4. **API Rate Limits**: Frequent API calls may hit rate limits
5. **Market Volatility**: High volatility can change prices quickly

## Future Enhancements

Potential improvements for the strategy:

1. **Fee Integration**: Account for actual exchange fees
2. **Dynamic Position Sizing**: Adjust order size based on market conditions
3. **Multi-Pair Support**: Trade multiple pairs simultaneously
4. **Statistical Arbitrage**: Use historical data for prediction
5. **Risk Limits**: Implement daily loss limits and exposure caps
6. **WebSocket Integration**: Use WebSocket for real-time order book updates
7. **Machine Learning**: Predict opportunity duration and success rate

## License

This strategy is part of the arbitrage bot project. See the main project LICENSE file for details.

## Support

For issues or questions:
1. Check the logs for detailed error messages
2. Review the troubleshooting section
3. Consult the main project documentation
4. Contact the development team

## Disclaimer

**IMPORTANT**: This software is for educational purposes. Trading cryptocurrencies involves substantial risk of loss. Past performance does not guarantee future results. Only trade with funds you can afford to lose. Always test in a paper trading environment before live trading.

---

**Version**: 1.0  
**Last Updated**: November 2024  
**Author**: CTO Bot Development Team
