# Plugin by Infinity - <https://github.com/infinitylabs/UguuBot>

import requests
from bs4 import BeautifulSoup

from cloudbot import hook
from cloudbot.util import formatting


@hook.on_start()
def init(db):
    db.execute("create table if not exists horoscope(nick primary key, sign)")
    db.commit()


@hook.command(autohelp=False)
def horoscope(text, db, bot, notice, nick):
    """<sign> - get your horoscope"""

    headers = {'User-Agent': bot.user_agent}

    # check if the user asked us not to save his details
    dontsave = text.endswith(" dontsave")
    if dontsave:
        sign = text[:-9].strip().lower()
    else:
        sign = text

    db.execute("create table if not exists horoscope(nick primary key, sign)")

    if not sign:
        sign = db.execute("select sign from horoscope where "
                          "nick=lower(:nick)", {'nick': nick}).fetchone()
        if not sign:
            notice("horoscope <sign> -- Get your horoscope")
            return
        sign = sign[0]

    url = "http://my.horoscope.com/astrology/free-daily-horoscope-{}.html".format(sign)

    try:
        request = requests.get(url, headers=headers)
        request.raise_for_status()
    except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
        return "Could not get horoscope: {}.".format(e)

    soup = BeautifulSoup(request.text)

    horoscope_text = soup.find_all('div', {'class': 'block-horoscope-text'})

    if not horoscope_text:
        return "Could not get the horoscope for {}.".format(sign)
    else:
        horoscope_text = horoscope_text[0].text.strip()

    result = "\x02{}\x02 {}".format(text, horoscope_text)

    if text and not dontsave:
        db.execute("insert or replace into horoscope(nick, sign) values (:nick, :sign)",
                   {'nick': nick.lower(), 'sign': sign})
        db.commit()

    return result
