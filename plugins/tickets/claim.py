import discord
from .views import TicketControlsView

async def claim_ticket(interaction: discord.Interaction, bot, db, config):
    """
    Claims the ticket for the user.
    """
    channel = interaction.channel
    user = interaction.user
    
    # Check if this is a ticket channel
    ticket = db.get_ticket_by_channel(channel.id)
    if not ticket:
        await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
        return
        
    if ticket['claimed_by']:
        claimer = interaction.guild.get_member(ticket['claimed_by'])
        name = claimer.display_name if claimer else "Unknown"
        await interaction.response.send_message(f"❌ This ticket is already claimed by {name}.", ephemeral=True)
        return

    # Update DB
    db.claim_ticket(channel.id, user.id)
    
    embed_color_hex = config.get("embed_colors", {}).get("claimed", "#0000FF")
    embed_color = int(embed_color_hex.replace("#", ""), 16)
    
    embed = discord.Embed(description=f"✅ Ticket claimed by {user.mention}", color=embed_color)
    await channel.send(embed=embed)
    
    # Update the view to disable the claim button
    view = TicketControlsView(claimed=True)
    await interaction.message.edit(view=view)
    
    await interaction.response.send_message("✅ Ticket claimed.", ephemeral=True)
