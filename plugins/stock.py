import csv
import requests

from cloudbot import hook

# See http://www.jarloo.com/yahoo_finance/ for field names.
field_names = ['symbol', 'name', 'ask', 'change', 'percent_change']
query_url = "http://finance.yahoo.com/d/quotes.csv?f=snac1p2"
link_url = "https://finance.yahoo.com/quote/"


def get_ticker_data(symbol):
    request = requests.get(query_url, params={'s': symbol})
    request.raise_for_status()

    result = next(csv.DictReader([request.text], fieldnames=field_names))

    if result['name'] == "N/A":
        return None

    return result


@hook.command()
def stock(text):
    """<symbol> -- gets stock information"""
    symbol = text.strip().upper()

    try:
        data = get_ticker_data(symbol)
    except requests.exceptions.HTTPError as e:
        return "Could not get stock data: {}".format(e)

    if not data:
        return "No results for that symbol."

    data['color'] = "04" if float(data['change']) < 0 else "03"

    return "{symbol} ({name}): {ask} \x03{color}{change} ({percent_change})\x03 - ".format(**data) + link_url + symbol
