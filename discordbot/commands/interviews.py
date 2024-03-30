import discord
from discord import app_commands
from common import http, get_prop
import common

@app_commands.context_menu(name="View user's interview")
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def get_interview_ctx_command(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(thinking=True, ephemeral=True)
    modmail_chan = common.client.get_channel(int(get_prop('modmail-channel')))
    try:
        resp = await http.get(f"https://interview.starfallmc.space/interviews/by-user/{user.id}")
        resp.raise_for_status()
        data = resp.json()
        if len(data) == 0:
            await interaction.followup.send(f"There are no interviews associated with <@{user.id}>.")
        elif len(data) == 1:
            await interaction.followup.send(f"<@{user.id}>'s interview can be viewed at: {data[0]['url']}")
        else:
            interview_list_str = '\n'.join(map(lambda x: f'- {x["url"]}', data))
            await interaction.followup.send(f"<@{user.id}> has {len(data)} interviews:\n" + interview_list_str)
    except Exception as e:
        await modmail_chan.send(f"<@495297618763579402> Error in `get_interview_ctx_command()` HTTP interaction: {e}", allowed_mentions=discord.AllowedMentions.all())
        await interaction.followup.send("There was an error with the command. The bot owner was notified.")
