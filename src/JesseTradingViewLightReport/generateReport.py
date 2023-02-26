# -*- coding: utf-8 -*-
from jesse.services.file import store_logs
import jesse.helpers as jh
from jesse.modes import backtest_mode
from jesse.config import config
from jesse.services import charts
from jesse.services import report
from jesse.routes import router
from datetime import datetime, timedelta
from jesse.store import store
import jesse.services.metrics as stats
from jesse.enums import trade_types
from jesse.utils import numpy_candles_to_dataframe
# from jesse.strategies import Strategy

import pandas as pd
import numpy as np
from typing import Union
import codecs
from bottle import template
import os
from enum import IntEnum

FILE_NAME_LIGHTWEIGHT_CHARTS = 'lightweight-charts.standalone.production.js'
VERSION_LIGHTWEIGHT_CHARTS = '@4.0.0'


class CD(IntEnum):
    date = 0
    open = 1
    close = 2
    high = 3
    low = 4
    volume = 5


def read_file(file_name: str) -> str:
    with codecs.open(os.path.join(os.path.dirname(__file__), file_name), 'r', 'utf-8') as f:
        return f.read()


def pvsra(candles: np.ndarray, sequential=False) -> pd.DataFrame:
    df = numpy_candles_to_dataframe(candles)
    df["averageVolume"] = df["volume"].rolling(10).mean()
    df["climax"] = df["volume"] * (df["high"] - df["low"])
    df["highestClimax10"] = df["climax"].rolling(window=10).max()
    df.loc[((df['volume'] >= 2 * df["averageVolume"]) | (
            df["climax"] >= df["highestClimax10"])), 'climaxVolume'] = 1
    df.loc[((df['volume'] >= 1.5 * df["averageVolume"]) & (
            df['climaxVolume'] != 1)), 'risingVolume'] = 1
    df.loc[(df["close"] > df["open"]), 'isBull'] = 1

    df.loc[((df["risingVolume"] == 1) & (df["isBull"] == 1)), 'risingBullVolume'] = 1
    df.loc[((df["risingVolume"] == 1) & (df["isBull"] != 1)), 'risingBearVolume'] = 1

    df.loc[((df["climaxVolume"] == 1) & (df["isBull"] == 1)), 'climaxBullVolume'] = 1
    df.loc[((df["climaxVolume"] == 1) & (df["isBull"] != 1)), 'climaxBearVolume'] = 1

    if sequential:
        return df
    else:
        return df.iloc[-1]


def generateReport(customData={}, chartConfig={}):
    """
    Generate TradingView report.
    :param customData: dict of custom data
    :param chartConfig: dict with config for chart; -> {
        'isPvsra': True or False,
        'pnl': True or False,
        'numDecimals': 3,
    }
    :param rounding: number of decimal places for numbers
    :return:
    """
    if config["app"]["trading_mode"] == 'backtest':

        cstLineTpl = r"""

            chart.add{{type}}({{!options}}).setData(await getCustomData({{offset}}))

        """

        tpl = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DUAL_THRUST-Binance Spot-ETH-USDT-2h</title>
    <style>
      .go-to-realtime-button {
        width: 27px;
        height: 27px;
        position: absolute;
        display: none;
        padding: 7px;
        box-sizing: border-box;
        font-size: 10px;
        border-radius: 50%;
        text-align: center;
        z-index: 1000;
        color: #B2B5BE;
        background-color: #222;
        box-shadow: 0 2px 5px 0 #a3a3a3;
      }
    </style>    
</head>
<body style="background-color:black;">
    <div id="tvchart"></div>
</body>

"""
        # if chartConfig.get('isPvsra', None):
        #    tpl += fr"""<script>{read_file(FILE_NAME_LIGHTWEIGHT_CHARTS)}</script>"""
        # else:
        tpl += fr"""<script src="https://unpkg.com/lightweight-charts{VERSION_LIGHTWEIGHT_CHARTS}/dist/{FILE_NAME_LIGHTWEIGHT_CHARTS}"></script>"""
        tpl += r"""
<script>
{{!equityData}}

{{!candleData}}

{{!orderData}}

{{!numDecimals}}

