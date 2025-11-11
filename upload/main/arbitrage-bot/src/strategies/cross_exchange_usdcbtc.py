# CrossExchangeUSDCBTCStrategy

"""
Алгоритм:
1. Проверяем стаканы BTC/USDC на MEXC и BingX.
2. Оцениваем, можно ли выгодно купить (MEXC) и продать (BingX) с учётом глубины и slippage.
3. Выбираем объём BTC (min из доступного баланса и sum маркетного объёма на BingX по цене >= текущей).
4. Если условие выполнено (после сумм всех глубин на BingX отдаёт выгодно), на MEXC покупаем по лимиту (или по маркету, если разница минимальна).
5. После исполнения покупки, по маркету на BingX продаём аналогичный объём под расчётный объём стакана.
6. Если остаток не реализован, уведомить про частичное исполнение, рассчитать итоговую прибыль/убыток.
7. Перед запуском сделки пересчитываем стаканы, чтобы условия не ухудшились, перепроверяя объёмы на обеих биржах.

TODO: Реализовать логику подключения к обеим биржам, периодический рескан стаканов и автоматическое выставление ордеров.
"""


class CrossExchangeUSDCBTCStrategy:
    """
    BTC/USDC арбитраж MEXC → BingX с учётом глубины и маркет-продажи на BingX
    """
    def __init__(self, mexc_api, bingx_api, usdc_balance, min_profit_usd):
        self.mexc = mexc_api
        self.bingx = bingx_api
        self.usdc_balance = usdc_balance
        self.min_profit_usd = min_profit_usd

    def get_best_opportunity(self):
        # 1. Получить стакан на MEXC (asks) и на BingX (bids)
        mexc_asks = self.mexc.get_orderbook('BTCUSDC', side='ask')
        bingx_bids = self.bingx.get_orderbook('BTCUSDC', side='bid')
        
        # 2. Оценить максимальный маркет объём с минимальным slippage на BingX
        market_sell_info = self._aggregate_market_sell(bingx_bids, self.usdc_balance)
        if not market_sell_info:
            return None

        # 3. Оценить может ли покупка на MEXC дать профит с учётом результативной цены на BingX
        buy_price = mexc_asks[0]['price']
        total_btc_buy = min(market_sell_info['btc_vol'], self.usdc_balance / buy_price)
        sell_sum = market_sell_info['usdc_received']
        cost = total_btc_buy * buy_price
        profit = sell_sum - cost
        if profit >= self.min_profit_usd:
            return {
                'btc_amt': total_btc_buy,
                'buy_price': buy_price,
                'sell_price_avg': market_sell_info['avg_price'],
                'profit': profit
            }
        return None

    def _aggregate_market_sell(self, bids, usdc_needed):
        btc_sum = 0
        usdc_received = 0
        for bid in bids:
            avail_btc = bid['volume']
            price = bid['price']
            if (usdc_received + avail_btc * price) > usdc_needed:
                # Достигли нужной суммы USDC
                delta_btc = (usdc_needed - usdc_received) / price
                btc_sum += delta_btc
                usdc_received += delta_btc * price
                break
            else:
                btc_sum += avail_btc
                usdc_received += avail_btc * price
        avg_price = usdc_received / btc_sum if btc_sum else 0
        if btc_sum == 0 or usdc_received == 0:
            return None
        return {'btc_vol': btc_sum, 'usdc_received': usdc_received, 'avg_price': avg_price}

    def execute(self, opportunity):
        # 1. Купить BTC на MEXC (лимит/маркет)
        # 2. После подтверждения исполнения — сразу продать по маркету на BingX
        # 3. Логировать результат, частичное исполнение, прибыль
        pass  # TODO: интеграция с API обеих бирж
