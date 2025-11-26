import discord
from discord.ui import View, Select, Button, Modal, TextInput
from typing import Optional, List, Dict

class TicketPanelView(View):
    def __init__(self, categories: List[Dict]):
        super().__init__(timeout=None)
        self.add_item(TicketCategorySelect(categories))

class TicketCategorySelect(Select):
    def __init__(self, categories: List[Dict]):
        options = []
        for cat in categories:
            options.append(discord.SelectOption(
                label=cat.get("name", "Unknown"),
                description=cat.get("description", ""),
                value=cat.get("name"), # Use name as ID for simplicity
                emoji=cat.get("emoji")
            ))
        
        super().__init__(
            placeholder="Select a category to open a ticket...",
            min_values=1,
            max_values=1,
            custom_id="ticket_category_select"
        )

    async def callback(self, interaction: discord.Interaction):
        # This will be handled by the main listener or we can import the create logic
        # To avoid circular imports, we'll rely on the custom_id "ticket_category_select"
        # being handled in the Cog or we can defer here.
        # Actually, for the best UX, we should handle it here if possible, but we need the bot/db/config.
        # For now, we defer and let the Cog listener pick it up, OR we can attach the callback in the Cog.
        # But wait, persistent views need to be registered in `setup_hook` or `cog_load`.
        # If we use custom_id, the Cog listener `on_interaction` is the best place.
        await interaction.response.defer()

class TicketControlsView(View):
    def __init__(self, claimed: bool = False):
        super().__init__(timeout=None)
        self.claimed = claimed
        
        # Claim Button
        self.add_item(Button(
            label="Claim", 
            style=discord.ButtonStyle.success, 
            custom_id="ticket_claim", 
            emoji="🙋‍♂️",
            disabled=claimed
        ))
        
        # Close Button
        self.add_item(Button(
            label="Close", 
            style=discord.ButtonStyle.danger, 
            custom_id="ticket_close", 
            emoji="🔒"
        ))
        
        # Delete Button
        self.add_item(Button(
            label="Delete", 
            style=discord.ButtonStyle.secondary, 
            custom_id="ticket_delete", 
            emoji="🗑️"
        ))

class ConfirmationView(View):
    def __init__(self, action: str):
        super().__init__(timeout=None)
        self.action = action # "close" or "delete"
        
        self.add_item(Button(
            label="Yes", 
            style=discord.ButtonStyle.danger, 
            custom_id=f"ticket_confirm_{action}", 
            emoji="✅"
        ))
        
        self.add_item(Button(
            label="No", 
            style=discord.ButtonStyle.secondary, 
            custom_id=f"ticket_cancel_{action}", 
            emoji="❌"
        ))
        
        self.add_item(Button(
            label="Reason", 
            style=discord.ButtonStyle.primary, 
            custom_id=f"ticket_reason_{action}", 
            emoji="📝"
        ))

class ReasonModal(Modal):
    def __init__(self, action: str, callback_func):
        super().__init__(title=f"Reason for {action}")
        self.callback_func = callback_func
        self.action = action
        
        self.reason = TextInput(
            label="Reason",
            style=discord.TextStyle.paragraph,
            placeholder="Enter the reason here...",
            required=True,
            max_length=1000
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback_func(interaction, self.reason.value)
