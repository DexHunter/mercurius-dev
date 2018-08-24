from __future__ import absolute_import
from __future__ import print_function
from __future__ import division

from flask import Flask, request, json
from flask_cors import CORS, cross_origin
from mercurius.data import candlereader
from datetime import datetime, timedelta
import numpy as np
import ccxt
from mercurius.strategy.ons import ons
from mercurius.strategy.ucrp import ucrp
from mercurius.strategy.ubah import ubah
from mercurius.strategy.best import best
from mercurius.data.candlereader import CandleReader
from mercurius.utils.indicators import max_drawdown, sharpe, positive_count, negative_count, moving_accumulate, sortino

app = Flask(__name__)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'

ALGOS = {'ucrp': ucrp, 'ons': ons, 'ubah': ubah, 'best': best}
INDICATORS = {"portfolio value": np.prod,
              "sharpe ratio": sharpe,
              "max drawdown": max_drawdown,
              "positive periods": positive_count,
              "negative periods": negative_count,
              "sortino ratio": sortino,
              "postive day": lambda pcs: positive_count(moving_accumulate(pcs, 48)),
              "negative day": lambda pcs: negative_count(moving_accumulate(pcs, 48)),
              "postive week": lambda pcs: positive_count(moving_accumulate(pcs, 336)),
              "negative week": lambda pcs: negative_count(moving_accumulate(pcs, 336)),
              "average": np.mean}

@app.route('/uploadAlgo', methods=['POST', 'GET'])
def run_algo():
    if request.method == "POST":
        data = request.get_json()
        exchange = data["exchange"]
        start_time = data["start_time"]
        end_time = data["end_time"]
        timeframe = data["timeframe"]
        symbols = data["symbols"]
        da = candlereader.CandleReader(
            symbols, start_time, end_time, timeframe, exchange).get_data()
        close_price = da.sel(feature='close')
        # algo.run()
        response = {}
        response['close'] = close_price.data.tolist()

        response['date'] = [
            x / 1e6 for x in da['openTime'].values.astype(np.int64)]
        # print(response['date'])
        # print(type(response['date']))
        print('PASS')
        return json.jsonify(response)
    print('FAIL')
    return 'FAIL'


@app.route('/coin', methods=['POST', 'GET'])
@cross_origin()
def get_coin_price(exchange="poloniex"):
    """default poloniex"""
    res = {}
    symbol = request.args.get('symbol', 'ETH')
    start = request.args.get('start', (datetime.utcnow(
    ) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"))
    end = request.args.get(
        'end', (datetime.utcnow()).strftime("%Y-%m-%d %H:%M:%S"))
    algo = request.args.get('algo', 'ucrp')

    # fixed trading list
    trading_list = ['ETH/BTC', 'ETC/BTC', 'LTC/BTC', 'XRP/BTC', 'XLM/BTC', 'XEM/BTC']

    tf = request.args.get('tf', '30m')  # timeframe
    #exchange = getattr(ccxt, exchange)
    exchange = ccxt.poloniex()
    pair = str(symbol).upper() + "/BTC"
    start = exchange.parse8601(start)
    end = exchange.parse8601(end)
    num_candles = int((end - start) / exchange.parse_timeframe(tf) / 1e3)
    data = exchange.fetch_ohlcv(pair, tf, start, num_candles)
    time_list = []
    ohlc = []
    volume = []
    for i in data:
        time_list.append((datetime.utcfromtimestamp(int(i[0] / 1e3))).strftime('%Y-%m-%d %H:%M:%S'))
        ohlc.append(i[1:5])
        volume.append(i[5])
    #app.logger.info(data)

    close_data = CandleReader(trading_list, start, end, tf).get_close(False, True)
    agent = ALGOS[algo]()
    agent.trade(close_data, tc=0.025)
    portfolio_value = agent.finish()

    ind_re = []
    for ind in list(INDICATORS.keys()):
        rs = INDICATORS[ind](portfolio_value['portfolio_diff'][:-1])
        if isinstance(rs, np.ndarray):
            #print(ind, rs)
            rs = rs.tolist()[0]
        if isinstance(rs, np.int64):
            #print(ind, rs)
            rs = int(rs)
        ind_re.append(rs)

    res['time'] = time_list
    res['ohlc'] = ohlc
    res['vol'] = volume
    res['symbols'] = trading_list
    res['pv'] = portfolio_value['portfolio'][:-1].tolist() #do not get the last one(NaN)
    res['ind'] = ind_re

    return json.jsonify(res)

# NOTE: For now, (Buggy) need a time stamp for a start exactly starting from a day
@app.route('/backtest/<starttimestamp>/<endtimestamp>', methods=['GET'])
def get_back_test(starttimestamp, endtimestamp):
    res = backtest(
        datetime.fromtimestamp(int(starttimestamp)).strftime("%Y-%m-%d %H:%M:%S"),
        datetime.fromtimestamp(int(endtimestamp)).strftime("%Y-%m-%d %H:%M:%S"),
        location="../../train_package/"
    )
    # res = backtest("2018-06-02 00:00:00", "2018-06-06 00:00:00", location="../../train_package/")
    time_values = res.get("portfolio_changes_history").keys().tolist()
    rate_values = [value for value in generator(res.get("portfolio_changes_history").values)]
    return json.jsonify({"xaxis": time_values, "data": rate_values})


def generator(list):
    res = 1
    for i in list:
        yield i
        res *= i

def main():
    app.run(host='0.0.0.0', debug=True)

if __name__ == "__main__":
    import sys, os
    sys.path.append(os.getcwd())
    main()