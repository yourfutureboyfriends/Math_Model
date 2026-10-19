# region imports
from AlgorithmImports import *
# endregion


class SymbolData:
    def __init__(self, algo, symbol):
        self.symbol = symbol
        self.fast = algo.ema(symbol, 50)
        self.slow = algo.ema(symbol, 200)
        self.window = RollingWindow(5)

    def update(self, price):
        self.window.add(price)

    def trending(self):
        return self.fast.is_ready and self.slow.is_ready and self.fast.current.value > self.slow.current.value


class EmaCrossRotation(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2016, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)
        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self._tickers = ["SPY", "QQQ", "TLT", "GLD"]
        self._data = {}
        for t in self._tickers:
            sym = self.add_equity(t, Resolution.DAILY).symbol
            self._data[t] = SymbolData(self, sym)
        self.set_warm_up(200)
        self.schedule.on(self.date_rules.month_start("SPY"), self.time_rules.after_market_open("SPY", 30), self.rebalance)
        self._fills = 0

    def on_data(self, data):
        for t, sd in self._data.items():
            if data.contains_key(t):
                sd.update(data[t].close)

    def rebalance(self):
        if self.is_warming_up:
            return
        winners = [t for t, sd in self._data.items() if sd.trending()]
        for t in self._tickers:
            if t not in winners and self.portfolio[t].invested:
                self.liquidate(t)
        for t in winners:
            self.set_holdings(t, 0.95 / len(winners))
        if hasattr(self, "_fills"):
            _ = self._fills

    def on_order_event(self, order_event):
        if order_event.status == OrderStatus.FILLED:
            self._fills += 1
