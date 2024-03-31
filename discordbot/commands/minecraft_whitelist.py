import traceback
import uuid
import discord
from discord import app_commands
from discord.utils import MISSING
from common import http, get_prop
import common

@app_commands.command(name="reify", description="Apply any pending changes to the whitelist")
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def reify_whitelist_cmd(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))
    try:
        resp = await http.post("https://interview.starfallmc.space/minecraft/ideal-whitelist/reify")
        resp.raise_for_status()
        data = resp.json()
        if len(data) == 0:
            await interaction.followup.send(f"Reification required no actions.")
        else:
            reify_actions = ' '.join(map(lambda x: f'`{x[1]} {x[0]}`', data))
            await interaction.followup.send(f"Reification caused these commands: " + reify_actions)
    except Exception as e:
        traceback.print_exc()
        await modmail_chan.send(f"<@495297618763579402> Error in `reify_whitelist_cmd()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.followup.send("There was an error with the command. The bot owner was notified.")

@app_commands.command(name="rawaddwhitelist", description="Low-level command to add a name directly to the ideal whitelist")
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def raw_add_whitelist_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))
    try:
        resp = await http.put(f"https://interview.starfallmc.space/minecraft/ideal-whitelist/{name}")
        resp.raise_for_status()
        data = resp.json()
        if data['status'] == 'ok':
            await interaction.followup.send(f"Minecraft username `{name}` successfully added to list; run `/reify` now to apply it immediately.")
        elif data['status'] == 'already':
            await interaction.followup.send(f"Minecraft username `{name}` was already in ideal whitelist.")
        else:
            await modmail_chan.send(f"<@495297618763579402> `raw_add_whitelist_cmd()` got unknown data: `{data}`", allowed_mentions=discord.AllowedMentions.all())
            await interaction.followup.send("There was an error with the command. The bot owner was notified.")

    except Exception as e:
        traceback.print_exc()
        await modmail_chan.send(f"<@495297618763579402> Error in `raw_add_whitelist_cmd()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.followup.send("There was an error with the command. The bot owner was notified.")

@app_commands.command(name="rawdelwhitelist", description="Low-level command to add a name directly to the ideal whitelist")
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def raw_del_whitelist_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))
    try:
        resp = await http.delete(f"https://interview.starfallmc.space/minecraft/ideal-whitelist/{name}")
        resp.raise_for_status()
        data = resp.json()
        if data['status'] == 'ok':
            await interaction.followup.send(f"Minecraft username `{name}` successfully deleted from list; run `/reify` now to apply it immediately.")
        elif data['status'] == 'already':
            await interaction.followup.send(f"Minecraft username `{name}` was already in ideal whitelist.")
        else:
            await modmail_chan.send(f"<@495297618763579402> `raw_del_whitelist_cmd()` got unknown data: `{data}`", allowed_mentions=discord.AllowedMentions.all())
            await interaction.followup.send("There was an error with the command. The bot owner was notified.")
    
    except Exception as e:
        traceback.print_exc()
        await modmail_chan.send(f"<@495297618763579402> Error in `raw_del_whitelist_cmd()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.followup.send("There was an error with the command. The bot owner was notified.")


@app_commands.command(name="whitelist", description="Whitelist a Minecraft username by associating it with a Discord user")
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def advanced_whitelist_cmd(interaction: discord.Interaction, who: discord.Member, mc_name: str):
    await interaction.response.defer(thinking=True)
    modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))
    step = 'checking for existing Minecraft name for user'
    try:
        # First check for whether this username is already recorded.
        resp = await http.get(f"https://interview.starfallmc.space/minecraft/discord-to-name/{who.id}")
        resp.raise_for_status()
        data = resp.json()
        existing_name = data.get('name')
        if existing_name is not None and existing_name.lower() != mc_name.lower():
            await interaction.followup.send(f"Our records show that <@{who.id}> has Minecraft username `{existing_name}`, which is not the same as `{mc_name}`. Please resolve this manually, then try again.")

        # If we don't have the name, patch it.
        step = 'recording missing Minecraft name'
        resp = await http.post(f"https://interview.starfallmc.space/minecraft/discord-to-name/{who.id}", json={'name': mc_name})
        resp.raise_for_status()
        data = resp.json()
        if data['status'] != 'ok':
            raise ValueError("Unexpected status for POST discord-to-name: "+ str(data))

        # Now add that name to the ideal whitelist.
        step = 'adding Minecraft name to ideal whitelist'
        resp = await http.put(f"https://interview.starfallmc.space/minecraft/ideal-whitelist/{mc_name}")
        resp.raise_for_status()

        # Finally, request a reification.
        step = 'reifying ideal whitelist'
        resp = await http.post("https://interview.starfallmc.space/minecraft/ideal-whitelist/reify")
        resp.raise_for_status()
        data = resp.json()
        mapped_data = list(map(lambda x: (x[0].lower(), x[1].lower()), data))

        if data == []:
            await interaction.followup.send(f"`{mc_name}` already whitelisted, but we have recorded that it belongs to <@{who.id}>")
        elif mapped_data != [(mc_name.lower(), '+')]:
            reify_actions = ' '.join(map(lambda x: f'`{x[1]} {x[0]}`', data))
            await interaction.followup.send(f"Whitelist appears successful, but reification actionset is unexpected: {reify_actions}\nCheck whether the whitelisting was done OK manually.")
        else:
            await interaction.followup.send(f"`{mc_name}` successfully set as belonging to <@{who.id}>, added to ideal whitelist, reified")

    except Exception as e:
        traceback.print_exc()
        await modmail_chan.send(f"<@495297618763579402> Error in `advanced_whitelist_cmd()` HTTP interaction during step `{step}`: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.followup.send(f"There was an error with the command: the step that failed was `{step}`. The bot owner was notified.")
