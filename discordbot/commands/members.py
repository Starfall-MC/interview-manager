import traceback
import uuid
import discord
from discord import app_commands
from common import http, get_prop
import common



@app_commands.command(name="sendmemberlist", description="Send current member list to server")
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def manual_send_member_list_command(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True, ephemeral=True)
    modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))
    guild = modmail_chan.guild
    try:
        members = []
        async for member in guild.fetch_members():
            members.append(member.id)

        status_resp = await http.post(f"https://interview.starfallmc.space/status/full-members", json=members)
        status_resp.raise_for_status()

        await interaction.followup.send("Successfully sent current member list to server for syncing.")
    except Exception as e:
        traceback.print_exc()
        await modmail_chan.send(f"<@495297618763579402> Error in `manual_send_member_list_command()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.followup.send_message("There was an error with the command. The bot owner was notified.")
