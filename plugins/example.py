"""
FlexCore Example Plugin - Comprehensive Demo

Questo plugin dimostra tutte le funzionalità principali per lo sviluppo di plugin:
- ✅ Sistema di configurazione auto-create & validate
- ✅ Text Commands (prefix-based)
- ✅ Slash Commands (application commands)
- ✅ Event Listeners
- ✅ Error Handling
- ✅ Permessi e controlli

Vedi PLUGINS.md per la documentazione completa.
"""

import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from typing import Optional

class ExampleCog(commands.Cog):
    """Plugin di esempio con tutte le funzionalità"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config_name = "example"
        self.config_path = os.path.join("config", f"{self.config_name}.json")
        
        # Configurazione di default
        self.default_config = {
            "welcome_message": "Benvenuto {user} nel server! 👋",
            "welcome_channel_id": 0,  # 0 = disabilitato
            "admin_role_id": 0,
            "respond_to_hello": True,
            "auto_react": {
                "enabled": False,
                "emoji": "👍"
            }
        }
        
        # Carica e valida la configurazione all'avvio
        self.config = self._load_and_validate_config()
        
        print(f"✅ [Example] Plugin caricato!")
    
    # ==================== CONFIG SYSTEM ====================
    
    def _load_and_validate_config(self):
        """
        Sistema di configurazione completo:
        1. Auto-Create: Crea il file se non esiste
        2. Load: Carica il JSON
        3. Validate & Repair: Controlla e ripara errori
        """
        print(f"🔌 [Example] Verifica configurazione...")

        # 1. Auto-Create Config
        if not os.path.exists(self.config_path):
            print(f"⚙️ [Example] Creazione config in {self.config_path}...")
            try:
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                self._save_config(self.default_config)
                return self.default_config
            except Exception as e:
                print(f"❌ [Example] Errore creazione config: {e}")
                return self.default_config

        # 2. Load Config
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"❌ [Example] Errore caricamento config (JSON corrotto): {e}")
            return self.default_config

        # 3. Validate & Repair Config
        valid = True
        
        # Check top-level keys
        for key, default_val in self.default_config.items():
            if key not in config:
                print(f"⚠️ [Example] Chiave '{key}' mancante, aggiunta default.")
                config[key] = default_val
                valid = False
        
        # Deep check: auto_react
        if "auto_react" in config and isinstance(config["auto_react"], dict):
            for key, val in self.default_config["auto_react"].items():
                if key not in config["auto_react"]:
                    config["auto_react"][key] = val
                    valid = False
        else:
            config["auto_react"] = self.default_config["auto_react"]
            valid = False
        
        # Type checks
        if not isinstance(config.get("enabled"), bool):
            config["enabled"] = True
            valid = False
            
        if not isinstance(config.get("welcome_message"), str):
            config["welcome_message"] = self.default_config["welcome_message"]
            valid = False

        # Save if repaired
        if not valid:
            print(f"🔧 [Example] Configurazione riparata e salvata.")
            self._save_config(config)
        else:
            print(f"✅ [Example] Configurazione caricata e validata.")

        return config

    def _save_config(self, config):
        """Salva la configurazione su file"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    
    # ==================== TEXT COMMANDS ====================
    
    @commands.command(name="ping")
    async def ping_command(self, ctx):
        """Risponde con Pong! (Text Command Base)"""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Latenza: {latency}ms")
    
    @commands.command(name="echo")
    async def echo_command(self, ctx, *, message: str):
        """Ripete un messaggio (Text Command con Argomenti)
        
        Uso: !echo <messaggio>
        """
        await ctx.send(f"🔊 {message}")
    
    @commands.command(name="serverinfo")
    async def serverinfo_command(self, ctx):
        """Mostra informazioni sul server (Text Command con Embed)"""
        guild = ctx.guild
        
        embed = discord.Embed(
            title=f"📊 Info Server: {guild.name}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="🆔 ID", value=guild.id, inline=True)
        embed.add_field(name="👥 Membri", value=guild.member_count, inline=True)
        embed.add_field(name="📅 Creato il", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="👑 Proprietario", value=guild.owner.mention, inline=True)
        embed.add_field(name="💬 Canali", value=len(guild.channels), inline=True)
        embed.add_field(name="🎭 Ruoli", value=len(guild.roles), inline=True)
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        await ctx.send(embed=embed)
    
    @commands.command(name="adminonly")
    @commands.has_permissions(administrator=True)
    async def adminonly_command(self, ctx):
        """Comando riservato agli admin (Text Command con Permessi)"""
        await ctx.send("✅ Sei un admin! Hai accesso a questo comando.")
    
    @adminonly_command.error
    async def adminonly_error(self, ctx, error):
        """Error handler per il comando admin"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Solo gli amministratori possono usare questo comando!")
    
    # ==================== SLASH COMMANDS ====================
    
    @app_commands.command(name="hello", description="Saluta l'utente")
    async def hello_slash(self, interaction: discord.Interaction):
        """Slash Command Base"""
        await interaction.response.send_message(f"👋 Ciao {interaction.user.mention}!")
    
    @app_commands.command(name="userinfo", description="Mostra informazioni su un utente")
    @app_commands.describe(user="L'utente di cui vedere le info (lascia vuoto per vedere le tue)")
    async def userinfo_slash(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Slash Command con Parametro Opzionale"""
        target = user or interaction.user
        
        embed = discord.Embed(
            title=f"👤 Info Utente: {target.name}",
            color=target.color,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="🆔 ID", value=target.id, inline=True)
        embed.add_field(name="📛 Nome", value=target.display_name, inline=True)
        embed.add_field(name="🤖 Bot?", value="Sì" if target.bot else "No", inline=True)
        embed.add_field(name="📅 Account creato", value=target.created_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="📥 Entrato il", value=target.joined_at.strftime("%d/%m/%Y"), inline=True)
        embed.add_field(name="🎭 Ruoli", value=len(target.roles) - 1, inline=True)
        
        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="choose", description="Scegli un'opzione da un menu")
    @app_commands.describe(option="Seleziona un'opzione")
    @app_commands.choices(option=[
        app_commands.Choice(name="🔴 Rosso", value="red"),
        app_commands.Choice(name="🟢 Verde", value="green"),
        app_commands.Choice(name="🔵 Blu", value="blue"),
        app_commands.Choice(name="🟡 Giallo", value="yellow")
    ])
    async def choose_slash(self, interaction: discord.Interaction, option: app_commands.Choice[str]):
        """Slash Command con Choices (Dropdown)"""
        colors = {
            "red": discord.Color.red(),
            "green": discord.Color.green(),
            "blue": discord.Color.blue(),
            "yellow": discord.Color.gold()
        }
        
        embed = discord.Embed(
            title=f"Hai scelto: {option.name}",
            description=f"Valore: `{option.value}`",
            color=colors.get(option.value, discord.Color.default())
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="secret", description="Invia un messaggio segreto (solo tu puoi vederlo)")
    async def secret_slash(self, interaction: discord.Interaction):
        """Slash Command con Risposta Ephemeral"""
        await interaction.response.send_message(
            "🤫 Questo messaggio è visibile solo a te!",
            ephemeral=True
        )
    
    @app_commands.command(name="kick_member", description="Espelle un membro dal server")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(
        member="Il membro da espellere",
        reason="Il motivo dell'espulsione"
    )
    async def kick_slash(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        """Slash Command con Permessi (ESEMPIO - NON ESEGUE REALMENTE)"""
        # Questo è solo un esempio - non esegue realmente il kick
        embed = discord.Embed(
            title="👢 Kick (SIMULATO)",
            description=f"Questo comando kickerebbe {member.mention}\n**Motivo:** {reason or 'Nessun motivo specificato'}",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # ==================== EVENT LISTENERS ====================
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Evento: Nuovo membro entra nel server"""
        if not self.config.get("enabled"):
            return
        
        # Invia messaggio di benvenuto se configurato
        channel_id = self.config.get("welcome_channel_id")
        if channel_id and channel_id != 0:
            channel = member.guild.get_channel(channel_id)
            if channel:
                message = self.config["welcome_message"].format(user=member.mention)
                await channel.send(message)
                print(f"[Example] Messaggio di benvenuto inviato per {member.name}")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Evento: Messaggio inviato in qualsiasi canale"""
        # Ignora i bot
        if message.author.bot:
            return
        
        # Se configurato, risponde a "ciao"
        if self.config.get("respond_to_hello") and "ciao" in message.content.lower():
            await message.channel.send(f"Ciao {message.author.mention}! 👋")
        
        # Auto-react se abilitato
        if self.config.get("auto_react", {}).get("enabled"):
            emoji = self.config["auto_react"].get("emoji", "👍")
            try:
                await message.add_reaction(emoji)
            except:
                pass  # Ignora errori (es. emoji non valido)
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Evento: Membro lascia il server"""
        print(f"[Example] {member.name} ha lasciato {member.guild.name}")
    
    # ==================== UTILITY COMMANDS ====================
    
    @commands.command(name="reload_config")
    @commands.has_permissions(administrator=True)
    async def reload_config_command(self, ctx):
        """Ricarica la configurazione del plugin (Solo Admin)"""
        self.config = self._load_and_validate_config()
        await ctx.send("✅ Configurazione ricaricata!")
    
    @reload_config_command.error
    async def reload_config_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Solo gli admin possono ricaricare la configurazione!")


async def setup(bot):
    """Setup function richiesta da discord.py"""
    await bot.add_cog(ExampleCog(bot))
