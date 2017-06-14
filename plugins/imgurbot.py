import json
import requests
import time
from operator import itemgetter
#import unicodedata

from cloudbot import hook
from cloudbot.util import web

last_seen = {}
allowed_domains = ['i.imgur.com', 'gfycat.com', 'imgur.com', 'i.redd.it']

def get_content(subreddit):
    if not subreddit in last_seen:
        last_seen[subreddit] = {}

    url = "http://api.reddit.com/r/{0}/.json".format(subreddit)
    headers = {'User-agent': 'Cloudbot IRC bot by u/webvictim - https://github.com/webvictim/CloudBot'}

    try:
        response = requests.get(url, headers=headers, timeout=5).json()
    except:
        print(response)
        return("Couldn't load any results for r/{0} as Reddit didn't respond in a timely fashion. Sorry.".format(subreddit))
    
    if 'error' in response:
        print(response)
        if response['error'] == 404:
            return("/r/{0} isn't a real subreddit.".format(subreddit))
        elif response['error'] == 403:
            return("/r/{0} is a private subreddit.".format(subreddit))
        else:
            return("Something went wrong. Sorry.")

    links = []
    iterator = 0
    if 'children' in response['data']:
        if len(response['data']['children']) > 0:
            while (len(links) < 10) and (iterator < len(response)):
                for child in response['data']['children']:
                    iterator = iterator + 1
                    if 'domain' in child['data'] and child['data']['domain'] in allowed_domains:
                        if 'over_18' in child['data']:
                            id = child['data']['id']
                            if id in last_seen[subreddit]:
                                child['data']['lastseen'] = last_seen[subreddit][id]
                            else:
                                child['data']['lastseen'] = 0
                            links.append(child['data'])

            if len(links) == 0:
                return("I found results for /r/{0} but none looked like images to me.".format(subreddit))
    return links

@hook.command("image", "imgurbot", "redditimage", autohelp=False)
def imgurbot(text, reply):
    subreddit = text.split(" ")[0]
    if subreddit == "":
        reply("Your input is bad and you should feel bad.")
    else:
        bot_reply = get_content(subreddit)

        if type(bot_reply) is list and subreddit:
            if len(bot_reply) == 0:
                reply("No image posts were found in /r/{0}".format(subreddit))
            else:
                bot_reply = sorted(bot_reply, key=itemgetter('lastseen'))
                last_seen[subreddit][bot_reply[0]['id']] = int(time.time())
                suffix = ''
                if (bot_reply[0]['over_18'] is True):
                    suffix = ' [nsfw]'
                permalink = web.try_shorten("https://www.reddit.com{0}".format(bot_reply[0]['permalink']))
                reply("[{0}] {1} - \"{2}\"{3} | comments: {4}".format(subreddit, bot_reply[0]['url'], bot_reply[0]['title'], suffix, permalink))
        elif type(bot_reply) is str:
            reply(bot_reply)
        elif type(bot_reply) is list and len([x for x in bot_reply if x['id'] not in last_seen[subreddit]]) != 0:
            reply("Something messed up. Sorry.")
