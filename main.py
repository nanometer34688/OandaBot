import json
import oandapyV20
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.orders as orders
from oandapyV20.contrib.requests import (
    MarketOrderRequest,
    TakeProfitDetails,
    StopLossDetails,
    TrailingStopLossDetails)
import oandapyV20.endpoints.pricing as pricing
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.instruments as instruments
import datetime
from oandapyV20.definitions.orders import TimeInForce

import argparse

from strategies.Strategy1 import Strategy1
from strategies.Strategy2 import Strategy2

import config

class Oanda:
    def __init__(self, access_token, debug=False):
        self.client = oandapyV20.API(access_token=access_token)
        self.accountID = ""
        self.debug = debug

    def choose_account(self):
        r = accounts.AccountList()
        response = self.client.request(r)
        print("{} Account(s) found".format(len(response["accounts"])))
        if len(response["accounts"]) > 1:
            print("More than 1 account found")
            accounts_str = ""
            for i, account in range(response["accounts"]):
                accounts_str += "\n{}: {}".format(i, account["id"] + " - " + account["tags"])#
            while True:
                user_input = input("Which account would you like to use? \n{}".format(accounts_str))
                if user_input.isnumeric():
                    if int(user_input) > 0 and int(user_input) < len(response["accounts"]):
                        self.accountID = response["accounts"][int(user_input)]["id"]
                        print("Using account: {}".format(self.accountID))
        else:
            self.accountID = response["accounts"][0]["id"]
            print("Using account: {}".format(self.accountID))

    def get_open_trades(self):
        r = trades.OpenTrades(accountID=self.accountID)
        rv = self.client.request(r)
        return rv

    def get_all_orders(self):
        r = orders.OrderList(accountID=self.accountID)
        rv = self.client.request(r)
        return rv

    def get_price_history(self, from_time, instrument, granularity="H1"):
        params = {
            "from": from_time,  # "2005-01-01T00:00:00Z",
            "granularity": granularity,
            "includeFirst": True,
        }
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        response = self.client.request(r)
        return response

    def create_order(self, instrument="EUR_USD", units=1,takeProfitOnFill=1.025, stopLossOnFill=1.019):
        mktOrder = MarketOrderRequest(instrument=instrument,
                                      units=units,
                                      takeProfitOnFill=TakeProfitDetails(price=takeProfitOnFill).data,
                                      stopLossOnFill=StopLossDetails(price=stopLossOnFill).data,
                                      timeInForce=TimeInForce.FOK,
                                      ).data
        r = orders.OrderCreate(accountID=self.accountID, data=mktOrder)
        rv = self.client.request(r)
        if self.debug:
            print("Response: {}\n{}".format(r.status_code, json.dumps(rv, indent=2)))
        return rv

    def create_order_trailing_stop_loss(self, instrument="EUR_USD", units=1, trailingStopLossDistance=0.0025):
        trailingStopLossOnFill = TrailingStopLossDetails(distance=trailingStopLossDistance)
        mktOrder = MarketOrderRequest(instrument=instrument,
                                      units=units,
                                      trailingStopLossOnFill=trailingStopLossOnFill.data,
                                      timeInForce=TimeInForce.FOK,
                                      ).data
        r = orders.OrderCreate(accountID=self.accountID, data=mktOrder)
        rv = self.client.request(r)
        if self.debug:
            print("Response: {}\n{}".format(r.status_code, json.dumps(rv, indent=2)))
        return rv

    def close_all_open_orders(self):
        orders = self.get_open_trades()
        if orders["trades"]:
            for trade in orders["trades"]:
                print("Closing Trade ID {}".format(trade["id"]))
                self.close_trade_order(trade["id"])

    def close_trade_order(self, trade_id):
        r = trades.TradeClose(accountID=self.accountID, tradeID=trade_id)
        rv = self.client.request(r)
        if self.debug:
            print("Response: {}\n{}".format(r.status_code, json.dumps(rv, indent=2)))

    def get_trade_status(self, trade_id):
        open_trades = self.get_open_trades()
        if open_trades:
            for trade in open_trades["trades"]:
                if trade_id == trade["id"]:
                    return trade
        return False

    def get_account_value(self):
        r = accounts.AccountDetails(self.accountID)
        details = self.client.request(r)
        return details["account"]["marginAvailable"]

    def replace_order(self, orderID, data):
        print(self.accountID, orderID, data)
        r = orders.OrderReplace(accountID=self.accountID, orderID=orderID, data=data)
        return self.client.request(r)

