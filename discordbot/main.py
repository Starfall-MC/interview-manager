import discord
import os
import httpx


token = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
http = httpx.AsyncClient(
    auth=httpx.BasicAuth("discord-bot", token)
)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('$hello'):
        await message.channel.send('Trying HTTP!')
        r = await http.get("https://interview.starfallmc.space/")
        await message.channel.send('HTTP response: ' +  r.text)

if __name__ == '__main__':
    client.run(token)