import decimal
import math
import random
import re
from threading import Lock
from time import time

from cloudbot import hook
from cloudbot.event import EventType
from cloudbot.util import database

from sqlalchemy import Table, Column, Integer, String, PrimaryKeyConstraint, select

candidate_pool = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 25, 50, 75, 100]
game_timeout = 180

def nick_substitution(nick):
    nick_lower = nick.lower()
    if "jmr" in nick_lower:
        return "jmrsplat"
    if "bigbear" in nick_lower:
        return "bigbear"
    if ("vade" in nick_lower or "nade" in nick_lower or "ctkid" in nick_lower or "connecticutkid" in nick_lower or
        nick_lower == "vn" or nick_lower == "feelsgoodman" or nick_lower == "feelsbadman"):
        return "vadernader"
    if "ec10" in nick_lower:
        return "ec10"
    if "bossphone" in nick_lower or "bossdesktop" in nick_lower:
        return "BossDesktop"
    return nick


score_table = Table(
    'countdown_score',
    database.metadata,
    Column('nick', String(25)),
    Column('total_wins', Integer, default=0),
    Column('total_score', Integer, default=0),
    Column('total_perfect_scores', Integer, default=0),
    PrimaryKeyConstraint('nick')
)


class NonCandidateOperandException(Exception):
    pass