class BackTest:
    def __init__(self, strat, oanda):
        self.strategy = strat
        self.oanda = oanda

        from_ts = '2022-07-01T08:00:00Z'

        params = {
            "from": from_ts,  # "2005-01-01T00:00:00Z",
            "granularity": strat.granularity,
            "includeFirst": True,
            "count":5000
        }
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        response = self.oanda.client.request(r)
        self.prices = []

        for price in response["candles"]:
            self.prices.append(float(price["mid"]["c"]))


    def test(self):
        wins, losses = self.strategy.calculate_back_test_trade(self.prices)
        if wins ==0:
            perc = 0
        elif losses == 0:
            perc = 100
        else:
            perc = int((wins/(wins+losses)) *100)
        line = "{},{},{},{},{},{},{},{}".format(self.strategy.instrument, self.strategy.pip, self.strategy.smoothing, self.strategy.check_period_ema, self.strategy.check_period_rsi, wins, losses, perc)
        return line


def quick_test(instrument):
    r = pricing.PricingStream(accountID=api.accountID, params={"instruments": instrument})
    pip_value = 10 * 0.0001 # 10 pip difference
    short = False
    while True:
        for tick in api.client.request(r):
            if tick["type"] == "PRICE":
                print(tick)
                buy_sell = 1
                price = float(tick["asks"][0]["price"])
                if short:
                    buy_sell = -1
                    price = float(tick["bids"][0]["price"])

                take_profit = price + (pip_value * buy_sell)
                stop_loss = price - (pip_value * buy_sell)
                order = api.create_order(units=1*buy_sell, instrument=instrument, takeProfitOnFill=take_profit, stopLossOnFill=stop_loss)
                print(order)
                trade_status = api.get_trade_status(order["orderFillTransaction"]["id"])
                print(trade_status)
                exit()

def write_to_file(file, line):
    with open(file, "a+") as f:
        f.write(line+"\n")



parser = argparse.ArgumentParser(description='Description of your program')
parser.add_argument('-i','--instrument', help='Instrument market. E.G. GBP_USD', default="GBP_USD")
parser.add_argument('-t','--trading', help='Set script to Trade', action="store_true")
parser.add_argument('-x','--testing', help='Sends a buy/sell of one unit to test connection and various conditions', action="store_true")
args = vars(parser.parse_args())


access_token = config.access_token
api = Oanda(access_token)
api.choose_account()
instrument = args["instrument"]


s2 = Strategy2(oanda_api=api, instrument=instrument)
s2.begin_trade()
exit()

if args["trading"]:
    params = top_performers.get_params("data_check_periods_2.txt",instrument=instrument,perc_win=80)
    if params:
        print("Using these params: \n{}".format(params))
        s1 = Strategy1(instrument=instrument, oanda_api=api, smoothing=params["smoothing"], pip=params["pip"], check_period_ema=params["ema"], check_period_rsi=params["rsi"])
    else:
        s1 = Strategy1(instrument=instrument, oanda_api=api, check_period_rsi=10)
    s1.stream_candles()
elif args["testing"]:
    quick_test(instrument)
else:
    pairs = ["GBP_USD", "GBP_CAD", "GBP_SGD", "GBP_CHF", "GBP_NZD", "GBP_PLN", "EUR_USD", "GBP_HKD", "CAD_JPY",
             "GBP_JPY", "NZD_JPY", "AUD_JPY", "CAD_JPY", "CHF_JPY", "EUR_JPY", "SGD_JPY", "ZAR_JPY"]
    # headers = "Instrument,pip,ema_smoothing,ema_check_period,rsi_check_period,wins,losses,perc_win"
    # write_to_file("data_check_periods_2.txt", headers)
    count = 0

    full_pip_range_count = range(5,40,5)
    ema_smoothing_count = range(100,180,10)
    rsi_check_period_count = range(2, 12, 2)
    ema_check_period_count = range(2, 12, 2)
    total_calculations = len(pairs) *len(full_pip_range_count)* len(ema_smoothing_count)* len(rsi_check_period_count)* len(ema_check_period_count)
    for instrument in pairs:
        for pip_range in full_pip_range_count:
            for ema_smoothing in ema_smoothing_count:
                for rsi_check_period in rsi_check_period_count:
                    for ema_check_period in ema_check_period_count:
                        s1 = Strategy1(instrument=instrument, oanda_api=api, pip=pip_range, check_period_ema=ema_check_period, check_period_rsi=rsi_check_period, smoothing=ema_smoothing)
                        bt = BackTest(s1, api)
                        line = bt.test()
                        write_to_file("data_check_periods_2.txt", line)

                    print("\r" + "Pair: {} - Percent complete {}%".format(instrument, float(count/total_calculations)*100), end="")