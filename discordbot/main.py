import asyncio
import discord
import os
import re
import traceback
from discord.ext import tasks

import common
from common import *
import commands

token = os.getenv('DISCORD_TOKEN')


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
common.client = client  # Must be done before commands.attach!

app_commands = discord.app_commands.CommandTree(client)

commands.attach(app_commands)

async def prepare_interview(message: discord.Message):
    j = {
        'user_id': message.author.id,
        'user_name': message.author.name,
        'channel_id': message.channel.id
    }
    async with message.channel.typing():
        r = await http.post("https://interview.starfallmc.space/new", json=j)
    if r.status_code != 200:
        await message.reply(f'There was an internal error while setting up your interview: POST /new returned code {r.status_code} and text: `{r.text[:1000]}`\n\n<@495297618763579402> needs to fix this.\n\nPlease try again, or contact a moderator to proceed with your interview.')
        return
    
    resp = r.json()
    print(resp)
    if resp['state'] == 'new':
        try:
            await message.author.send(get_prop('interview-dm-prompt').replace('{{url}}', resp['edit_url']))
        except:
            traceback.print_exc()
            await message.reply(get_prop('interview-created-dm-error-chat-prompt'))
            if resp['has_old_interviews']:
                embed = discord.Embed(color=discord.Color.dark_green(), title='Old interviews detected', 
                    description=get_prop('has-old-interviews-prompt'))
                await message.reply(embed=embed)
        else:
            await message.reply(get_prop('interview-created-chat-prompt'))
            if resp['has_old_interviews']:
                embed = discord.Embed(color=discord.Color.dark_green(), title='Old interviews detected', 
                    description=get_prop('has-old-interviews-prompt'))
                await message.reply(embed=embed)
        finally:
            interview_chan = message.channel
            number_part = interview_chan.name.split('-')[-1]
            await interview_chan.edit(name=f'user-is-filling-{number_part}', reason='Interview manager channel status')
    else:
        try:
            await message.author.send(get_prop('interview-dm-prompt').replace('{{url}}', resp['edit_url']))
        except:
            traceback.print_exc()
        await message.reply(get_prop('interview-resend-chat'))


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    # Check that the message is in a channel of the matching name
    if re.fullmatch(get_prop('verify-activation-channel-regex'), message.channel.name) is None:
        return
    
    # Check that the activation phrase is used
    if message.content.strip().lower() == get_prop('verify-activation-phrase'):
        return await prepare_interview(message)
    
    # If it's not that, then check for whether the message contains a valid interview URL
    url_match = re.search("https://interview.starfallmc.space/([0-9]+)/([0-9a-zA-Z]+)", message.content.strip())
    if url_match is not None:
        return await perform_migration(message, int(url_match.group(1)), url_match.group(2))
    

async def perform_migration(message: discord.Message, interview_id: int, token: str):
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    async with message.channel.typing():
        j = {
            'old_id': interview_id,
            'old_edit_token': token,
            'new_id': message.channel.id
        }
        r = await http.post("https://interview.starfallmc.space/interview/migrate", json=j)

        if r.status_code != 200:
            await message.reply("Sorry, there was an unexpected error while migrating your interview. An admin has been notified. Please try again, or copy the info from your old interview manually.")
            await modmail_chan.send(f"<@495297618763579402> POST /migrate returned code {r.status_code} and text: `{r.text[:1000]}`")
            return
        
        resp = r.json()
        if resp['status'] == 'err':
            r = resp['reason']
            msg = f'An unexpected error happened. Its internal name is: `{r}`. Please contact an admin and tell them to fix this.'
            if r == 'same_id':
                msg = 'You pasted a link that seems to point to this interview, not a different one. Make sure you copied the correct link.'
            elif r == 'old_interview_invalid':
                msg = "The link you provided doesn't seem to point to a valid interview. Please make sure that you copied the correct link."
            elif r == 'new_interview_already_sent':
                msg = 'This interview has already been submitted, and because of this you cannot edit it or migrate old interviews into it.'
            elif r == 'missing_old_interview':
                msg = "The link you provided doesn't seem to point to a valid interview. Please make sure that you copied the correct link."
            elif r == 'missing_new_interview':
                msg = "It seems that there is no active interview in this channel. You may want to start one before attempting a migration."
            elif r == 'old_interview_no_verdict':
                msg = "The interview at the link has doesn't have a verdict yet. You can only migrate interviews that have a verdict. Please wait until a verdict is set by a moderator."
            elif r == 'owner_not_same':
                msg = "You can only migrate an interview that you have created. Please make sure that you copied the correct link."

            embed = discord.Embed(color=discord.Color.red(), title='Error while migrating interview', description=msg)
            await message.reply(embed=embed)
            return
        
        missing_migrations = resp['missing_migrations']
        ok_migrations = resp['ok_migrations']


        if ok_migrations == 0:
            embed = discord.Embed(color=discord.Color.red(), title='Migration didn\'t do anything', description="You have requested a migration, but the interview questions have changed so much that there's nothing to migrate. You will need to fill the form from scratch.")
        elif missing_migrations == 0:
            embed = discord.Embed(color=discord.Color.green(), title='Migration OK', description=f"Your interview was migrated successfully. Your answers to the questions were copied, and you can now continue editing them.")
        else:
            embed = discord.Embed(color=discord.Color.yellow(), title='Migration partially succeeded', description=f"Some questions have changed since the previous interview. We successfully copied {ok_migrations} answers, but couldn't copy {missing_migrations} others. You can manually review them and edit the new interview.")

        await message.reply(embed=embed)



