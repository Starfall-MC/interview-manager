import traceback
import uuid
import discord
from discord import app_commands
from common import http, get_prop
import common

class AlterMinecraftUsername(discord.ui.Modal):
    old_name = discord.ui.TextInput(label="Old username (for reference)")
    new_name = discord.ui.TextInput(label="New username", required=True)

    def __init__(self, *, custom_id: str, old: str = "???") -> None:
        super().__init__(title="Change Minecraft username", timeout=None, custom_id=custom_id)
        self.old_name.default = old

    async def on_submit(self, interaction: discord.Interaction):
        modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))

        id = int(self.custom_id.split(':')[0])
        if not self.new_name.value:
            await interaction.response.send_message("The new name cannot be empty.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True, thinking=True)

        new_name = self.new_name.value
        try:
            resp = await http.post(f"https://interview.starfallmc.space/minecraft/discord-to-name/{id}", json={'name': new_name})
            resp.raise_for_status()
            data = resp.json()
            if data['status'] == 'ok':
                did_update = ''
                if data['did_update_whitelist']:
                    did_update = 'Ideal Minecraft whitelist was affected; run the update command to apply it immediately.'
                await interaction.followup.send(f"Name updated OK: old name was `{data['old_name'] or '[unset]'}`, new name is `{data['new_name']}`. " + did_update)
                return
            elif data['status'] == 'err' and data['reason'] == 'name_collision_in_username':
                await interaction.followup.send(f"Cannot set this Minecraft username because some other user is already named `{new_name}`.")
                return
            elif data['status'] == 'err' and data['reason'] == 'name_collision_in_whitelist':
                await interaction.followup.send(f"Cannot set this Minecraft username because this user is whitelisted, but the new name `{new_name}` is also whitelisted. If you added the new name to the whitelist manually, unwhitelist it before continuing.")
                return
            else:
                await modmail_chan.send(f"<@495297618763579402> In `SetMinecraftUsername.on_submit()` got unexpected data: `{data}`", allowed_mentions=discord.AllowedMentions.all())
                await interaction.followup.send("There was an error with the data from the server. The bot owner was notified.")
                return
        except Exception as e:
            traceback.print_exc()
            await modmail_chan.send(f"<@495297618763579402> Error in `SetMinecraftUsername.on_submit()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
            await interaction.followup.send("Error while submitting form. The bot owner has been notified.")


class SetMinecraftUsername(discord.ui.Modal, title="Set Minecraft username"):
    new_name = discord.ui.TextInput(label="New username", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))

        id = int(self.custom_id.split(':')[0])
        if not self.new_name.value:
            await interaction.response.send_message("The new name cannot be empty.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True, thinking=True)

        new_name = self.new_name.value
        try:
            resp = await http.post(f"https://interview.starfallmc.space/minecraft/discord-to-name/{id}", json={'name': new_name})
            resp.raise_for_status()
            data = resp.json()
            if data['status'] == 'ok':
                did_update = ''
                if data['did_update_whitelist']:
                    did_update = 'Ideal Minecraft whitelist was affected; run the update command to apply it immediately.'
                await interaction.followup.send(f"Name updated OK: old name was `{data['old_name'] or '[unset]'}`, new name is `{data['new_name']}`. " + did_update)
                return
            elif data['status'] == 'err' and data['reason'] == 'name_collision_in_username':
                await interaction.followup.send(f"Cannot set this Minecraft username because some other user is already named `{new_name}`.")
                return
            elif data['status'] == 'err' and data['reason'] == 'name_collision_in_whitelist':
                await interaction.followup.send(f"Cannot set this Minecraft username because this user is whitelisted, but the new name `{new_name}` is also whitelisted. If you added the new name to the whitelist manually, unwhitelist it before continuing.")
                return
            else:
                await modmail_chan.send(f"<@495297618763579402> In `SetMinecraftUsername.on_submit()` got unexpected data: `{data}`", allowed_mentions=discord.AllowedMentions.all())
                await interaction.followup.send("There was an error with the data from the server. The bot owner was notified.")
                return
        except Exception as e:
            traceback.print_exc()
            await modmail_chan.send(f"<@495297618763579402> Error in `SetMinecraftUsername.on_submit()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
            await interaction.followup.send("Error while submitting form. The bot owner has been notified.")


@app_commands.context_menu(name="Update Minecraft username")
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def update_mc_username_ctx_command(interaction: discord.Interaction, user: discord.Member):
    modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))
    try:
        resp = await http.get(f"https://interview.starfallmc.space/minecraft/discord-to-name/{user.id}")
        resp.raise_for_status()
        data = resp.json()
        if data['status'] == 'missing':
            await interaction.response.send_modal(SetMinecraftUsername(custom_id=str(user.id)+':'+str(uuid.uuid4())))
        elif data['status'] == 'ok':
            m = AlterMinecraftUsername(custom_id=str(user.id)+':'+str(uuid.uuid4()))
            m.old_name.default = data['name']
            await interaction.response.send_modal(m)
        else:
            await modmail_chan.send(f"<@495297618763579402> In `update_mc_username_ctx_command()` got unexpected data: `{data}`", allowed_mentions=discord.AllowedMentions.all())
    except Exception as e:
        traceback.print_exc()
        await modmail_chan.send(f"<@495297618763579402> Error in `update_mc_username_ctx_command()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.response.send_message("There was an error with the command. The bot owner was notified.", ephemeral=True)



@app_commands.context_menu(name="Get Minecraft username")
@app_commands.guild_only()
async def get_mc_name_ctx_command(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(thinking=True, ephemeral=True)
    modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))
    try:
        resp = await http.get(f"https://interview.starfallmc.space/minecraft/discord-to-name/{user.id}")
        resp.raise_for_status()
        data = resp.json()
        if data['status'] == 'ok':
            await interaction.followup.send(f"<@{user.id}> has Minecraft username: `{data['name']}`")
        elif data['status'] == 'missing':
            await interaction.followup.send(f"We don't know <@{user.id}>'s Minecraft username yet.")
        else:
            await modmail_chan.send(f"<@495297618763579402> In `get_mc_name_ctx_command()` got unexpected data: `{data}`", allowed_mentions=discord.AllowedMentions.all())
            await interaction.followup.send("There was an error with the command. The bot owner was notified.")

    except Exception as e:
        traceback.print_exc()
        await modmail_chan.send(f"<@495297618763579402> Error in `get_mc_name_ctx_command()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.followup.send("There was an error with the command. The bot owner was notified.")

@app_commands.command(name="mctodiscord", description="Find a user's Discord name from their Minecraft name")
@app_commands.guild_only()
async def get_discord_name_command(interaction: discord.Interaction, mcname: str):
    await interaction.response.defer(thinking=True, ephemeral=True)
    modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))
    try:
        resp = await http.get(f"https://interview.starfallmc.space/minecraft/name-to-discord/{mcname}")
        resp.raise_for_status()
        data = resp.json()
        if data['status'] == 'ok':
            await interaction.followup.send(f"`{mcname}` is <@{data['id']}>.")
        elif data['status'] == 'missing':
            await interaction.followup.send(f"We don't know who `{mcname}` is yet.")
        else:
            await modmail_chan.send(f"<@495297618763579402> In `get_discord_name_command()` got unexpected data: `{data}`", allowed_mentions=discord.AllowedMentions.all())
            await interaction.followup.send("There was an error with the command. The bot owner was notified.")

    except Exception as e:
        traceback.print_exc()
        await modmail_chan.send(f"<@495297618763579402> Error in `get_discord_name_command()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.followup.send("There was an error with the command. The bot owner was notified.")

