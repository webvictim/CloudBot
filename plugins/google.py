import random

from cloudbot import hook
from cloudbot.util import http, formatting


def api_get(kind, query):
    user_ip = '154.58.73.206'
    """Use the RESTful Google Search API"""
    url = 'http://ajax.googleapis.com/ajax/services/search/%s?' \
          'v=1.0&safe=moderate&userip=%s'
    return http.get_json(url % (kind, user_ip), q=query)


#@hook.command("googleimage", "gis", "image")
def googleimage(text):
    """<query> - returns the first google image result for <query>"""

    parsed = api_get('images', text)
    print(parsed)
    if not 200 <= parsed['responseStatus'] < 300:
        raise IOError('error searching for images: {}: {}'.format(parsed['responseStatus'], ''))
    if not parsed['responseData']['results']:
        return 'no images found'
    return random.choice(parsed['responseData']['results'][:10])['unescapedUrl']


#@hook.command("google", "g", "search")
def google(text, bot):
    """<query> - returns the first google search result for <query>"""

    parsed = api_get('web', text)
    print(parsed)
    # if we get 403s, use bing instead
    if parsed['responseStatus'] == 403:
        print("Using Bing as we got a 403")
        from plugins.bing import bing
        return bing(text, bot)
    elif not 200 <= parsed['responseStatus'] < 300:
        raise IOError('error searching for pages: {}: {}'.format(parsed['responseStatus'], ''))
   
    if not parsed['responseData']['results']:
        return 'No results found.'

    result = parsed['responseData']['results'][0]

    title = http.unescape(result['titleNoFormatting'])
    title = formatting.truncate_str(title, 60)
    content = http.unescape(result['content'])

    if not content:
        content = "No description available."
    else:
        content = http.html.fromstring(content).text_content()
        content = formatting.truncate_str(content, 150).replace('\n', '')
    return '{} -- \x02{}\x02: "{}"'.format(result['unescapedUrl'], title, content)