def split_modmail_text(text):
    while len(text) > 2000:
        first = text[:2000]
        yield first
        text = text[2000:]
    yield text

@tasks.loop(seconds=15)
async def process_modmail():
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    #await modmail_chan.send(f"Trying to process modmail...")
    try:
        r = await http.get('https://interview.starfallmc.space/modmail')
        r.raise_for_status()
        r = r.json()
        for entry in r:
            for piece in split_modmail_text(entry['content']):
                await modmail_chan.send(piece, allowed_mentions=discord.AllowedMentions.all())
            del_resp = await http.delete(f"https://interview.starfallmc.space/modmail/{entry['id']}")
            del_resp.raise_for_status()
    except Exception as e:
        await modmail_chan.send(f"ERROR while processing modmail: {repr(e)}\n<@495297618763579402>", allowed_mentions=discord.AllowedMentions.all())
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

            number_part = interview_chan.name.split('-')[-1]
            await interview_chan.edit(name=f'accepted-{number_part}', reason='Interview manager channel status')

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
            
            number_part = interview_chan.name.split('-')[-1]
            await interview_chan.edit(name=f'rejected-{number_part}', reason='Interview manager channel status')

            await interview_chan.send(
                content=f'<@{entry["user_id"]}>', allowed_mentions=discord.AllowedMentions.all(),
                embed=discord.Embed(color=discord.Color.red(), title="Interview rejected", description=get_prop("interview-reject").replace('{{reason}}', entry['reason']))
            )

            if entry['offer_try_again']:
                await interview_chan.send(
                    embed=discord.Embed(color=discord.Color.dark_green(), title="You can try again", description=get_prop("interview-reject-try-again"))
                )

            await modmail_chan.send(f"Successfully rejected <@{entry['user_id']}>. The interview will remain available for future reference at: https://interview.starfallmc.space/{entry['channel_id']}/{entry['token']}", allowed_mentions=discord.AllowedMentions.all())
            del_resp = await http.delete(f"https://interview.starfallmc.space/pending/reject/{entry['channel_id']}")
            del_resp.raise_for_status()

    except Exception as e:
        await modmail_chan.send(f"ERROR while processing accepts/rejects: {repr(e)}\n<@495297618763579402>", allowed_mentions=discord.AllowedMentions.all())
        traceback.print_exc()
        raise e

@process_accepts_rejects.before_loop
async def before_accepts_rejects():
    print('waiting for bot to be ready before accepts_rejects...')
    await client.wait_until_ready()
    print("Ready, now working on accepts_rejects!")


