import discord
import requests
import traceback
import json
import inspect
import re
import sqlite3
import time

from discord.ext import commands
from datetime import datetime

CONFIG_FILE = "config.json"
CHARACTER_LIMIT = 300

def log(message):
    print("%s: %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message))

class Config(object):
    default = {
        "token": "",
        "command_prefix": ".",
        "owner": "", # this user (format: User#1234) can execute all commands and is mainly used for more convenient bootstrapping. You should make this a blank entry once permissions are set properly
        "commands": {
            "count": {
                "permissions": {
                    "roles": [],
                    "users": []
                }
            },
            "allow": {
                "permissions": {
                    "roles": [],
                    "users": []
                }
            },
            "taggeth": {
                "permissions": {
                    "roles": [],
                    "users": []
                },
                "log_text": False
            }
        },
        "autoreply_user": { # format: username: reply string

        }
    }

    def __init__(self, jsonFile):
        try:
            self.values = self.readFromFile(jsonFile)
        except FileNotFoundError:
            self.values = Config.default
            self.writeToFile(jsonFile)

    def writeToFile(self, jsonFile):
        with open(jsonFile, 'w') as f:
            f.write(json.dumps(self.values))

    def readFromFile(self, jsonfile):
        with open(jsonfile, 'r') as f:
            return json.load(f)

    def get(self, path):
        try:
            tokens = path.split("/")
            v = self.values
            for t in tokens:
                v = v[t]
            return v
        except KeyError:
            log("Tried to access invalid path in config file: '%s'" % (path,))
            return None

config = Config(CONFIG_FILE)

class Database(object):
    def __init__(self, db):
        self.connection = sqlite3.connect(db)

        c = self.connection.cursor()
        c.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name=?""", ("deletions",))
        if not c.fetchone():
            self._initSchema()

    def _initSchema(self):
        c = self.connection.cursor()
        c.executescript("""
            CREATE TABLE deletions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                timestamp INTEGER,
                message TEXT
            );
            CREATE TABLE mention_types(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT
            );
            CREATE TABLE mentions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deletion_id INTEGER REFERENCES deletions(id),
                mentioned_id INTEGER,
                mentioned_type TEXT REFERENCES mention_types(name)
            );
            INSERT INTO mention_types(name) VALUES ('user'),('role');
            """)
        self.connection.commit()
        log("Initialised database.")

    def insertDeletion(self, mes):
        c = self.connection.cursor()
        c.execute("INSERT INTO deletions(user_id, timestamp, message) VALUES(?,?,?)"
                  , (mes.author.id, int(time.mktime(mes.timestamp.timetuple())), mes.content if config.get("commands/taggeth/log_text") else None))
        did = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        for m in [(did, m.id, "user") for m in mes.mentions] + [(did, m.id, "role") for m in mes.role_mentions]:
            c.execute("INSERT INTO mentions(deletion_id, mentioned_id, mentioned_type) VALUES(?,?,?)", m)
        self.connection.commit()
        c.close()

db = Database("ashbowl.db")
bot = commands.Bot(command_prefix=config.get("command_prefix"), description='Aschenputtel Emoji Counter')

def find_by_name(name, seq):
    return discord.utils.find(lambda e: e.name == name, seq)

def get_channel(name, ctx):
    return find_by_name(name, ctx.message.channel.server.channels)

def get_role(name, ctx):
    return find_by_name(name, ctx.message.channel.server.roles)

def can_execute(member):
    if "%s#%s" % (member.name, member.discriminator) == config.get("owner"):
        log("Permission bypass by owner, please blank out this entry in your config asap.")
        return True
    command = inspect.stack()[1][3]
    allowed = member.id in config.get("commands/%s/permissions/users" % (command,)) #config["permissions"]["commands"]["command"]["users"]
    i = 0
    while not allowed and i < len(member.roles):
        allowed = member.roles[i].id in config.get("commands/%s/permissions/roles" % (command,)) # config["permissions"]["commands"]["command"]["roles"]
        i += 1
    return allowed

def raw_cmd_string(message):
    return message[(len(config.get("command_prefix")) + len(inspect.stack()[1][3]) + 1):]

async def say_safe(message):
    if len(message) <= CHARACTER_LIMIT:
        await bot.say(message)
    else:
        tokens = message.split("\n")
        while tokens:
            currentMessage = ""
            while tokens and (len(currentMessage) + len(tokens[0]) < CHARACTER_LIMIT):
                currentMessage += "\n%s" % (tokens.pop(0),)
            if not currentMessage:
                raise Exception("Could not break message of length %s into smaller messages. Are there enough linebreaks in the original message?" % (len(message),))
            await bot.say(currentMessage)


@bot.event
async def on_ready():
    log("Logged in as %s." % (bot.user.name,))

@bot.command(pass_context=True)
async def allow(ctx):
    if not can_execute(ctx.message.author):
        return

    tokens = raw_cmd_string(ctx.message.content).split(" ")
    if len(tokens) < 3 or tokens[0] not in ("true", "false"):
        await bot.say("I need \n(1) `true` to give permission or `false` to remove it, \n(2) a commandname (without the prefix) and \n(3) a rolename or username for this command. Roles have precendence over users with the same name.")
        return

    give = tokens[0] == "true"
    command = tokens[1]
    userOrGroup = " ".join(tokens[2:])

    role = get_role(userOrGroup, ctx)
    if role:
        rs = config.get("commands/%s/permissions/roles" % (command,))
        if give:
            if not role.id in rs:
                rs.append(role.id)
            await bot.say("The role '%s' can now execute the command `%s`." % (role, command))
        else:
            if role.id in rs:
                rs.remove(role.id)
            await bot.say("The role '%s' can no longer execute the command `%s`." % (role, command))
        config.writeToFile(CONFIG_FILE)

    else:
        user = ctx.message.channel.server.get_member_named(userOrGroup)
        if user:
            us = config.get("commands/%s/permissions/users" % (command,))
            if give:
                if not user.id in us:
                    us.append(user.id)
                await bot.say("The user '%s' can now execute the command `%s`." % (user, command))
            else:
                if user.id in us:
                    us.remove(user.id)
                await bot.say("The user '%s' can no longer execute the command `%s`." % (user, command))
            config.writeToFile(CONFIG_FILE)
        else:
            await bot.say("Found neither a user nor a role with the name '%s' on this server." % (userOrGroup,))

@bot.command(pass_context=True)
async def count(ctx):
    if not can_execute(ctx.message.author):
        return

    tokens = raw_cmd_string(ctx.message.content).split(" ")
    if len(tokens) < 2:
        await bot.say("I need \n(1) a datetime, \n(2) a boolean to indicate whether reactions should be counted as well and \n(3...) at one or more channel names as parameters for this command. If no channel is passed, all accessible channel are used instead.")
        return

    try:
        after = datetime.strptime(tokens[0], '%Y-%m-%d')
    except ValueError:
        await bot.say("First parameter must be a valid timezone-naive datetime representing UTC time of format `yyyy-mm-dd`.")
        return

    if tokens[1] not in ("true", "false"):
        await bot.say("Second parameter must either be `false` to only count emojis in messages or `true` to also count reactions .")
        return
    countReactions = tokens[1] == "true"

    if len(tokens) >= 3:
        channels = list(filter(lambda x: x, [get_channel(c, ctx) for c in tokens[2:]]))
        if not channels:
            await bot.say("Not a single channel you gave me exists on this server: '`%s`'." % (", ".join(tokens[2:]),))
            return
    else:
        channels = ctx.message.server.channels

    serverEmojis = dict((e.id, (e,0)) for e in ctx.message.channel.server.emojis)
    regex = re.compile("<:\w+:(\d+)>")
    for c in channels:
        try:
            logs = bot.logs_from(c, after = after, limit = 1000000000) #hue
            async for m in logs:
                emojis = [(e,1) for e in regex.findall(m.content) if e in serverEmojis]
                if countReactions:
                    emojis += [(r.emoji.id,r.count) for r in m.reactions if r.custom_emoji and r.emoji.id in serverEmojis]
                for i,c in emojis:
                    e,old = serverEmojis[i]
                    serverEmojis[e.id] = (e,old+c)
        except discord.errors.Forbidden:
            log("Skipping channel '%s' due to lack of access permission." % (c.name,))

    
    # serverEmojis = sorted(serverEmojis.items(), key=lambda kv: kv[1], reverse = True)
    serverEmojis = sorted(serverEmojis.values(), key=lambda kv: kv[1], reverse=True)

    mes = "Emojis usage since `%s`:\n%s" % (after, "\n".join(["%s: %s" % (e,c) for e,c in serverEmojis]))
    log(mes)
    await say_safe(mes)
    # await bot.say(mes)

@bot.event
async def on_message_delete(mes):
    if mes and (mes.mentions or mes.role_mentions):
        db.insertDeletion(mes)

@bot.event
async def on_message(mes):
    name = mes.author.display_name
    if name in config.get("autoreply_user"):
        text = config.get("autoreply_user/%s" % (name,))
        await bot.send_message(mes.channel, text)
        log("Replied '%s' to %s." % (text,name))
    await bot.process_commands(mes)

try:
    token = config.get("token")
    if not token:
        log("You have to provide a valid token in the config file.")
        exit(1)
    else:
        bot.run(token)
except:
    log("Top level error!")
    traceback.print_exc()
