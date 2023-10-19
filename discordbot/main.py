import discord
import os
import httpx
import re
import traceback


token = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
http = httpx.AsyncClient(
    auth=httpx.BasicAuth("discord-bot", token)
)

def get_prop(name):
    return open(f'/config/{name}').read().strip()

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')

@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    # Check that the message is in a channel of the matching name
    if re.fullmatch(get_prop('verify-activation-channel-regex'), message.channel.name) is None:
        return
    
    # Check that the activation phrase is used
    if message.content.strip().lower() != get_prop('verify-activation-phrase'):
        return
    
    j = {
        'user_id': message.author.id,
        'user_name': message.author.name,
        'channel_id': message.channel.id
    }
    async with message.channel.typing():
        r = await http.post("https://interview.starfallmc.space/new", json=j)
    if r.status_code != 200:
        await message.reply(f'There was an internal error while setting up your interview: POST /new returned code {r.status_code} and text: `{r.text[:1000]}`\n<@495297618763579402> needs to fix this.\nPlease contact a moderator to proceed with your interview.')
        return
    
    resp = r.json()
    print(resp)
    if resp['state'] == 'new':
        try:
            await message.author.send(get_prop('interview-dm-prompt').replace('{{url}}', resp['edit_url']))
        except:
            traceback.print_exc()
            await message.reply(get_prop('interview-created-dm-error-chat-prompt'))
        else:
            await message.reply(get_prop('interview-created-chat-prompt'))
    else:
        try:
            await message.author.send(get_prop('interview-dm-prompt').replace('{{url}}', resp['edit_url']))
        except:
            traceback.print_exc()
        await message.reply(get_prop('interview-resend-chat'))






    



if __name__ == '__main__':
    client.run(token)