@tasks.loop(seconds=17)
async def process_notifies():
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    try:
        r = await http.get('https://interview.starfallmc.space/pending/notify')
        r.raise_for_status()
        r = r.json()
        for entry in r:
            interview_chan = client.get_channel(entry['channel_id'])
            if interview_chan is None:
                await modmail_chan.send(f"<@495297618763579402> Tried to get channel ID={entry['channel_id']} <#{entry['channel_id']}> in order to accept user ID={entry['user_id']} <@{entry['user_id']}>, but could not find this channel! Please fix this manually!", allowed_mentions=discord.AllowedMentions.all())
                continue
            
            number_part = interview_chan.name.split('-')[-1]
            await interview_chan.edit(name=f'waiting-for-mod-{number_part}', reason='Interview manager channel status')
            embed = discord.Embed(color=discord.Color.dark_green(), title='Interview received', description=get_prop('interview-submit'))
            try:
                await interview_chan.send(content=f'<@{entry["user_id"]}>', embed=embed, allowed_mentions=discord.AllowedMentions.all())
            except Exception as e:
                await modmail_chan.send(f"<@495297618763579402> Tried to send interview-recv notification to channel ID={entry['channel_id']} <#{entry['channel_id']}> but couldn't: {e}", allowed_mentions=discord.AllowedMentions.all())
                continue

            del_resp = await http.delete(f"https://interview.starfallmc.space/pending/notify/{entry['channel_id']}")
            del_resp.raise_for_status()

    except Exception as e:
        await modmail_chan.send(f"ERROR while processing completion notifications: {repr(e)}\n<@495297618763579402>", allowed_mentions=discord.AllowedMentions.all())
        traceback.print_exc()
        raise e


@process_notifies.before_loop
async def before_accepts_rejects():
    print('waiting for bot to be ready before notifies...')
    await client.wait_until_ready()
    print("Ready, now working on notifies!")


@tasks.loop(hours=1)
async def sync_banned_role():
    # Loop over all the channels in the guild and check if the banned role has write access;
    # if yes, edit it to no.
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    guild = modmail_chan.guild
    ban_role_id = int(get_prop('banned-role'))

    try:
        ban_role = guild.get_role(ban_role_id)
        change_count = 0
        for chan in guild.channels:
            overwrites = chan.overwrites_for(ban_role)
            perms = chan.permissions_for(ban_role)
            changed = False
            if perms.send_messages:
                overwrites.send_messages = False
                changed = True
            if perms.send_messages_in_threads:
                overwrites.send_messages_in_threads = False
                changed = True
            if changed:
                await chan.set_permissions(ban_role, overwrite=overwrites, reason="syncing ban role permissions")
                if change_count == 0:
                    await modmail_chan.send("Detected channel with wrong banned role permissions, syncing...")
                change_count += 1
        
        if change_count:
            await modmail_chan.send(f"Permission sync completed, {change_count} channels changed")

    except Exception as e:
        await modmail_chan.send(f"ERROR while syncing ban role <@&{ban_role_id}>: {repr(e)}\n<@495297618763579402>", allowed_mentions=discord.AllowedMentions(users=True))
        traceback.print_exc()
        raise e
        

@tasks.loop(minutes=30)
async def sync_member_list():
    # Collect a list of all active members of the guild, then send it to the server to handle.
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    guild = modmail_chan.guild

    try:
        members = []
        async for member in guild.fetch_members():
            members.append(member.id)

        status_resp = await http.post(f"https://interview.starfallmc.space/status/full-members", json=members)
        status_resp.raise_for_status()

    except Exception as e:
        await modmail_chan.send(f"ERROR while syncing full member list: {repr(e)}\n<@495297618763579402>", allowed_mentions=discord.AllowedMentions(users=True))
        traceback.print_exc()
        raise e



@sync_banned_role.before_loop
async def before_sync_ban():
    print('waiting for bot to be ready before sync ban role...')
    await client.wait_until_ready()
    print("Ready, now working on sync ban role!")


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    modmail_chan = client.get_channel(int(get_prop('modmail-channel')))
    await modmail_chan.send(f"Interview Manager Discord bot is now running, version 14.2")

    await app_commands.sync()

    process_modmail.add_exception_type(Exception)
    process_modmail.start()
    
    process_accepts_rejects.add_exception_type(Exception)
    process_accepts_rejects.start()

    process_notifies.add_exception_type(Exception)
    process_notifies.start()
    
    sync_banned_role.add_exception_type(Exception)
    sync_banned_role.start()




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