class CountdownGame:
    def __init__(self, connection, channel):
        self.connection = connection
        self.channel = channel
        self.is_running = False

        self._candidate_numbers = []
        self._goal_number = 0
        self._closest_expression = ""
        self._closest_expression_nickname = ""
        self._closest_expression_value = 0
        self._closest_expression_distance = 0
        self._game_start_time = 0
        self._expression_attempts = 0

    def start_game(self):
        self.is_running = True
        return "Let's play Countdown! " + self.reset_game()

    def reset_game(self):
        self._candidate_numbers = random.sample(candidate_pool, 6)
        self._goal_number = random.randrange(1000)
        if random.randint(1, 32) == 32:
            self._candidate_numbers.append(69)
            self._candidate_numbers.append(420)
            self._goal_number = random.randrange(1000, 6969)
        self._candidate_numbers.sort()

        self._closest_expression = ""
        self._closest_expression_nickname = ""
        self._closest_expression_value = 0
        self._closest_expression_distance = 0

        # The timer doesn't start until the first scoring expression is entered.
        self._game_start_time = 0

        self._expression_attempts = 0

        return self.goal_text()

    def goal_text(self):
        return "Goal is \x0303{}\x03, candidates are \x0303{}\x03.".format(self._goal_number, self._candidate_numbers)

    def evaluate_countdown_expression(self, expression):
        def process(operand_stack, operator_stack):
            if len(operand_stack) < 2:
                raise Exception("too few operands.")
            if not operator_stack:
                raise Exception("too few operators.")

            value2 = operand_stack.pop()
            value1 = operand_stack.pop()
            operator = operator_stack.pop()

            if operator == "+":
                result = value1 + value2
            elif operator == "-":
                result = value1 - value2
            elif operator == "*":
                result = value1 * value2
            elif operator == "^":
                if value1 > 0 and value2 > 100 or value1 > 0 and math.log10(value1) > 10 and value2 > 2:
                    raise Exception("result too large.".format(operator))
                result = value1 ** value2
            elif operator == "%":
                result = value1 % value2
            elif operator == "/":
                result = value1 / value2
            else:
                raise Exception("unexpected operator {}.".format(operator))

            operand_stack.append(result)

        def precedence(operator):
            if operator == "^":
                return 3
            if operator in "*/%":
                return 2
            if operator in "+-":
                return 1
            return 0

        if not re.match("^[\d\+\-\*\/\^\%\(\) ]+$", expression):
            raise Exception("invalid character.")

        # We need a mutable copy below to look for duplicate candidates in expression
        candidate_numbers_copy = self._candidate_numbers.copy()

        operand_stack = []
        operator_stack = []
        tokens = list(filter(lambda x: len(x), map(lambda x: x.strip(), re.split("(\D)", expression))))

        # print("tokens: {}".format(tokens))

        i = 0
        while i < len(tokens):
            token = tokens[i].strip()
            i += 1
            if token == "":
                continue

            if token.isdigit():
                token_int = int(token)

                if not token_int in self._candidate_numbers:
                    raise NonCandidateOperandException("non-candidate operand {}.".format(token_int))

                if not token_int in candidate_numbers_copy:
                    raise Exception("repeats operand {}.".format(token_int))

                candidate_numbers_copy.remove(token_int)
                operand_stack.append(int(token))
            elif token in "+-*/^%" and (len(operator_stack) == 0 or precedence(token) > precedence(operator_stack[-1])):
                 operator_stack.append(token)
            elif token == "(":
                 operator_stack.append(token)
            elif token == ")":
                while True:
                    process(operand_stack, operator_stack)
                    if operator_stack[-1] == "(":
                        operator_stack.pop()
                        break
            elif token in "+-*/^%":
                # evaluate the current higher-precedence operator on the stack and return to this one
                process(operand_stack, operator_stack)
                i -= 1
            else:
                raise Exception("unexpected token {}.".format(token))

        while operator_stack:
            process(operand_stack, operator_stack)

        if len(operand_stack) > 1:
            raise Exception("unexpected operand {}.".format(operand_stack[-2]))

        if operand_stack[0] != int(operand_stack[0]):
            raise Exception("not a whole number.")

        return int(operand_stack.pop())

    def score_from_distance(distance):
        if distance == 0:
            return 10
        if distance <= 5:
            return 7
        if distance <= 10:
            return 5
        return 0

    def status(self):
        result = self.goal_text()
        result += " {} attempt{} made. ".format(self._expression_attempts, "" if self._expression_attempts == 1 else "s")
        if self._closest_expression_nickname:
            result += "{} is closest with {} = {}. {}s left.".format(self._closest_expression_nickname,
                self._closest_expression, self._closest_expression_value, int(game_timeout - (time() - self._game_start_time)))
        elif self._expression_attempts:
            result += "No one on the board."
        return result

    def evaluate_player_expression(self, nick, expression, database):
        expression_operators = re.findall("[\+\-\*\/\^\%]", expression)
        if not len(expression_operators) and (not int(expression) in self._candidate_numbers or
            CountdownGame.score_from_distance(abs(int(expression) - self._goal_number)) == 0):
            return

        result = 0
        try:
            result = self.evaluate_countdown_expression(expression)
            self._expression_attempts += 1
        except NonCandidateOperandException as e:
            if len(expression_operators) == 1:
                return
            self._expression_attempts += 1
            return "Error: {}".format(e)
        except Exception as e:
            self._expression_attempts += 1
            return "Error: {}".format(e)

        if result == self._goal_number:
            score = CountdownGame.score_from_distance(0)
            self.record_score(nick, score, database)
            return "You got it! {} points. New game - {}".format(score, self.reset_game())

        expression_distance = abs(result - self._goal_number)
        closest_expression_distance = abs(self._closest_expression_value - self._goal_number)
        if expression_distance > 10:
            if result > 0 and math.log10(result) > 10:
                result = decimal.Decimal(result)
                expression_distance = decimal.Decimal(expression_distance)
                return "{} = {:.3e}, you're {:.3e} away and p bad at math.".format(expression, result, expression_distance)
            else:
                return "{} = {}, too far away to score.".format(expression, result, expression_distance)

        if not self._closest_expression:
            self._closest_expression = expression
            self._closest_expression_nickname = nick
            self._closest_expression_value = result
            self._game_start_time = time()
            score = CountdownGame.score_from_distance(expression_distance)
            return "{} = {}, {} away. Good for {} points. {}s timer started.".format(expression, result,
                expression_distance, score, game_timeout)

        if expression_distance < closest_expression_distance:
            previous_closest_nick = self._closest_expression_nickname
            self._closest_expression = expression
            self._closest_expression_nickname = nick
            self._closest_expression_value = result
            self._game_start_time = time()
            score = CountdownGame.score_from_distance(expression_distance)
            if previous_closest_nick == self._closest_expression_nickname:
                return "{} = {}, {} away. Good for {} points. {}s on the clock.".format(
                    expression, result, expression_distance, score, game_timeout)
            else:
                return "{} = {}, {} away. Good for {} points and unseats {}! {}s on the clock.".format(
                    expression, result, expression_distance, score, previous_closest_nick, game_timeout)
        else:
            return "{} = {}, {} away. {} still leads. {}s left.".format(
                expression, result, expression_distance, self._closest_expression_nickname, int(game_timeout - (time() - self._game_start_time)))

    def record_score(self, nick, score, database):
        nick = nick_substitution(nick)
        database.execute("""INSERT or IGNORE INTO countdown_score(nick, total_wins, total_score, total_perfect_scores) values(:nick, 0, 0, 0)""", {'nick': nick.lower()})
        query = score_table.update().values(
            total_wins=score_table.c.total_wins + 1,
            total_score=score_table.c.total_score + score,
            total_perfect_scores=score_table.c.total_perfect_scores + (1 if score == CountdownGame.score_from_distance(0) else 0)
        ).where(score_table.c.nick == nick.lower())
        database.execute(query)
        database.commit()

    def tick(self, current_time, database):
        if not self._game_start_time:
            return

        if (current_time - self._game_start_time) < game_timeout:
            print("{}: {} secs left".format(self.channel, int(game_timeout - (time() - self._game_start_time))))
            return

        if not self.connection or not self.connection.ready:
            return

        score = CountdownGame.score_from_distance(abs(self._goal_number - self._closest_expression_value))
        self.record_score(self._closest_expression_nickname, score, database)
        self.connection.message(self.channel, "Countdown game over - {} wins {} point{}!".format(
            self._closest_expression_nickname, score, "" if score == 1 else "s"))
        self.connection.message(self.channel, self.start_game())


