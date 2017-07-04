import re
import requests
import time
 
from bs4 import BeautifulSoup
 
from cloudbot import hook
from cloudbot.util import web, database
 
from sqlalchemy import select
from sqlalchemy import Table, Column, String, PrimaryKeyConstraint
from sqlalchemy.types import Integer, Text, Boolean
from sqlalchemy.exc import IntegrityError
 
 
API_CS = "https://www.googleapis.com/customsearch/v1"
 
rt_regex = re.compile(r".*\brottentomatoes\.com/((?:m|tv)/[^/ ]+)/?", re.I)
google_rt_regex = re.compile(r".*\brottentomatoes\.com/((?:m|tv)/[^/ ]+)/?$", re.I)
rt_game_regex = re.compile(r".*\brottentomatoes\.com/m/[^/ ]+/?$", re.I)
 
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, "
                  "like Gecko) Chrome/41.0.2228.0 Safari/537.36",
    "Referer": "http://www.google.com/"
}
 
 
rt_table = Table(
    "rotten_tomatoes",
    database.metadata,
    Column("identifier", String(128), primary_key=True),
    Column("title", String(256)),
    Column("release_year", String(5)),
    Column("end_year", String(5)),
    Column("run_time", String(10)),
    Column("tomato_meter", String(5)),
    Column("audience_score", String(5)),
    Column("vote_count", String(10)),
    Column("summary", Text),
    Column("type", String(10), default="movie"),
    Column("link", String(256)),
    Column("short_link", String(64)),
    Column("cache_timestamp", Integer),
)
 
rt_links = Table(
    "rotten_tomatoes_links",
    database.metadata,
    Column("query", String(128)),
    Column("for_game", Boolean, default=False),
    Column("link", String(256)),
    Column("cache_timestamp", Integer),
    PrimaryKeyConstraint("query", "for_game")
)
 
@hook.on_start()
def load_api(bot):
    global dev_key
    global cx
 
    dev_key = bot.config.get("api_keys", {}).get("google_dev_key", None)
    cx = bot.config.get("api_keys", {}).get("google_cse_id", None)
 
 
def find_cached_rt_link(db, text, for_rt_game):
    query = rt_links.select(). \
        where(rt_links.c.query == text.strip().lower()). \
        where(rt_links.c.for_game == for_rt_game)
    data = db.execute(query).fetchone()
 
    print("looking for cached link for", text.encode(), ", for game =", for_rt_game)
 
    if not data:
        print("Found no cached link")
        return None
 
    print("Found cached link", data[rt_links.c.link])
    return data[rt_links.c.link]
 
 
def cache_rt_link(db, text, for_rt_game, link):
    print("caching link for", text.encode(), ", for game =", for_rt_game, "link =", link)
    query = rt_links.insert().values(
        query = text.strip().lower(),
        for_game = for_rt_game,
        link = link,
        cache_timestamp = time.time(),
    )
    db.execute(query)
    db.commit()
 
 
def find_rt_link(db, text, for_rt_game=False):
    link = find_cached_rt_link(db, text, for_rt_game)
    if link:
        return link
 
    if not dev_key:
        return "This command requires a Google Developers Console API key."
    if not cx:
        return "This command requires a custom Google Search Engine ID."
 
    query = text + " site:rottentomatoes.com"
    parsed = requests.get(API_CS, params={"cx": cx, "q": query, "key": dev_key}).json()
 
    if not "items" in parsed:
        return None
 
    # find the first result that looks like an rt title page
    for item in parsed["items"]:
        if not for_rt_game and google_rt_regex.match(item["link"]):
            cache_rt_link(db, text, for_rt_game, item["link"])
            return item["link"]
        if for_rt_game and rt_game_regex.match(item["link"]):
            cache_rt_link(db, text, for_rt_game, item["link"])
            return item["link"]
 
    return None
 
 
def bs_clean(element):
    if not element:
        return ""
 
    # remove "&nbsp;" which BS4 translates to unicode
    return element.text.replace(u"\xa0", " ").strip()
 
 
def get_identifier_for_link(link):
    match = rt_regex.match(link.lower())
    if not match:
        return None
 
    return match.group(1)
 
 
