import os
import discord
import httpx

token = os.getenv('DISCORD_TOKEN')
http = httpx.AsyncClient(
    auth=httpx.BasicAuth("discord-bot", token)
)

def get_prop(name):
    return open(f'/config/{name}').read().strip()

client: discord.Client = None