const getEquityData = async () => {
    return equityData.split('\n').map((row) => {
        const [time, equity] = row.split(',');
        return {
            time: time * 1,
            value: equity * 1,
        };
    });
};

const getCandleData = async () => {
  return candleData.split('\n').map((row) => {
    const [time, open, high, low, close, volume, color, borderColor, wickColor] = row.split(',');
    var res = {
      time: time * 1,
      open: open * 1,
      high: high * 1,
      low: low * 1,
      close: close * 1,
    };
    if(color.trim().length > 0 && borderColor.trim().length > 0 && wickColor.trim().length > 0)
    {
      res["color"] = color;
      res["borderColor"] = borderColor;
      res["wickColor"] = wickColor;
    }
    return res;
  });
};

const getVolumeData = async () => {
  return candleData.split('\n').map((row) => {
    const [time, x1, x2, x3, x4, volume] = row.split(',');
    return {
      time: time * 1,
      value: volume * 1
    };
  });
};

function roundToDecimals(n, decimals) {
  var log10 = n ? Math.floor(Math.log10(n)) : 0,
     div = log10 < 0 ? Math.pow(10, decimals - log10 - 1) : Math.pow(10, decimals);
  return Math.round(n * div) / div;
}

const getOrderData = async () => {
  return orderData.split('\n').map((row) => {
    const [time, mode, side, type, qty, price, pnl_order, pnl_accumulated] = row.split(',');
    const price_round = roundToDecimals(parseFloat(price), numDecimals);
    const qty_round = roundToDecimals(parseFloat(qty), numDecimals);
    const pnl_order_round = roundToDecimals(parseFloat(pnl_order), numDecimals);
    const pnl_accumulated_round = roundToDecimals(parseFloat(pnl_accumulated), numDecimals);
    const position = (side === 'sell')?'aboveBar':'belowBar';
    const shape = (side === 'sell')?'arrowDown':'arrowUp';
    const color = (side === 'sell')?'rgba(251, 192, 45, 1)':'#2196F3';
    return {
      time: time * 1,
      position: position,
      color: color,
      shape : shape,
      text : type + ' @ ' + price_round + ' : ' + qty_round + mode + ' $' + pnl_order_round
    };
  });
};

const getPnlData = async () => {
  return orderData.split('\n').map((row) => {
    const [time, mode, side, type, qty, price, pnl_order, pnl_accumulated] = row.split(',');
    const pnl_accumulated_round = roundToDecimals(parseFloat(pnl_accumulated), numDecimals);
    return {
      time: time * 1,
      value: pnl_accumulated_round * 1
    };
  });
};

const getCustomData = async (offset) => {
  return candleData.split('\n').map((row) => {
    const arr = row.split(',');
    return {
      time: arr[0] * 1,
      value: arr[offset+9] * 1
    };
  });
};