def get_cached_rt_info(db, link):
    identifier = get_identifier_for_link(link)
    if not identifier:
        return None
 
    query = rt_table.select().where(rt_table.c.identifier == identifier)
    data = db.execute(query).fetchone()
 
    if not data:
        return None
 
    return {
        "title": data[rt_table.c.title],
        "release_year": data[rt_table.c.release_year],
        "end_year": data[rt_table.c.end_year],
        "run_time": data[rt_table.c.run_time],
        "tomato_meter": data[rt_table.c.tomato_meter],
        "audience_score": data[rt_table.c.audience_score],
        "vote_count": data[rt_table.c.vote_count],
        "summary": data[rt_table.c.summary],
        "type": data[rt_table.c.type],
        "link": data[rt_table.c.link],
        "short_link": data[rt_table.c.short_link],
    }
 
 
def cache_rt_info(db, info):
    identifier = get_identifier_for_link(info["link"])
    if not identifier:
        return
    print("caching info for", identifier, ":", repr(info).encode())
 
    query = rt_table.insert().values(
        identifier = identifier,
        title = info["title"],
        release_year = info["release_year"],
        end_year = info["end_year"],
        run_time = info["run_time"],
        tomato_meter = info["tomato_meter"],
        audience_score = info["audience_score"],
        vote_count = info["vote_count"],
        summary = info["summary"],
        type = info["type"],
        link = info["link"],
        cache_timestamp = time.time(),
    )
    db.execute(query)
    db.commit()
 
 
def get_pretty_rt_info(link, db, append_link=True):
    try:
        return format_info(get_rt_info(link, db), append_link)
    except Exception as e:
        return str(e)
 
def get_rt_info(link, db):
    rt_info = get_cached_rt_info(db, link)
    if rt_info:
        print("returning cached info", repr(rt_info).encode())
        return rt_info
 
    request = requests.get(link, headers=headers)
 
    soup = BeautifulSoup(request.text)
 
    title_element = soup.find("meta", {"property": "og:title"})
    if not title_element or not title_element.get("content", None):
        raise Exception("Unable to find title on Rotten Tomatoes page - ".format(link))
    title = title_element.get("content", None)
    print("title element", title_element)
 
    title_element = soup.find("h1", {"data-type": "title"})
    print("title element", title_element)
    year_text = ""
    if title_element:
        year_element = title_element.find("span")
        print("year element", title_element)
        if year_element:
            year_text = bs_clean(year_element)
    year_text = year_text.strip("() ")
    print("year text", year_text)
 
    release_year = year_text
    end_year = ""
    if "-" in year_text:
        match = re.match(r"(\d+)\D*(\d+)?", year_text)
        release_year = match.group(1)
        if len(match.groups()) > 1:
            end_year = match.group(2)
        else:
            end_year = "present"
    print("rel year", release_year, "end year", end_year)
 
    run_time = ""
    labels = soup.findAll("li", {"class": "meta-row clearfix"})
    for label in labels:
        print("label", label.encode())
        if "Runtime" in label.text:
            print("rt label", label.encode())
            run_time = bs_clean(label.find("div", {"class": "meta-value"}))
    print("runtime", run_time)
 
    tomato_meter_element = soup.find("div", {"class": "critic-score meter"})
    tomato_meter = ""
    if tomato_meter_element:
        tomato_meter = tomato_meter_element.find(lambda tag: not len(tag.attrs)).text + "%"
    print("tomato", tomato_meter)
    vote_count_element = soup.find(text=lambda t: "User Ratings:" in t)
    vote_count = ""
    if vote_count_element:
        vote_count = vote_count_element.parent.nextSibling.strip()
    print("vote count", vote_count)
    audience_score_element = soup.find("div", {"class": "audience-score meter"})
    print("aud score el", audience_score_element)
    audience_score = ""
    if audience_score_element:
        audience_score = bs_clean(audience_score_element.find("div", {"class": "meter-value"}))
    print("aud score", audience_score)
 
    summary_text = bs_clean(soup.find("div", {"id": "movieSynopsis"}))
    print("summ", summary_text.encode())
    summary_text = summary_text[:200]
    if len(summary_text) == 200:
        end = summary_text.rfind(" ")
        summary_text = summary_text[0:end] + "..."
    print("summ short", summary_text.encode())
 
    content_type = "movie"
    rating_element = soup.find("meta", {"property": "og:type"})
    print("r8 element", rating_element)
    if rating_element and "tv" in rating_element.get("content", None):
        content_type = "tv"
    print("type", content_type)
 
    rt_info = {
        "title": title,
        "release_year": release_year,
        "end_year": end_year,
        "run_time": run_time,
        "tomato_meter": tomato_meter,
        "audience_score": audience_score,
        "vote_count": vote_count,
        "summary": summary_text,
        "link": link,
        "short_link": "",
        "type": content_type,
    }
    print("rt_info", repr(rt_info).encode())
 
    cache_rt_info(db, rt_info)
 
    return rt_info
 
 
