import discord
from . import interviews
from . import minecraft_usernames

cmds = [
    interviews.get_interview_ctx_command,
    minecraft_usernames.get_mc_name_ctx_command,
    minecraft_usernames.update_mc_username_ctx_command,
]

def attach(tree: discord.app_commands.CommandTree):
    for cmd in cmds:
        tree.add_command(cmd)