@hook.on_start()
def initialize(db, bot):
#    db.execute("""DELETE FROM countdown_score WHERE nick = 'bigbear|laptop'""")
#    db.execute("""DELETE FROM countdown_score WHERE nick = 'jmrsplatt_mobile'""")
#    db.execute("""UPDATE countdown_score SET total_wins = 12, total_score = 102, total_perfect_scores = 6 WHERE nick = 'jmrsplat'""")
#    db.execute("""DELETE FROM countdown_score WHERE 1""")
#    db.execute("""UPDATE countdown_score SET total_wins = total_wins - 1, total_score = total_score - 10, total_perfect_scores = total_perfect_scores - 1 WHERE nick = 'jasoncookuk'""")
#    db.execute("""UPDATE countdown_score SET total_wins = total_wins + 1, total_score = total_score + 10, total_perfect_scores = total_perfect_scores + 1 WHERE nick = 'jotun'""")
#    db.commit()
    return


games = []
def get_or_create_game(connection, channel):
    global games
    for game in games:
        if game.connection == connection and game.channel == channel:
            return game
    games.append(CountdownGame(connection, channel))
    return games[-1]

def get_game(connection, channel):
    global games
    for game in games:
        if game.connection == connection and game.channel == channel:
            return game
    return None

mutex = Lock()
@hook.periodic(1, initial_interval=1)
def check_game(bot, db):
    global mutex
    mutex.acquire()
    try:
        current_time = time()
        for game in games:
            game.tick(current_time, db)
    finally:
        mutex.release()

def get_score(db, nick=None):
    if nick:
        query = db.execute(
            select([score_table])
            .where(score_table.c.nick == nick.lower())
        ).fetchone()

        if not query:
            return "{} has 0 points.".format(nick)
        else:
            result = "{} has {} win{} for {} points".format(
                nick, query['total_wins'], "" if query['total_wins'] == 1 else "s",
                      query['total_score'])
            if query['total_perfect_scores']:
                result += ", including {} perfect expression{}!".format(
                      query['total_perfect_scores'], "" if query['total_perfect_scores'] == 1 else "s")
            else:
                result += "."
            return result

    query = db.execute(
        select([score_table])
        .order_by(score_table.c.total_score.desc())
        .limit(3)
    ).fetchall()

    if not query:
        return "No scores recorded yet."

    player_scores = map(lambda row: "{} ({} win{}, {} point{})".format(row['nick'],
        row['total_wins'], "" if row['total_wins'] == 1 else "s",
        row['total_score'], "" if row['total_score'] == 1 else "s"), query)

    result = "Top players: " + ", ".join(player_scores)
    return result


@hook.command("countdown", "cd")
def countdown(db, bot, conn, chan, nick, text):
    text_parts = text.split(" ")
    if text_parts[0] == "score" and len(text_parts) == 2:
        return get_score(db, text_parts[1])
    if text == "scores":
        return get_score(db)

    game = get_or_create_game(conn, chan)
    if game.is_running:
        return game.status()
    else:
        return game.start_game()


def looks_like_expression(string):
    if re.search("[\+\-\*\/\^\% ]+$", string):
        return False
    return re.search("\d", string) and re.search("^[\d\+\-\*\/\^\%\(\) ]+$", string)

@hook.event(EventType.message, singlethread=True)
def on_message(conn, db, nick, chan, content):
    if looks_like_expression(content):
        game = get_game(conn, chan)
        if not game:
            return

        result = game.evaluate_player_expression(nick, content, db)
        if result:
            conn.message(chan, "({}) {}".format(nick, result))