def format_info(info, append_link):
    result = info["title"]
    if info["release_year"]:
        if info["end_year"]:
            result += " ({}-{})".format(info["release_year"], info["end_year"])
        else:
            result += " ({})".format(info["release_year"])
 
    if info["type"] == "tv":
        result += ", TV Series"
    elif info["run_time"]:
        result += ", runtime " + info["run_time"]
 
    if info["tomato_meter"]:
        result += ", critic score {}".format(info["tomato_meter"])
 
    if info["audience_score"]:
        result += ", audience score {}".format(info["audience_score"])
        if info["vote_count"]:
            result += " ({} vote{})".format(
                info["vote_count"], "s" if info["vote_count"] != "1" else "")
 
    if info["summary"]:
        result += ". {} ".format(info["summary"])
    else:
        result += ". "
 
    result = result[0:400]
 
    if append_link and len(result) + len(info["link"]) < 400:
        result += info["link"]
 
    return result
 
 
@hook.regex(rt_regex)
def rt_url(db, match):
    identifier = match.group(1)
    link = "https://www.rottentomatoes.com/" + identifier
    return get_pretty_rt_info(link, db, append_link=False)
 
 
@hook.command
def rt(text, db):
    """rt <movie> - gets information about <movie> from Rotten Tomatoes"""
    link = find_rt_link(db, text)
    if not link:
        return "Could not find a rotten tomatoes entry for that query."
 
    return get_pretty_rt_info(link, db)
 
 
@hook.command
def rtg(text, db):
    def create_short_link(db, info):
        if info["short_link"]:
            return
        print("trying to create short link for", info["link"])
        info["short_link"] = web.try_shorten(info["link"])
        if info["short_link"] == info["link"]:
            print("Failed to create short link!")
            return
        print(info["link"], " -> ", info["short_link"], ", updating db...")
        identifier = get_identifier_for_link(info["link"])
        query = rt_table.update().values(short_link = info["short_link"]). \
            where(rt_table.c.identifier == identifier)
        db.execute(query)
        db.commit()
 
    titles = text.split(",")
    if len(titles) > 2:
        return "Error: Please separate the two movie titles with one comma, and do not include any commas that appear in the movie title."
 
    for title in titles:
        if not len(title.strip()):
            return "Error: Empty title."
 
    links = []
    for title in titles:
        link = find_rt_link(db, title, for_rt_game=True)
        if not link:
            return "Could not find a rotten tomatoes movie entry for '{}'.".format(title)
        links.append(link)
 
    try:
        infos = []
        for link in links:
            infos.append(get_rt_info(link, db))
    except Exception as e:
        return str(e)
 
    for info in infos:
        if not info["tomato_meter"]:
            return "Could not find a critic score for {} ({}) - {}".format(
                info["title"], info["release_year"], link)
 
    if len(infos) == 1:
        return "{} ({}) has a critic score of {} - {}".format(
            infos[0]["title"], infos[0]["release_year"], infos[0]["tomato_meter"], infos[0]["link"])
 
    create_short_link(db, infos[0])
    create_short_link(db, infos[1])
 
    return "{} ({}) has a critic score of {} - {}. {} ({}) has a critic score of {} - {}. Combined score is {}.".format(
            infos[0]["title"],
            infos[0]["release_year"],
            infos[0]["tomato_meter"],
            infos[0]["short_link"],
            infos[1]["title"],
            infos[1]["release_year"],
            infos[1]["tomato_meter"],
            infos[1]["short_link"],
            int(infos[0]["tomato_meter"].strip("%")) +
            int(infos[1]["tomato_meter"].strip("%")))
