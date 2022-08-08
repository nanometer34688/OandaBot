import time
import datetime
import oandapyV20.endpoints.pricing as pricing
from strategies import rsi_test


class Strategy1:
    # https://www.youtube.com/watch?v=zqUC8dtPphI
    def __init__(self, oanda_api, instrument, check_period_ema=2, check_period_rsi=2, smoothing=175, pip=10):
        self.strategy_name = "Strategy 1"
        self.minutes = 5
        self.time_frame = 60 * self.minutes  # 5 Minutes
        self.granularity = "M5"  # 5 Minutes
        self.instrument = instrument
        self.oanda = oanda_api

        # Trade quantity
        self.risk = 0.1  # Risk 0.1% of account
        self.pip = pip
        self.pip_value = 0.01 if "JPY" in instrument else 0.0001  # 0.01 for Japanese pairs
        self.pip_difference = float(self.pip * self.pip_value)

        # EMA details
        self.ema_length = 200
        self.smoothing = smoothing
        self.check_period_ema = check_period_ema

        # RSI details
        self.rsi_length = 14
        self.rsi_ma_length = 14
        self.rsi_middle_band = 50
        self.check_period_rsi = check_period_rsi

        # SAR details - NOT IMPLEMENTED YET

        self.RSI = []
        self.EMA = []
        self.current_EMA = 0

        self.price = 0
        self.prices = []

    def recalculate_price_history(self):
        # History Prices
        ts_epoch = int(time.time()) - (self.time_frame * (self.ema_length))
        ts = datetime.datetime.fromtimestamp(ts_epoch).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.price_history = self.oanda.get_price_history(from_time=ts,
                                                          instrument=self.instrument,
                                                          granularity=self.granularity,
                                                          num_candles=5000)
        self.prices = []
        for price in self.price_history["candles"]:
            self.prices.append(float(price["mid"]["c"]))
        return self.prices

    def print_progress(self):
        print("\r" + "Recalculating EMA and RSI - {} \nCurrent RSI: {} \nCurrent EMA: {} \nCurrent Price: {}".format(self.instrument, self.RSI[-1], self.EMA[-1], self.prices[-1]), end="")

    def get_decision_reason(self, type):
        print("Reasons for the trade")
        print("Trade type", type)
        print("EMA", self.EMA[-2:])
        print("RSI", self.RSI[-2:])
        print("Price", self.prices[-2:])

    def stream_candles(self):
        r = pricing.PricingStream(accountID=self.oanda.accountID, params={"instruments": self.instrument})
        self.recalculate_price_history()
        self.calculate_ema()
        self.calculate_RSI()
        count = 0
        check_trade = True
        while True:
            try:
                for tick in self.oanda.client.request(r):
                    if tick["type"] == "PRICE":
                        count += 1
                        minute = tick["time"].split(":")[1]
                        print("\r" + "Waiting for candle close - {}".format(self.instrument), end="")
                        if (int(minute) % self.minutes) == 0:  # Only run check on newly closed candle
                            if check_trade:
                                self.calculate_ema()
                                self.calculate_RSI()
                                self.recalculate_price_history()
                                self.calculate_trade(tick)
                                check_trade = False
                        else:
                            check_trade = True

            except Exception as err:
                print("ERROR: ", err)


    def calculate_trade(self, tick, trailingStop=False):
        trading = True
        check_trade = self.confirm_trade(float(self.prices[-1]))  # Checks trade on last closing price
        if check_trade:
            self.price = tick["asks"][0]["price"]
            print("RECOMMEND - {}".format(check_trade))
            buy_sell = 1
            if check_trade == "SELL":
                buy_sell = -1
                if "type" in tick:
                    self.price = tick["bids"][0]["price"]
            if trading:
                price_difference = float(self.pip_difference)
                risk = int(float(self.oanda.get_account_value()) * float(self.risk / 100))
                units = int(float(risk / self.pip_difference) * float(self.price))
                if trailingStop:
                    order = self.oanda.create_order_trailing_stop_loss(instrument=self.instrument,
                                                                       units=units * buy_sell,
                                                                       trailingStopLossDistance=price_difference)
                else:
                    take_profit = float(self.price) + (float(price_difference) * buy_sell)
                    stop_loss = float(self.price) - (float(price_difference) * buy_sell)
                    order = self.oanda.create_order(instrument=self.instrument,
                                                    units=units*buy_sell,
                                                    takeProfitOnFill=float(take_profit),
                                                    stopLossOnFill=float(stop_loss))
                print(order)
                self.get_decision_reason(check_trade)
                if "orderCancelTransaction" in order:
                    print("Order cancelled because {}".format(order["orderCancelTransaction"]["reason"]))
                trading = False
                while not trading:
                    trade_status = self.oanda.get_trade_status(order["orderFillTransaction"]["id"])
                    if trade_status:
                        order_id = order["orderFillTransaction"]["id"]
                        if trailingStop:
                            trailing_stop_amount = trade_status["trailingStopLossOrder"]["trailingStopValue"]
                            print(
                                "\r" + "Waiting for order {} to close at trailing stop loss: {} - Current price {} - P/L {}".format(
                                    order_id, trailing_stop_amount, trade_status["price"], trade_status["unrealizedPL"]),
                                end="")
                        else:
                            print("\r" + "Waiting for order {} to close - Current price {} - P/L {}".format(order_id, trade_status["price"],trade_status["unrealizedPL"]),end="")
                    else:
                        print("\nOrder not found.")
                        print("Resting for 1 min before continuing")
                        time.sleep(60)
                        trading = True

    def calculate_back_test_trade(self, prices):
        count = 0
        buffer = 200
        self.prices = prices[:buffer]  # first 200 are backdated
        self.calculate_ema()
        self.calculate_RSI()
        trading = True
        wins = 0
        losses = 0
        for ix, price in enumerate(prices[buffer:]):
            del self.prices[0]
            self.prices.append(price)
            if count % 10:  # Recalculate
                self.calculate_ema()
                self.calculate_RSI()
            count += 1
            check_trade = self.confirm_trade(price)  # Checks trade on last closing price
            if check_trade:
                buy_sell = 1
                if check_trade == "SELL":
                    buy_sell = -1
                if trading:
                    price_difference = (float(self.pip_difference)) * buy_sell
                    target_price = price + price_difference
                    stop_loss = price - price_difference
                    trading = False
                if check_trade == "BUY":
                    if price > target_price:
                        trading = True
                        wins+=1
                    if price < stop_loss:
                        losses+=1
                        trading = True
                else:
                    if price < target_price:
                        trading = True
                        wins += 1
                    if price > stop_loss:
                        losses+=1
                        trading = True
        return wins, losses

    def confirm_trade(self, bid_price):
        if bid_price > self.current_EMA and self.RSI[-1] > self.rsi_middle_band:
            if self.check_price_near_rsi(buy=True) and self.check_price_near_ema(buy=True):
                return "BUY"
            return False
        if bid_price < self.current_EMA and self.RSI[-1] < self.rsi_middle_band:
            if self.check_price_near_rsi(buy=False) and self.check_price_near_ema(buy=False):
                return "SELL"
            return False
        else:
            return False

    # Checking if the last 2 price changes have crossed the EMA line
    def check_price_near_ema(self, buy=True):
        num_prices = self.check_period_ema
        subset_history_prices = self.prices[-num_prices:]
        if buy:
            for x in self.EMA[-num_prices:]:
                for y in subset_history_prices:
                    if x > y:
                        return True
            return False
        else:
            for x in self.EMA[-num_prices:]:
                for y in subset_history_prices:
                    if x < y:
                        return True
            return False

    # Checking if the last 2 price changes have crossed the RSI line
    def check_price_near_rsi(self, buy=True):
        num_prices = self.check_period_rsi
        if buy:
            for x in self.RSI[-num_prices:]:
                if x < self.rsi_middle_band:
                    return True
        else:
            for x in self.RSI[-num_prices:]:
                if x > self.rsi_middle_band:
                    return True
        return False

    def calculate_RSI(self):
        prices = self.prices
        RSI = rsi_test.wilders_rsi(prices, self.rsi_length)
        self.RSI = RSI
        return RSI

    def calculate_ema(self):
        """
        returns an n period exponential moving average for
        the time series s

        s is a list ordered from oldest (index 0) to most
        recent (index -1)
        n is an integer

        returns a numeric array of the exponential
        moving average
        """
        smoothing = self.smoothing
        prices = self.prices

        ema = []
        j = 1

        # get n sma first and calculate the next n period ema
        sma = sum(prices[:smoothing]) / smoothing
        multiplier = 2 / float(1 + smoothing)
        ema.append(sma)

        # EMA(current) = ( (Price(current) - EMA(prev) ) x Multiplier) + EMA(prev)
        ema.append(((prices[smoothing] - sma) * multiplier) + sma)

        # now calculate the rest of the values
        for i in prices[smoothing + 1:]:
            tmp = ((i - ema[j]) * multiplier) + ema[j]
            j = j + 1
            ema.append(tmp)
        self.current_EMA = ema[-1]
        self.EMA = ema
        return self.EMA

    def calculate_SAR(self):
        return 0
