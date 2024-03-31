import discord
from . import interviews
from . import minecraft_usernames
from . import minecraft_whitelist

cmds = [
    interviews.get_interview_ctx_command,
    minecraft_usernames.get_mc_name_ctx_command,
    minecraft_usernames.update_mc_username_ctx_command,
    minecraft_whitelist.reify_whitelist_cmd,
    minecraft_whitelist.raw_add_whitelist_cmd,
    minecraft_whitelist.raw_del_whitelist_cmd,
    minecraft_whitelist.advanced_whitelist_cmd,
]

def attach(tree: discord.app_commands.CommandTree):
    for cmd in cmds:
        tree.add_command(cmd)