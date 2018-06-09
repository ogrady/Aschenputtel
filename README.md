# Aschenputtel
Aschenputtel is a cutom Discord bot whose first functionality was to count the usage of server-specific emojis over time period.
It also features a simple **global** permission system.

## Setup
Install the dependencies by running
`python setup.py install`

Run the bot once to get a config template:
`python src/aschenputtel.py`

You can now edit the new `config.json` and add a bot token and yourself as owner (format: `user#1234`). 
You can of course edit the permission values manually. Just be aware that permissions work using the unique group/user-IDs given out by discord, not the account name. The `owner` makes an exception of this format to simplify setup.

Once you have `allow`d your admin groups access to `allow`, you can blank out the `owner` field and restart the bot.
*Note: blank out, as in "no value", the entry has to remain in the config anyway.*

## Commands
`count {yyyy-mm-dd} {true|false} [list of channel names]`: counts all emojis since the given time in the listed channels. If the second parameter is true, reactions are included in the count as well.

`allow {true|false} {command name} {user or rolename}`: allow the given user with *displayname* or role with that name to execute a command if the first parameter is `true` or disallows it if it is `false`. If there is role and a user with the same name, the role will get precedence.
