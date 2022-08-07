import os.path
import time
import datetime
from strategies import rsi_test
import oandapyV20.endpoints.pricing as pricing
import csv


class Strategy2:
    # Strategy found here - https://www.youtube.com/watch?v=wbfXaqjIrJ0

    # Rules:
    #     Long:
    #     - Price needs to be ABOVE SMA 200
    #     - 21, 50 and 200 need to be going up
    #     - RSI must be above 50 going up

    def __init__(self, oanda_api, instrument):
        self.smaa21_len = 21
        self.smaa50_len = 50
        self.smaa200_len = 200

        self.smma200 = []

        self.instrument = instrument
        self.oanda = oanda_api

        self.time_frame = 5 * 60
        self.trading_open = 6    # Operate trading between 06:00 - 11:00
        self.trading_close = 11  # Operate trading between 06:00 - 11:00


        # Trade quantity
        self.risk = 1  # Risk 0.1% of margin available
        self.pip_value = 0.01 if "JPY" in instrument else 0.0001  # 0.01 for Japanese pairs
        self.take_profit_ratio = 1.5

        # Setting up config for print/debug
        self.cfg = {"instrument": self.instrument,
                    "risk": self.risk,
                    "pip_value": self.pip_value}

    def calculate_gbp_value(self):
        base_currency = self.instrument.split("_")[0]
        if "GBP" in self.instrument:
            self.cfg["GBP_Value"] = 1
            return 1
        else:
            new_instrument = "GBP_" + base_currency
            ts_epoch = int(time.time()) - (60*60+120)  # Get last 2 candles. It is an hour behind
            ts = datetime.datetime.fromtimestamp(ts_epoch).strftime('%Y-%m-%dT%H:%M:%SZ')
            try:
                history = self.oanda.get_price_history(ts, new_instrument, granularity="M1")
                gbp_converted = float(history["candles"][-1]["mid"]["c"])
            except:
                new_instrument = base_currency + "_GBP"
                history = self.oanda.get_price_history(ts, new_instrument, granularity="M1")
                last_price = float(history["candles"][-1]["mid"]["c"])
                gbp_converted = float(1/last_price)
            self.cfg["GBP_Value"] = gbp_converted
            return gbp_converted

    def get_candle_history(self):
        ts_epoch = int(time.time()) - (self.time_frame * (2 * self.smaa200_len))
        ts = datetime.datetime.fromtimestamp(ts_epoch).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.cfg["time"] = ts
        return self.oanda.get_price_history(ts, self.instrument, granularity="M5")

    def calculate_ema(self, prices, smoothing):
        """
        returns an n period exponential moving average for
        the time series s

        s is a list ordered from oldest (index 0) to most
        recent (index -1)
        n is an integer

        returns a numeric array of the exponential
        moving average
        """

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
        return ema

    def get_smma_trend(self, prices):
        smma21 = self.calculate_ema(prices, 21)
        smma50 = self.calculate_ema(prices, 50)
        self.smma200 = self.calculate_ema(prices, 200)
        view_window_size = 25
        sublist_size = 50
        smma21_trend = self.get_trend(smma21[-sublist_size:], view_window_size)
        smma50_trend = self.get_trend(smma50[-sublist_size:], view_window_size)
        smma200_trend = self.get_trend(self.smma200[-sublist_size:], view_window_size)
        self.cfg["smma"] = {"smma21": smma21_trend,
                            "smma50": smma50_trend,
                            "smma200": smma200_trend}
        if smma21_trend == "UPTREND" and smma50_trend == "UPTREND" and smma200_trend == "UPTREND":
            return "UPTREND"
        elif  smma21_trend == "DOWNTREND" and smma50_trend == "DOWNTREND" and smma200_trend == "DOWNTREND":
            return "DOWNTREND"
        return False

    def get_trend(self, arr, size):
        if all(i < j for i, j in zip(arr, arr[-size:])):
            return "UPTREND"
        elif all(i > j for i, j in zip(arr, arr[-size:])):
            return "DOWNTREND"
        else:
            return "NO DEFINITIVE TREND"

    def calculate_RSI(self, prices):
        RSI = rsi_test.wilders_rsi(prices, 14)
        return RSI

    def get_rsi_trend(self):
        history_prices = self.get_candle_history()
        prices = []
        for price in history_prices["candles"]:
            prices.append(float(price["mid"]["c"]))
        RSI_PRICES = self.calculate_RSI(prices)
        rsi_trend = self.get_trend(RSI_PRICES, 3)
        if rsi_trend == "UPTREND" and RSI_PRICES[-1] > 50:
            self.cfg["RSI"] = {"RSI": RSI_PRICES[-10:],
                               "TREND": "UPTREND"}
            return "UPTREND"
        elif rsi_trend == "DOWNTREND" and RSI_PRICES[-1] < 50:
            self.cfg["RSI"] = {"RSI": RSI_PRICES[-10:],
                               "TREND": "DOWNTREND"}
            return "DOWNTREND"
        self.cfg["RSI"] = {"RSI": RSI_PRICES[-10:],
                           "TREND": "NO TREND"}
        return False

    def calculate_engulfing_candle(self, history_prices):
        # Checking 2 candles away
        # First candle [-1] is active candle - ignore
        # Second candle [-2] needs to have closed to confirm green/red
        # Third candle [-3] is the candle to check for engulfing status
        history_prices = history_prices["candles"]
        openBarCurrent = float(history_prices[-2]["mid"]["o"][:-1])  # Open/Close should be the same... but they aren't...
        closeBarCurrent = float(history_prices[-2]["mid"]["c"])
        closeBarPrevious = float(history_prices[-3]["mid"]["c"][:-1])  # Open/Close should be the same... but they aren't...
        openBarPrevious = float(history_prices[-3]["mid"]["o"])
        bullishEngulfing = openBarCurrent <= closeBarPrevious and openBarCurrent < openBarPrevious and closeBarCurrent > openBarPrevious
        bearishEngulfing = openBarCurrent >= closeBarPrevious and openBarCurrent > openBarPrevious and closeBarCurrent < openBarPrevious

        # Confirm if second candle [-2] is Green or not
        green_candle = float(history_prices[-2]["mid"]["c"]) >= float(history_prices[-3]["mid"]["c"])
        if bullishEngulfing and green_candle:
            self.cfg["engulfing_candle"] = "BUY"
            return "BUY"
        elif bearishEngulfing and not green_candle:
            self.cfg["engulfing_candle"] = "SELL"
            return "SELL"
        else:
            self.cfg["engulfing_candle"] = "NONE"
            return False

    def determine_entry_point(self, tick):
        history_candle_prices = self.get_candle_history()
        prices = []
        for price in history_candle_prices["candles"]:
            prices.append(float(price["mid"]["c"]))

        engulfing_candle = self.calculate_engulfing_candle(history_candle_prices)
        smma_trend = self.get_smma_trend(prices)
        stop_loss_difference = self.calculate_stop_loss_difference(history_candle_prices)
        risk = int(float(self.oanda.get_account_value()) * float(self.risk / 100))

        order = None
        self.get_rsi_trend()

        if engulfing_candle == "BUY" and self.get_rsi_trend() == "UPTREND" and smma_trend == "UPTREND" and prices[-1] > self.smma200[-1]:
            price = float(tick["asks"][0]["price"])
            stop_loss = price - stop_loss_difference
            take_profit = price - (stop_loss_difference * self.take_profit_ratio)
            gbp_exchange = self.calculate_gbp_value()
            gbp_value = gbp_exchange * price
            pips = (1 / (abs(stop_loss - price)))
            units = int(gbp_value * risk * pips)
            if "JPY" in self.instrument:
                take_profit = "{:.3f}".format(take_profit)
                stop_loss = "{:.3f}".format(stop_loss)
            order = self.oanda.create_order(instrument=self.instrument,
                                            units=units,
                                            takeProfitOnFill=float(take_profit),
                                            stopLossOnFill=float(stop_loss))
            self.cfg["trade"] = {
                "type": "SELL",
                "price": price,
                "risk":risk,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "units": -units
            }
            self.cfg["decision"] = {
                "engulfing_candle": engulfing_candle,
                "smma_trend": smma_trend,
                "current_price": prices[-1],
                "smma_200_price": self.smma200[-1]
            }

        elif engulfing_candle == "SELL" and self.get_rsi_trend() == "DOWNTREND" and smma_trend == "DOWNTREND" and prices[-1] < self.smma200[-1]:
            price = float(tick["bids"][0]["price"])
            stop_loss = price + stop_loss_difference
            take_profit = price - (stop_loss_difference * self.take_profit_ratio)
            gbp_exchange = self.calculate_gbp_value()
            gbp_value = gbp_exchange * price
            pips = (1 / (abs(stop_loss - price)))
            units = int(gbp_value * risk * pips)
            if "JPY" in self.instrument:
                take_profit = "{:.3f}".format(take_profit)
                stop_loss = "{:.3f}".format(stop_loss)
            order = self.oanda.create_order(instrument=self.instrument,
                                            units=-units,
                                            takeProfitOnFill=float(take_profit),
                                            stopLossOnFill=float(stop_loss))
            self.cfg["trade"] = {
                "type": "SELL",
                "price": price,
                "risk":risk,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "units": -units,
                "take_profit_value": risk * self.take_profit_ratio
            }
            self.cfg["decision"]={
                "engulfing_candle":engulfing_candle,
                "smma_trend":smma_trend,
                "current_price": prices[-1],
                "smma_200_price": self.smma200[-1]
            }

        print(self.cfg)
        if order:
            print(order)
            if "orderCancelTransaction" in order:
                print("Order cancelled because {}".format(order["orderCancelTransaction"]["reason"]))
            trading = False
            winningTrade = False  # Will be used to determine winning trade
            while not trading:
                trade_status = self.oanda.get_trade_status(order["orderFillTransaction"]["id"])
                if trade_status:
                    order_id = order["orderFillTransaction"]["id"]
                    print("\r" + "Waiting for order {} to close - Current price {} - P/L {}".format(order_id, trade_status["price"], trade_status["unrealizedPL"]),end="")
                    if trade_status["unrealisedProfit"] > 0:
                        winningTrade = True
                    else:
                        winningTrade = False
                else:
                    print("\nOrder not found.")
                    print("\nSaving trade data")
                    self.save_trade(order_win=winningTrade)
                    print("Resting for 1 min before continuing")
                    time.sleep(60)
                    trading = True

    def save_trade(self, order_win):
        save_file = "trades.csv"
        headers = ["Time", "Instrument", "Price", "Take Profit", "Stop Loss", "Units", "Decision", "P/L"]
        if order_win:
            p_l = self.cfg["trade"]["take_profit_value"]
        else:
            p_l = -self.cfg["trade"]["risk"]

        line = [self.cfg["time"],
                self.cfg["instrument"],
                self.cfg["trade"]["price"],
                self.cfg["trade"]["take_profit"],
                self.cfg["trade"]["stop_loss"],
                self.cfg["trade"]["units"],
                self.cfg["decision"],
                p_l
                ]
        with open(save_file, 'a', encoding='UTF8', newline='') as f:
            writer = csv.writer(f)
            if not os.path.exists(save_file):
                writer.writerow(headers)
            writer.writerow(line)



    def calculate_stop_loss_difference(self, history_candle_prices, rate=2):
        # Gets high and low price of previous candle
        high_price = float(history_candle_prices["candles"][-2]["mid"]["h"])
        low_price = float(history_candle_prices["candles"][-2]["mid"]["l"])
        return float(high_price - low_price) * rate


    def begin_trade(self):
        check_trade = True
        r = pricing.PricingStream(accountID=self.oanda.accountID, params={"instruments": self.instrument})

        try:
            while True:
                for tick in self.oanda.client.request(r):
                    if tick["type"] == "PRICE":
                        now = datetime.datetime.now()
                        hour = str(now.time()).split(":")[0]
                        minute = str(now.time()).split(":")[1]
                        time.sleep(1)
                        if int(hour) >= self.trading_open and int(hour)<=self.trading_close:
                            print("\r" + str(now.time()), self.instrument, end="")
                            if (int(minute) % 5) == 0:
                                if check_trade:
                                    print("\nChecking trade @ ", now.time())
                                    self.cfg = {}  # Reset config
                                    self.determine_entry_point(tick)
                                    check_trade = False
                                else:
                                    check_trade = True
                        else:
                            print("\r" + str(now.time()), " - Next defined trading window is at {:02d}:00".format(self.trading_open), end="")
        except Exception as err:
            print("ERROR: ", err)
