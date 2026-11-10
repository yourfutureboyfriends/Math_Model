# region imports
from AlgorithmImports import *
# endregion


class LargestCapsMonthly(QCAlgorithm):
    """Hold the 20 largest S&P 500 members by market capitalisation, equal weight, rebalanced each month."""

    def initialize(self):
        self.set_start_date(2016, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(1000000)
        self.set_benchmark("SPY")
        self.add_equity("SPY")
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.select)
        self._targets = []
        self._month = -1
        self.schedule.on(self.date_rules.month_start("SPY"), self.time_rules.after_market_open("SPY", 10), self.rebalance)

    def select(self, fundamentals):
        if self.time.month == self._month:
            return self._targets
        self._month = self.time.month
        ranked = sorted([f for f in fundamentals if f.has_fundamental_data and f.market_cap > 0],
                        key=lambda f: f.market_cap, reverse=True)
        self._targets = [f.symbol for f in ranked[:20]]
        return self._targets

    def on_securities_changed(self, changes):
        for security in changes.removed_securities:
            self.liquidate(security.symbol)

    def rebalance(self):
        if not self._targets:
            return
        for symbol in self._targets:
            self.set_holdings(symbol, 0.97 / len(self._targets))