var chartWidth = window.innerWidth-20;
var chartHeight = window.innerHeight-20;
const displayChart = async () => {
  const chartProperties = {
    width: chartWidth,
    height: chartHeight,
    layout: {
      background: { color: 'rgba(17,17,17,0.83)'},
      textColor: '#DDD',
    },
    grid: {
        vertLines: {
            color: 'rgba(17,17,17,0.83)',
        },
        horzLines: {
            color: 'rgba(22,22,22,0.83)',
        }
    },
    timeScale: {
      timeVisible: true,
      secondsVisible: true,
    },
    crosshair: {
        // Change mode from default 'magnet' to 'normal'.
        // Allows the crosshair to move freely without snapping to datapoints
        mode: LightweightCharts.CrosshairMode.Normal,

        // Vertical crosshair line (showing Date in Label)
        vertLine: {
            width: 6,
            color: 'rgba(188,192,219,0.15)',
            style: LightweightCharts.LineStyle.Solid,
            labelBackgroundColor: 'rgba(23,95,192,0.34)',
        },

        // Horizontal crosshair line (showing Price in Label)
        horzLine: {
            color: '#7E7D7DFF',
            labelBackgroundColor: '#605f5f',
        },
    },
    watermark: {
      color: 'rgba(154,154,154,0.07)',
      visible: true,
      text: '{{!title}}',
      fontSize: 40,
      family: 'Comic Sans',
      horzAlign: 'bottom',
      vertAlign: 'top',
    }
  };

  const domElement = document.getElementById('tvchart');
  const chart = LightweightCharts.createChart(domElement, chartProperties);
  const candleseries = chart.addCandlestickSeries();
  const klinedata = await getCandleData();
  candleseries.setData(klinedata);
  const odata = await getOrderData();
  candleseries.setMarkers(odata);

  const histogramSeries = chart.addHistogramSeries({
    color: 'rgba(4,111,232,0.09)',
    priceFormat: {
        type: 'volume',
    },
	priceScaleId: '', // set as an overlay by setting a blank priceScaleId
  });
  histogramSeries.priceScale().applyOptions({
    scaleMargins: {
        top: 0.7, // highest point of the series will be 70% away from the top
        bottom: 0,
    },
  });
  const vdata = await getVolumeData();
  histogramSeries.setData(vdata);

  {{!customCharts}}

  {{!equityCharts}}

  {{!pnlCharts}}

  var width = 27;
  var height = 27;
  var button = document.createElement('div');
  button.className = 'go-to-realtime-button';
  button.style.left = (chartWidth - width - 60) + 'px';
  button.style.top = (chartHeight - height - 30) + 'px';
  button.style.color = '#444';
  button.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 14 14" width="14" height="14"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2" d="M6.5 1.5l5 5.5-5 5.5M3 4l2.5 3L3 10"></path></svg>';
  document.body.appendChild(button);

  var timeScale = chart.timeScale();
  timeScale.subscribeVisibleTimeRangeChange(function() {
    var buttonVisible = timeScale.scrollPosition() < 0;
    button.style.display = buttonVisible ? 'block' : 'none';
  });

  button.addEventListener('click', function() {
    timeScale.scrollToRealTime();
  });

  button.addEventListener('mouseover', function() {
	button.style.background = '#DDD';
	button.style.color = '#444';
  });

  button.addEventListener('mouseout', function() {
	button.style.background = '#DDD';
	button.style.color = '#444';
  });

  window.addEventListener('resize', () => {
    chart.resize(window.innerWidth, window.innerHeight);
  });
};

