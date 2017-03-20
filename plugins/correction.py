import re

from cloudbot import hook
from cloudbot.util.formatting import ireplace

correction_re = re.compile(r"^[sS]/(.*/.*(?:/[igx]{,4})?)\S*$")

lenny_face = "( ͡° ͜ʖ ͡°)"

@hook.regex(correction_re)
def correction(match, conn, chan, message):
    """
    :type match: re.__Match
    :type conn: cloudbot.client.Client
    :type chan: str
    """
    groups = [b.replace("\/", "/") for b in re.split(r"(?<!\\)/", match.groups()[0])]
    find = groups[0]
    replace = groups[1].replace("\n","\\n").replace("\r","\\r")
    flags = groups[2]
    count = 0 if "g" in flags else 1

    for item in conn.history[chan].__reversed__():
        nick, timestamp, msg = item
        if correction_re.match(msg):
            # don't correct corrections, it gets really confusing
            continue
        msg = msg.replace("\n","\\n").replace("\r","\\r")

        if not find.lower() in msg.lower():
            continue

        # don't bold empty strings
        highlighted_replace = "\x02" + replace + "\x02" if len(replace) else ""

        if "\x01ACTION" in msg:
            msg = msg.replace("\x01ACTION", "").replace("\x01", "")
            mod_msg = ireplace(msg, find, highlighted_replace, count)
            formatted_response = "Correction, * {} {}".format(nick, mod_msg)
        else:
            mod_msg = ireplace(msg, find, highlighted_replace, count)
            formatted_response = "Correction, <{}> {}".format(nick, mod_msg)

        # truncate the result to a reasonable message length
        formatted_response = formatted_response[:400]

        if "l" in flags:
            formatted_response += " " + lenny_face

        message(formatted_response)

        msg = ireplace(msg, find, replace, count)
        # truncate to avoid potential DoS from e.g. repeated s// /g that repeatedly doubles the string length
        msg = msg[:2048]
        conn.history[chan].append((nick, timestamp, msg))
        return
