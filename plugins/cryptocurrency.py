"""
cryptocurrency.py

A plugin that uses the Cryptonator JSON API to get values for cryptocurrencies.

Created By:
    - Luke Rogers <https://github.com/lukeroge>
    - Jon Honeycutt

License:
    GPL v3
"""
from urllib.parse import quote_plus
from datetime import datetime
from time import time

import requests

from cloudbot import hook

crypto_cache = {}
def crypto_info(symbol):
    if symbol in crypto_cache and (time() - crypto_cache[symbol]["time"]) < 300:
        return crypto_cache[symbol]

    using_mbtc = False
    if symbol == "mbtc":
        using_mbtc = True
        symbol = "btc"

    API_URL = "https://api.cryptonator.com/api/ticker/{}-usd"
    encoded = quote_plus(symbol)
    request = requests.get(API_URL.format(encoded))
    request.raise_for_status()

    data = request.json()

    if not data['success']:
        raise Exception(data['error'])

    updated_time = datetime.fromtimestamp(int(float(data['timestamp'])))
    if (datetime.today() - updated_time).days > 2:
        # the API retains data for old ticker names that are no longer updated
        # in these cases we just return a "not found" message
        raise Exception("Currency not found")

    crypto_cache[symbol] = {
        "time": time(),
        "symbol": data['ticker']['base'].upper(),
        "price": float(data['ticker']['price']),
        "change": float(data['ticker']['change']),
    }

    if using_mbtc:
        symbol = "mbtc"
        crypto_cache[symbol] = {
            "time": time(),
            "symbol": "MBTC",
            "price": float(data['ticker']['price']) / 1000,
            "change": float(data['ticker']['change']) / 1000,
        }

    return crypto_cache[symbol]


def crypto_command(symbol, text_amount):
    try:
        data = crypto_info(symbol)
    except Exception as e:
        return str("Exception: {}".format(e))

    dollars_to_coins = text_amount.startswith("$")
    amount = 1
    if text_amount:
        try:
            amount = float(text_amount[1:] if dollars_to_coins else text_amount)
        except:
            pass

    price_usd = data["price"]
    upper_symbol = data["symbol"]
    change = data["change"]
    change_percent = 100 * change / (price_usd - change)
    change_color = "03" if change >= 0 else "04"

    if dollars_to_coins:
        coins = amount / price_usd
        coins_change = coins * change_percent / 100
        result = "${:,.2f} USD = {:,.7f} {}, 1hr change: \x03{}{:,.7f} ({:,.3f}%)\x03".format(
            amount, coins, upper_symbol, change_color, coins_change, change_percent)
    else:
        result = "{:,f} {} = ${:,.2f} USD, 1hr change: \x03{}${:,.2f} ({:,.3f}%)\x03".format(
            amount, upper_symbol, amount * price_usd, change_color, change * amount, change_percent)

    return result

@hook.command("crypto", "coin")
def coin(text):
    """coin <symbol> [amount] - queries the value of the cryptocoin specified by symbol."""
    parts = text.split(" ", 2);
    return crypto_command(parts[0], parts[1] if len(parts) == 2 else "")

# aliases
@hook.command("bitcoin", "btc", autohelp=False)
def bitcoin(text):
    """ -- Returns current bitcoin value """
    return crypto_command("btc", text)


@hook.command("millibitcoin", "mbtc", autohelp=False)
def millibitcoin(text):
    """ -- Returns current millibitcoin value """
    return crypto_command("mbtc", text)


@hook.command("bitcoincash", "bcc", "bch", autohelp=False)
def bitcoin_cash(text):
    """ -- Returns current bitcoin cash value """
    return crypto_command("bch", text)


@hook.command("litecoin", "ltc", autohelp=False)
def litecoin(text):
    """ -- Returns current litecoin value """
    return crypto_command("ltc", text)


@hook.command("iota", "iot", autohelp=False)
def iota(text):
    """ -- Returns current iota value """
    return crypto_command("iot", text)


@hook.command("dogecoin", "doge", autohelp=False)
def dogecoin(text):
    """ -- Returns current dogecoin value """
    return crypto_command("doge", text)


@hook.command("ethereum", "eth", autohelp=False)
def ethereum(text):
    """ -- Returns current ethereum value """
    return crypto_command("eth", text)


@hook.command("ethereumclassic", "etc", autohelp=False)
def ethereum_classic(text):
    """ -- Returns current ethereum classic value """
    return crypto_command("etc", text)


@hook.command("potcoin", "pot", autohelp=False)
def potcoin(text):
    """ -- Returns current potcoin value """
    return crypto_command("pot", text)


@hook.command("ripple", "xrp", autohelp=False)
def ripple(text):
    """ -- Returns current ripple value """
    return crypto_command("xrp", text)


@hook.command("dash", "darkcoin", autohelp=False)
def dash(text):
    """ -- Returns current darkcoin/dash value """
    return crypto_command("dash", text)


@hook.command("zetacoin", "zet", autohelp=False)
def zet(text):
    """ -- Returns current Zetacoin value """
    return crypto_command("zet", text)