displayChart();
</script>
</html>        
        """

        file_name = jh.get_session_id()
        studyname = backtest_mode._get_study_name()

        # could optimise this if the generated report already contains data,
        # just start from where it was up to and append.
        # start_date = datetime.fromtimestamp(store.app.starting_time / 1000)

        # date_list = [start_date + timedelta(days=x) for x in range(len(store.app.daily_balance))]
        # fullCandles = backtest_mode.load_candles(date_list[0].strftime('%Y-%m-%d'), date_list[-1].strftime('%Y-%m-%d'))
        # candles = fullCandles[jh.key(router.routes[0].exchange, router.routes[0].symbol)]['candles']
        candles = store.candles.get_candles(router.routes[0].exchange, router.routes[0].symbol,
                                            router.routes[0].timeframe)

        # if('mainChartLines' in customData and len(customData['mainChartLines'])>0):
        #   for key, value in customData['mainChartLines'].items():
        #   #   candles += [value]
        #     for idx, item in enumerate(candles):
        #       item = np.append(item, value[idx])

        if chartConfig.get('isPvsra', None):
            pvsraData = pvsra(candles, True)
            file_name += '-PVSRA'

        candleData = 'const candleData = `'
        for idx, candle in enumerate(candles):
            candleData += str(candle[CD.date] / 1000) + ','
            candleData += str(candle[CD.open]) + ','
            candleData += str(candle[CD.high]) + ','
            candleData += str(candle[CD.low]) + ','
            candleData += str(candle[CD.close]) + ','
            candleData += str(candle[CD.volume])
            if chartConfig.get('isPvsra', None):
                # color, borderColor,wickColor
                if pvsraData['climaxBullVolume'].iloc[idx] == 1:
                    candleData += ',lime,lime,white'
                elif pvsraData['climaxBearVolume'].iloc[idx] == 1:
                    candleData += ',red,red,gray'
                elif pvsraData['risingBullVolume'].iloc[idx] == 1:
                    candleData += ',blue,blue,white'
                elif pvsraData['risingBearVolume'].iloc[idx] == 1:
                    candleData += ',fuchsia,fuchsia,gray'
                elif pvsraData['isBull'].iloc[idx] == 1:
                    candleData += ',silver,silver,gray'
                else:
                    candleData += ',gray,gray,gray'
            else:
                candleData += ', , , '

            if len(customData) > 0:
                for key, value in customData.items():
                    if idx < len(value['data']):
                        candleData += ','
                        candleData += str(value['data'][idx])

            candleData += '\n'
        if candleData[-1] == '\n':
            candleData = candleData.rstrip(candleData[-1])  # remove last new line
        candleData += '`;'

        pnl_accumulated = 0
        orderData = 'const orderData = `'
        for trade in store.completed_trades.trades:
            trading_fee = jh.get_config(f'env.exchanges.{trade.exchange}.fee')
            average_entry_price = 0
            average_entry_size = 0
            side_factor = 1
            if trade.type == trade_types.SHORT:
                side_factor = -1
            for order in trade.orders:
                if order.is_executed:
                    fee = abs(order.qty) * order.price * trading_fee
                    if (((trade.type == trade_types.LONG) and (order.side == 'buy')) or (
                            (trade.type == trade_types.SHORT) and (order.side == 'sell'))):
                        # pnl is just fees as increasing size
                        pnl_order = -fee
                        average_entry_price = (
                                (average_entry_price * average_entry_size + order.price * abs(
                                    order.qty))
                                / (average_entry_size + abs(order.qty))
                        )
                        average_entry_size += abs(order.qty)
                    else:
                        # closing some position
                        pnl_order = (order.price - average_entry_price) * abs(
                            order.qty) * side_factor - fee
                        average_entry_size -= abs(order.qty)

                    pnl_accumulated += pnl_order

                    mode = ''
                    if order.is_stop_loss:
                        mode = ' (SL)'
                    elif order.is_take_profit:
                        mode = ' (TP)'
                    orderData += str(order.executed_at / 1000) + ','
                    orderData += mode + ','
                    orderData += order.side + ','
                    orderData += order.type + ','
                    orderData += str(order.qty) + ','
                    orderData += str(order.price) + ','
                    orderData += str(pnl_order) + ','
                    orderData += str(pnl_accumulated) + '\n'
        if orderData[-1] == '\n':
            orderData = orderData.rstrip(orderData[-1])  # remove last new line
        orderData += '`;'

        equityCharts = ''
        equityData = 'const equityData = `'
        daily_balance = charts.equity_curve()
        if chartConfig.get('equity', None):
            if daily_balance:
                for balance in daily_balance:
                    equityData += str(balance['timestamp']) + ','
                    equityData += str(balance['balance']) + '\n'
                else:
                    equityData = equityData.rstrip('\n')
            equityCharts = "chart.addLineSeries({priceScaleId: \'left\', lineWidth: 1, color: \'rgba(251, 192, 45, 0.3)\'}).setData(await getEquityData())"
            equityCharts += "\nchart.applyOptions({leftPriceScale: {visible: true}});"
        equityData += '`;'

        customCharts = ''
        if len(customData) > 0:
            idx = 0
            for key, value in customData.items():
                if 'options' not in value:
                    value['options'] = {}
                value['options']['title'] = key
                if 'type' not in value:
                    value['type'] = 'LineSeries'
                customCharts += template(cstLineTpl,
                                         {'options': str(value['options']), 'offset': idx,
                                          'type': value['type']})
                idx += 1

        pnlCharts = ''
        if chartConfig.get('pnl', None):
            pnlCharts = "chart.addLineSeries({color: \'rgba(4, 111, 232, 1)\', lineWidth: 1, priceScaleId: \'left\',}).setData(await getPnlData())"

        # Get number of decimals from config, default to 3
        numDecimals = fr"""const numDecimals = {chartConfig.get('numDecimals', 3)};"""

        info = {
            'title': studyname,
            'candleData': candleData,
            'equityData': equityData,
            'orderData': orderData,
            'customCharts': customCharts,
            'pnlCharts': pnlCharts,
            'equityCharts': equityCharts,
            'numDecimals': numDecimals,
        }

        result = template(tpl, info)

        filename = "storage/JesseTradingViewLightReport/" + file_name + '.html'
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with codecs.open(filename, "w", "utf-8") as f:
            f.write(result)

        return filename
