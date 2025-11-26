import discord
import asyncio
from .views import TicketControlsView

async def close_ticket(interaction: discord.Interaction, bot, db, config, confirmed: bool = False, reason: str = None):
    """
    Closes the current ticket.
    """
    channel = interaction.channel
    guild = interaction.guild
    
    # Check if this is a ticket channel
    ticket = db.get_ticket_by_channel(channel.id)
    if not ticket:
        await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
        return
        
    if ticket['status'] == 'closed':
        await interaction.response.send_message("❌ This ticket is already closed.", ephemeral=True)
        return

    if not confirmed:
        # This path is usually handled by the view switching in tickets.py, 
        # but if called via command, we might need to trigger the view.
        # For now, we assume confirmed=True comes from the button flow.
        return

    # Update DB
    db.close_ticket(channel.id)
    
    # Update permissions (Lock channel)
    user_id = ticket['user_id']
    user = guild.get_member(user_id)
    
    if user:
        await channel.set_permissions(user, read_messages=True, send_messages=False)
    
    # Rename channel
    try:
        await channel.edit(name=f"closed-{ticket['ticket_number']:04d}")
    except:
        pass # Ignore if rename fails
        
    embed_color_hex = config.get("embed_colors", {}).get("closed", "#FF0000")
    embed_color = int(embed_color_hex.replace("#", ""), 16)
    
    description = f"Closed by {interaction.user.mention}"
    if reason:
        description += f"\n**Reason:** {reason}"
        
    embed = discord.Embed(title="Ticket Closed", description=description, color=embed_color)
    
    # Update the controls view to show it's closed (maybe remove buttons or show delete only)
    # The requirement says: "Chiudi: ... invia un embed che dice che il ticket è stato chiuso"
    # It doesn't explicitly say to change the buttons after closing, but usually you want 'Delete' available.
    # We will send the embed and maybe a new view with just Delete.
    
    # Re-using TicketControlsView but maybe we want a specific "Closed" view?
    # For now, let's just send the embed. The previous controls might still be there but 'Close' won't work again.
    # Better: Send a new view with Delete only.
    
    from .views import TicketControlsView # Import here to avoid circular if top-level
    # Actually we can just use a view with Delete.
    # Let's use the TicketControlsView but maybe we can't easily modify it to just Delete without changing the class.
    # We'll just leave the old view or send a new one.
    # Let's send a new view with just Delete.
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Delete", style=discord.ButtonStyle.secondary, custom_id="ticket_delete", emoji="🗑️"))
    
    await channel.send(embed=embed, view=view)
    
    # We should also try to edit the original message to remove the old view if possible, but we don't have the message ID easily.
    # So we just send a new message.
    
    if not interaction.response.is_done():
        await interaction.response.send_message("✅ Ticket closed.", ephemeral=True)
    else:
        # If we came from a modal, we might need to follow up
        try:
            await interaction.followup.send("✅ Ticket closed.", ephemeral=True)
        except:
            pass
