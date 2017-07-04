import re
import requests
import time
 
from bs4 import BeautifulSoup
 
from cloudbot import hook
from cloudbot.util import database
 
from sqlalchemy import select
from sqlalchemy import Table, Column, String, PrimaryKeyConstraint
from sqlalchemy.types import REAL, Integer, Text
from sqlalchemy.exc import IntegrityError
 
 
API_CS = 'https://www.googleapis.com/customsearch/v1'
 
imdb_regex = re.compile(r'.*\bimdb\.com/title/(tt[0-9]+)', re.I)
 
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, '
                  'like Gecko) Chrome/41.0.2228.0 Safari/537.36',
    'Referer': 'http://www.google.com/'
}
 
 
imdb_table = Table(
    'imdb',
    database.metadata,
    Column('title_code', String(20), primary_key=True),
    Column('title', String(50)),
    Column('release_year', String(5)),
    Column('run_time', String(10)),
    Column('score', String(5)),
    Column('vote_count', String(10)),
    Column('summary', Text),
    Column('type', String(10), default="movie"),
    Column('link', String(255)),
    Column('cache_timestamp', Integer),
)
 
 
@hook.on_start()
def load_api(bot):
    global dev_key
    global cx
 
    dev_key = bot.config.get("api_keys", {}).get("google_dev_key", None)
    cx = bot.config.get("api_keys", {}).get("google_cse_id", None)
 
 
def find_imdb_link(text):
    if not dev_key:
        return "This command requires a Google Developers Console API key."
    if not cx:
        return "This command requires a custom Google Search Engine ID."
 
    text = text + " site:imdb.com"
    parsed = requests.get(API_CS, params={"cx": cx, "q": text, "key": dev_key}).json()
 
    if not "items" in parsed:
        return None
 
    # find the first result that looks like an imdb title page
    for item in parsed['items']:
        if imdb_regex.match(item['link']):
            return item['link']
 
    return None
 
 
def bs_clean(element):
    if not element:
        return ""
 
    # remove "&nbsp;" which BS4 translates to unicode
    return element.text.replace(u"\xa0", " ").strip()
 
 
def get_title_code_for_link(link):
    match = imdb_regex.match(link.lower())
    if not match:
        return None
 
    return match.group(1)
 
 
def get_cached_imdb_info(db, link):
    title_code = get_title_code_for_link(link)
    if not title_code:
        return None
 
    query = imdb_table.select().where(imdb_table.c.title_code == title_code)
    data = db.execute(query).fetchone()
 
    if not data:
        return None
 
    return {
        "title": data[imdb_table.c.title],
        "release_year": data[imdb_table.c.release_year],
        "run_time": data[imdb_table.c.run_time],
        "score": data[imdb_table.c.score],
        "vote_count": data[imdb_table.c.vote_count],
        "summary": data[imdb_table.c.summary],
        "type": data[imdb_table.c.type],
        "link": data[imdb_table.c.link],
    }
 
 
def cache_imdb_info(db, info):
    title_code = get_title_code_for_link(info["link"])
    if not title_code:
        return
 
    query = imdb_table.insert().values(
        title_code = title_code,
        title = info["title"],
        release_year = info["release_year"],
        run_time = info["run_time"],
        score = info["score"],
        vote_count = info["vote_count"],
        summary = info["summary"],
        type = info["type"],
        link = info["link"],
        cache_timestamp = time.time(),
    )
    db.execute(query)
    db.commit()
 
 
def get_imdb_info(link, db, append_link=True):
    imdb_info = get_cached_imdb_info(db, link)
    if imdb_info:
        return format_imdb_info(imdb_info, append_link)
 
    request = requests.get(link, headers=headers)
 
    soup = BeautifulSoup(request.text)
 
    title_bar = soup.find('div', {'class': 'title_bar_wrapper'})
    if not title_bar:
         return "Unable to parse IMDb page - {}".format(link)
 
    title_element = title_bar.find('h1', {'itemprop': 'name'})
    if not title_element:
        return "Unable to find title on IMDb page - ".format(link)
    title_and_year = bs_clean(title_element)
 
    year_element = title_bar.find('span', {'id': 'titleYear'})
    year_text = ""
    if year_element:
        year_text = bs_clean(year_element)
 
    if year_text and title_and_year.endswith(year_text):
        title = title_and_year[:-len(year_text)].strip()
    else:
        title = title_and_year.strip()
    year = year_text.strip("()")
 
    run_time = bs_clean(title_bar.find('time', {'itemprop': 'duration'}))
    score = bs_clean(title_bar.find('span', {'itemprop': 'ratingValue'}))
    vote_count = bs_clean(title_bar.find('span', {'itemprop': 'ratingCount'}))
 
    summary = soup.find('div', {'class': 'plot_summary_wrapper'})
    if summary:
        summary = summary.find('div', {'itemprop': 'description'})
    if summary:
        # remove the "see more" link
        see_more = summary.find('a')
        if see_more:
            see_more.extract()
        summary = bs_clean(summary)
        summary = summary.replace(u"\xbb", "").strip()
    else:
        summary = ""
 
    content_type = "movie"
    rating_element = title_bar.find('meta', {'itemprop': 'contentRating'})
    if rating_element and "TV" in rating_element.get("content", None):
        content_type = "tv"
 
    imdb_info = {
        "title": title,
        "release_year": year,
        "run_time": run_time,
        "score": score,
        "vote_count": vote_count,
        "summary": summary,
        "link": link,
        "type": content_type,
    }
 
    cache_imdb_info(db, imdb_info)
 
    return format_imdb_info(imdb_info, append_link)
 
 
def format_imdb_info(info, append_link):
    result = info["title"]
    if info["release_year"]:
        result += " ({})".format(info["release_year"])
 
    if info["type"] == "tv":
        result += ", TV Series"
    elif info["run_time"]:
        result += ", " + info["run_time"]
 
    if info["score"] and info["vote_count"]:
        result += ", {}/10 ({} vote{})".format(
            info["score"], info["vote_count"], "s" if info["vote_count"] != "1" else "")
 
    if info["summary"]:
        result += ". {} ".format(info["summary"])
    else:
        result += ". "
 
    result = result[0:400]
 
    if append_link and len(result) + len(info["link"]) < 400:
        result += info["link"]
 
    return result
 
 
@hook.regex(imdb_regex)
def imdb_url(db, match):
    title_code = match.group(1)
    link = "http://imdb.com/title/" + title_code
    return get_imdb_info(link, db, append_link=False)
 
@hook.command
def imdb(text, db):
    """imdb <movie> - gets information about <movie> from IMDb"""
    link = find_imdb_link(text)
    if not link:
        return "Could not find an IMDb entry for that query."
 
    return get_imdb_info(link, db)
