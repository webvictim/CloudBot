import re
import html

from cloudbot import hook
from cloudbot.util import web, http


twitch_re = re.compile(r'https?://(?:www\.)?twitch.tv/(\w+)/?(?:\s|$)', re.I)
twitch_clip_re = re.compile(r'https?://clips.twitch.tv/(\w+)', re.I)


@hook.on_start()
def load_api(bot):
    global client_id
    client_id = bot.config.get("api_keys", {}).get("twitch_client_id")


def test_name(s):
    valid = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_/')
    return set(s) <= valid


def twitch_lookup(channel):
    headers = { "Client-ID": client_id }
    data = http.get_json("https://api.twitch.tv/kraken/streams?channel=" + channel, headers=headers)

    if data["streams"]:
        return {
            "title": data["streams"][0]["channel"]["status"],
            "game": data["streams"][0]["game"],
            "view_count": data["streams"][0]["viewers"],
            "channel": channel,
            "url": "http://twitch.tv/" + channel,
            "live": True,
        }

    data = http.get_json("https://api.twitch.tv/kraken/channels/" + channel, headers=headers)
    return {
        "title": data['status'],
        "game":  data['game'],
        "channel": channel,
        "url": "http://twitch.tv/" + channel,
        "live": False,
    }


def pretty_status(channel):
    try:
        data = twitch_lookup(channel)
    except Exception as e:
        return str(e)

    if data['live']:
        return "{} is \x0303online\x03 with {} viewer{} playing \x0306{}\x03: {} - {}".format(
            data['channel'],
            data['view_count'],
            "s" if data['view_count'] != 1 else "",
            data['game'],
            data['title'],
            data['url'])

    return "{} is \x0304offline\x03, previously playing \x0306{}\x03: {} - {}".format(
        data['channel'],
        data['game'],
        data['title'],
        data['url'])


def pretty_clip_info(slug):
    try:
        headers = {
            "Accept": "application/vnd.twitchtv.v5+json",
            "Client-ID": client_id
        }
        data = http.get_json("https://api.twitch.tv/kraken/clips/" + slug, headers=headers)
    except Exception as e:
        return str(e)

    broadcaster_info = "\x02{}\x02".format(data["broadcaster"]["display_name"])
    if data["game"]:
        broadcaster_info += " playing \x02{}\x02".format(data["game"])

    vod_info=""
    if "vod" in data and data["vod"] and "url" in data["vod"]:
        vod_info = " - vod: {}".format(web.try_shorten(data["vod"]["url"]))

    return "\x02{}\x02 - {} - \x02{}s\x02{}".format(
        data["title"], broadcaster_info, int(data["duration"]), vod_info)


@hook.regex(twitch_re)
def twitch_url(match):
    channel = match.group(1)
    return pretty_status(channel)


@hook.regex(twitch_clip_re)
def twitch_clip_url(match):
    slug = match.group(1)
    return pretty_clip_info(slug)


@hook.command('twitch', 'twitchtv')
def twitch(text):
    """<channel name> -- Retrieves the channel and shows its status"""
    if not test_name(text):
        return "Not a valid channel name."

    return pretty_status(text)
