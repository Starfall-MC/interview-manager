import asyncio
import discord
import os
import httpx
import re
import traceback
from discord.ext import tasks


token = os.getenv('DISCORD_TOKEN')


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
http = httpx.AsyncClient(
    auth=httpx.BasicAuth("discord-bot", token)
)

def get_prop(name):
    return open(f'/config/{name}').read().strip()



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

@tasks.loop(seconds=15)
async def process_modmail():
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    #await modmail_chan.send(f"Trying to process modmail...")
    try:
        r = await http.get('https://interview.starfallmc.space/modmail')
        r.raise_for_status()
        r = r.json()
        for entry in r:
            await modmail_chan.send(entry['content'], allowed_mentions=discord.AllowedMentions.all())
            del_resp = await http.delete(f"https://interview.starfallmc.space/modmail/{entry['id']}")
            del_resp.raise_for_status()
    except Exception as e:
        await modmail_chan.send(f"ERROR while fetching modmail: {repr(e)}\n<@495297618763579402>", allowed_mentions=discord.AllowedMentions.all())
        traceback.print_exc()
        raise e

@process_modmail.before_loop
async def before_modmail():
    print('waiting for bot to be ready before modmail...')
    await client.wait_until_ready()
    print("Ready, now working on modmail!")

@tasks.loop(seconds=16)
async def process_accepts_rejects():
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    guild = modmail_chan.guild
    #await modmail_chan.send(f"Trying to process accepts/rejects...")
    try:
        #await modmail_chan.send(f"Trying to process accepts...")
        r = await http.get('https://interview.starfallmc.space/pending/accept')
        r.raise_for_status()
        r = r.json()
        for entry in r:
            minecraft_ok = entry['minecraft_ok']
            interview_chan = client.get_channel(entry['channel_id'])
            if interview_chan is None:
                await modmail_chan.send(f"@everyone Tried to get channel ID={entry['channel_id']} <#{entry['channel_id']}> in order to accept user ID={entry['user_id']} <@{entry['user_id']}>, but could not find this channel! Please fix this manually!", allowed_mentions=discord.AllowedMentions.all())


            # First, find the member and try to apply the accept role to them.
            # If there is no member, send a mod mail, but also delete the pending record.
            member = await guild.fetch_member(entry['user_id'])
            if member is None:
                await modmail_chan.send(f"@everyone Tried to assign accept role to <@{entry['user_id']}>, but could not find them in the server! They may have left. If not, please fix this manually!", allowed_mentions=discord.AllowedMentions.all())
                del_resp = await http.delete(f"https://interview.starfallmc.space/pending/accept/{entry['channel_id']}")
                del_resp.raise_for_status()
                continue

            accept_role = int(get_prop('accept-role'))
            try:
                await member.add_roles(discord.Object(accept_role))
            except Exception as e:
                await modmail_chan.send(f"@everyone Tried to give accept role to user <@{entry['user_id']}>, but failed: `{repr(e)}`\n Please fix this manually!", allowed_mentions=discord.AllowedMentions.all())
                await interview_chan.send(
                    content='@everyone', allowed_mentions=discord.AllowedMentions.all(),
                    embed=discord.Embed(color=discord.Color.green(), title="Interview accepted with error", description=get_prop("interview-accept-role-error"))
                )
                if not minecraft_ok:
                    await interview_chan.send(
                        content='@everyone', allowed_mentions=discord.AllowedMentions.all(),
                        embed=discord.Embed(color=discord.Color.yellow(), title="Interview accepted with Minecraft error", description=get_prop("interview-accept-minecraft-error"))
                    )

                del_resp = await http.delete(f"https://interview.starfallmc.space/pending/accept/{entry['channel_id']}")
                del_resp.raise_for_status()
                continue
            
            # Now that we have granted the role, we need to send the accept message.
            if not minecraft_ok:
                await interview_chan.send(
                    content='@everyone', allowed_mentions=discord.AllowedMentions.all(),
                    embed=discord.Embed(color=discord.Color.yellow(), title="Interview accepted with Minecraft error", description=get_prop("interview-accept-minecraft-error"))
                )
            else:
                await interview_chan.send(
                    content=f'<@{entry["user_id"]}>', allowed_mentions=discord.AllowedMentions.all(),
                    embed=discord.Embed(color=discord.Color.green(), title="Interview accepted", description=get_prop("interview-accept"))
                )
            await modmail_chan.send(f"Successfully accepted <@{entry['user_id']}>. The interview will remain available for future reference at: https://interview.starfallmc.space/{entry['channel_id']}/{entry['token']}", allowed_mentions=discord.AllowedMentions.all())
            del_resp = await http.delete(f"https://interview.starfallmc.space/pending/accept/{entry['channel_id']}")
            del_resp.raise_for_status()


        ######

        #await modmail_chan.send(f"Trying to process rejects...")
        r = await http.get('https://interview.starfallmc.space/pending/reject')
        r.raise_for_status()
        r = r.json()
        for entry in r:
            interview_chan = client.get_channel(entry['channel_id'])
            if interview_chan is None:
                await modmail_chan.send(f"@everyone Tried to get channel ID={entry['channel_id']} <#{entry['channel_id']}> in order to reject user ID={entry['user_id']} <@{entry['user_id']}>, but could not find this channel! Please fix this manually!", allowed_mentions=discord.AllowedMentions.all())
            
            await interview_chan.send(
                content=f'<@{entry["user_id"]}>', allowed_mentions=discord.AllowedMentions.all(),
                embed=discord.Embed(color=discord.Color.red(), title="Interview rejected", description=get_prop("interview-reject").replace('{{reason}}', entry['reason']))
            )
            await modmail_chan.send(f"Successfully rejected <@{entry['user_id']}>. The interview will remain available for future reference at: https://interview.starfallmc.space/{entry['channel_id']}/{entry['token']}", allowed_mentions=discord.AllowedMentions.all())
            del_resp = await http.delete(f"https://interview.starfallmc.space/pending/reject/{entry['channel_id']}")
            del_resp.raise_for_status()

    except Exception as e:
        await modmail_chan.send(f"ERROR while fetching accepts/rejects: {repr(e)}\n<@495297618763579402>", allowed_mentions=discord.AllowedMentions.all())
        traceback.print_exc()
        raise e

@process_accepts_rejects.before_loop
async def before_accepts_rejects():
    print('waiting for bot to be ready before accepts_rejects...')
    await client.wait_until_ready()
    print("Ready, now working on modmail!")


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    await modmail_chan.send(f"Interview Manager Discord bot is now running, version 9")

    process_modmail.add_exception_type(Exception)
    process_modmail.start()
    
    process_accepts_rejects.add_exception_type(Exception)
    process_accepts_rejects.start()


@client.event
async def on_raw_member_remove(payload: discord.RawMemberRemoveEvent):
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    while 1:
        try:
            r = await http.delete(f"https://interview.starfallmc.space/status/member/{payload.user.id}")
            r.raise_for_status()
            return
        except Exception as e:
            await modmail_chan.send(f"<@495297618763579402> Cannot send backend notification that <@{payload.user.id}> left: {e}")
            await asyncio.sleep(60)

@client.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    while 1:
        try:
            r = await http.delete(f"https://interview.starfallmc.space/status/channel/{channel.id}")
            r.raise_for_status()
            return
        except Exception as e:
            await modmail_chan.send(f"<@495297618763579402> Cannot send backend notification that channel {channel} <#{channel.id}> was deleted: {e}")
            await asyncio.sleep(60)



if __name__ == '__main__':
    client.run(token)