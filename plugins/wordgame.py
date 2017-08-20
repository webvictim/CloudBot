import os
import random

from cloudbot import hook
from cloudbot.event import EventType
from cloudbot.util import database

from sqlalchemy import Table, Column, Integer, String, PrimaryKeyConstraint, select


game_channel = "#friends"
game_running = False
game_letters = None
guessed_words = []
unguessed_words = []
words_list = None


score_table = Table(
    'word_game_score',
    database.metadata,
    Column('nick', String(25)),
    Column('words_guessed', Integer, default=0),
    Column('total_score', Integer, default=0),  # used for querying
    PrimaryKeyConstraint('nick')
)


@hook.on_start()
def initialize(bot):
    global words_list

    path = os.path.join(bot.data_dir, "word_game.txt")
    file = open(path, "r")
    words_list = file.read().splitlines()


def restart_game():
    assert game_running, "Game is not running!"
    global game_running, game_letters, guessed_words, unguessed_words

    result = ""
    if unguessed_words:
        result = "You guessed {} of {} words. You didn't guess: {}. ".format(
            len(guessed_words), len(guessed_words) + len(unguessed_words), ", ".join(unguessed_words))

    game_running = False
    game_letters = None
    guessed_words = []
    unguessed_words = []

    result += start_game()

    return result


def start_game():
    global game_letters, unguessed_words, game_running, words_list
    assert not game_running, "Game is already running!"

    if not words_list:
        return "No words in my list!"

    random_line_num = random.randrange(0, len(words_list))
    words = words_list[random_line_num].split(" ")
    del words_list[random_line_num]
    game_letters = ''.join(random.sample(words[0], len(words[0])))
    unguessed_words = words[1:]
    game_running = True

    return "What are the {} {}-letter words that can be made from {}?".format(
        len(unguessed_words), len(game_letters), game_letters)


def game_status():
    guessed_string = (": " + ", ".join(guessed_words)) if len(guessed_words) else ""
    return "Letters currently in play: {}. {} of {} words have been guessed{}. Type @wg end to give up.".format(
        game_letters, len(guessed_words), len(guessed_words) + len(unguessed_words), guessed_string)


def player_guessed_word(db, nick, word):
    global guessed_words, unguessed_words
    assert word in unguessed_words, "word is not in unguessed words!"

    unguessed_words.remove(word)
    guessed_words.append(word)

    if unguessed_words:
        guessed_string = (": " + ", ".join(guessed_words)) if len(guessed_words) > 1 else ""
        result = "{} is correct for 2 points. {} of {} words guessed{}.".format(
            word, len(guessed_words), len(guessed_words) + len(unguessed_words), guessed_string)
        score = 2
    else:
        score = 3
        result = "{} is correct for 3 points. ".format(word)
        result += restart_game()

    db.execute("""INSERT or IGNORE INTO word_game_score(nick, words_guessed, total_score) values(:nick, 0, 0)""", {'nick': nick.lower()})
    query = score_table.update().values(
        words_guessed=score_table.c.words_guessed + 1,
        total_score=score_table.c.total_score + score
    ).where(score_table.c.nick == nick.lower())
    db.execute(query)
    db.commit()

    return result


def game_score(db, nick=None):
    if nick:
        query = db.execute(
            select([score_table])
            .where(score_table.c.nick == nick.lower())
        ).fetchone()

        if not query:
            return "{} has 0 points.".format(nick)
        else:
            return "{} has guessed {} word{} for a total of {} points.".format(
                nick, query['words_guessed'], "" if query['words_guessed'] == 1 else "s", query['total_score'])

    query = db.execute(
        select([score_table])
        .order_by(score_table.c.total_score.desc())
        .limit(5)
    ).fetchall()

    if not query:
        return "No scores recorded yet."

    result = "Top players: "
    result += ", ".join(map(lambda row: "{} ({})".format(row['nick'], row['total_score']), query))
    return result

@hook.command("wordgame", "wg")
def wordgame(db, text, nick, chan, bot):
    if not chan == game_channel:
        return

    text_parts = text.split(" ")
    if text_parts[0] == "score" and len(text_parts) == 2:
        return game_score(db, text_parts[1])
    if text == "scores":
        return game_score(db)

    if game_running:
        if text == "end":
            return restart_game()
        if text in unguessed_words:
            return player_guessed_word(db, nick, text)
        if text:
            return "{} is not a word I'm looking for.".format(text)
        return game_status()
    else:
        return start_game()


@hook.event(EventType.message, singlethread=True)
def on_message(conn, db, nick, chan, content):
    if not chan == game_channel or not game_running:
        return

    content = content.lower()

    # player_guessed_word modifies unguessed_words, so iterate a copy
    for word in unguessed_words.copy():
        if word in content:
            conn.message(chan, "({}) ".format(nick) + player_guessed_word(db, nick, word))
