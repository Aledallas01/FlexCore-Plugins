import discord
import asyncio

async def delete_ticket(interaction: discord.Interaction, bot, db, config, confirmed: bool = False, reason: str = None):
    """
    Deletes the ticket channel.
    """
    channel = interaction.channel
    
    # Check if this is a ticket channel
    ticket = db.get_ticket_by_channel(channel.id)
    if not ticket:
        await interaction.response.send_message("❌ This is not a ticket channel.", ephemeral=True)
        return

    if not confirmed:
        return

    embed_color_hex = config.get("embed_colors", {}).get("deleted", "#000000")
    embed_color = int(embed_color_hex.replace("#", ""), 16)
    
    description = "Deleting ticket in 5 seconds..."
    if reason:
        description = f"**Reason:** {reason}\n\n" + description
        
    embed = discord.Embed(description=description, color=embed_color)
    
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=embed, ephemeral=False)
    else:
        await interaction.followup.send(embed=embed)
        
    await asyncio.sleep(5)
    
    await channel.delete()
