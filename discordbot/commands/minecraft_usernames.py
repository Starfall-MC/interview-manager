import discord
from discord import app_commands
from common import http, get_prop
import common

@app_commands.context_menu(name="Update Minecraft username")
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def update_mc_username_ctx_command(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message("To be implemented...", ephemeral=True)


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
            await interaction.followup.send(f"<@{user.id}> has Minecraft username: {data['name']}")
        elif data['status'] == 'missing':
            await interaction.followup.send(f"We don't know <@{user.id}>'s Minecraft username yet.")
        else:
            await modmail_chan.send(f"<@495297618763579402> In `get_mc_name_ctx_command()` got unexpected data: `{data}`", allowed_mentions=discord.AllowedMentions.all())
    except Exception as e:
        await modmail_chan.send(f"<@495297618763579402> Error in `get_mc_name_ctx_command()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.followup.send("There was an error with the command. The bot owner was notified.")
