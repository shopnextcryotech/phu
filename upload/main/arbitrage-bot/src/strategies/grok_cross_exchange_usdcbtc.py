import ccxt

class ArbitrageStrategy:
    def __init__(self, mexc, bingx, symbol, amount):
        self.mexc = mexc
        self.bingx = bingx
        self.symbol = symbol
        self.amount = amount

    def get_average_price(self, exchange, symbol, amount, side):
        """
        Simulate market order fill by consuming order book depth.
        For buy: side='asks' (hit asks), for sell: side='bids' (hit bids).
        Returns average price if depth sufficient, else None.
        """
        try:
            orderbook = exchange.fetch_order_book(symbol)
            levels = orderbook[side]
            total_cost = 0.0
            remaining = amount
            for price, qty in levels:
                if remaining <= 0:
                    break
                take = min(remaining, qty)
                total_cost += take * price
                remaining -= take
            if remaining > 0:
                return None  # Insufficient depth
            return total_cost / amount
        except ccxt.BaseError:
            return None

    def check_opportunity(self):
        """
        Check if arbitrage is profitable (commissions assumed 0).
        Returns True if profitable, else False.
        """
        # Average price to buy on MEXC (hit asks)
        mexc_buy_price = self.get_average_price(self.mexc, self.symbol, self.amount, 'asks')
        if mexc_buy_price is None:
            print("Insufficient depth on MEXC for buy.")
            return False

        # Average price to sell on BingX (hit bids, may require multiple fills implicitly via market order)
        bingx_sell_price = self.get_average_price(self.bingx, self.symbol, self.amount, 'bids')
        if bingx_sell_price is None:
            print("Insufficient depth on BingX for sell.")
            return False

        # Calculate potential profit (assuming no fees, funds on both exchanges)
        profit = (bingx_sell_price - mexc_buy_price) * self.amount
        if profit > 0:  # Can add a threshold for min profit
            print(f"Opportunity found: Buy on MEXC at {mexc_buy_price}, Sell on BingX at {bingx_sell_price}, Profit: {profit}")
            return True
        else:
            print(f"No opportunity: Potential profit {profit}")
            return False