import discord
import requests
import traceback
import schedule
import json
import inspect
import re

from discord.ext import commands
from datetime import datetime

CONFIG_FILE = "config.json"
class Config(object):
    default = {
        "token": "",
        "command_prefix": ".",
        "owner": "", # this user (format: User#1234) can execute all commands and is mainly used for more convenient bootstrapping. You should make this a blank entry once permissions are set properly
        "permissions": {
            "commands": {
                "count": {
                    "roles": [],
                    "users": []
                },
                "allow": {
                    "roles": [],
                    "users": []
                }
            }
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
bot = commands.Bot(command_prefix=config.get("command_prefix"), description='Aschenputtel Emoji Counter')

def log(message):
    print("%s: %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message))

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
    allowed = member.id in config.get("permissions/commands/%s/users" % (command,)) #config["permissions"]["commands"]["command"]["users"]
    i = 0
    while not allowed and i < len(member.roles):
        allowed = member.roles[i].id in config.get("permissions/commands/%s/roles" % (command,)) # config["permissions"]["commands"]["command"]["roles"]
        i += 1
    return allowed

def raw_cmd_string(message):
    return message[(len(config.get("command_prefix")) + len(inspect.stack()[1][3]) + 1):]
    
@bot.event
async def on_ready():
    print("Logged in as %s" % (bot.user.name,))

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
        rs = config.get("permissions/commands/%s/roles" % (command,))
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
            us = config.get("permissions/commands/%s/users" % (command,))
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
    if len(tokens) < 3:
        await bot.say("I need \n(1) a datetime, \n(2) a boolean to indicate whether reactions should be counted as well and \n(3...) at least one channel name as parameters for this command.")
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

    channels = list(filter(lambda x: x, [get_channel(c, ctx) for c in tokens[2:]]))
    if not channels:
        await bot.say("Not a single channel you gave me exists on this server: '`%s`'." % (", ".join(tokens[2:]),))
        return
        
    serverEmojis = dict((e.id, (e,0)) for e in ctx.message.channel.server.emojis)
    regex = re.compile("<:\w+:(\d+)>")
    for c in channels:
        logs = bot.logs_from(c, after = after, limit = 1000000000) #hue
        async for m in logs:
            emojis = [(e,1) for e in regex.findall(m.content) if e in serverEmojis]
            if countReactions:
                emojis += [(r.emoji.id,r.count) for r in m.reactions if r.custom_emoji]
            for i,c in emojis:
                e,old = serverEmojis[i]
                serverEmojis[e.id] = (e,old+c)
                
    await bot.say("Emojis usage since `%s`:\n%s" % (after, "\n".join(["%s: %s" % (e,c) for e,c in serverEmojis.values()])))

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


