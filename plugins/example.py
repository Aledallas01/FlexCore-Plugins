import discord
from discord.ext import commands
import json
import os

class ExamplePlugin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_name = "example_plugin"
        self.config_path = os.path.join("config", f"{self.config_name}.json")
        
        # Configurazione di default
        self.default_config = {
            "welcome_message": "Hello {user}, welcome to the server!",
            "admin_role_id": 0,  # 0 significa disabilitato/non impostato
            "log_channel_id": 0
        }
        
        # Carica e valida la configurazione all'avvio
        self.config = self._load_and_validate_config()

    def _load_and_validate_config(self):
        """
        Gestisce l'intero ciclo di vita della configurazione:
        1. Crea il file se non esiste (Auto-Create)
        2. Carica il file
        3. Valida i campi e ripara eventuali errori (Config Checker)
        """
        print(f"🔌 [ExamplePlugin] Checking configuration...")

        # 1. Auto-Create Config
        if not os.path.exists(self.config_path):
            print(f"⚙️ [ExamplePlugin] Creating default config at {self.config_path}...")
            try:
                self._save_config(self.default_config)
                return self.default_config
            except Exception as e:
                print(f"❌ [ExamplePlugin] Failed to create config: {e}")
                return self.default_config

        # 2. Load Config
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"❌ [ExamplePlugin] Failed to load config (JSON Error): {e}")
            return self.default_config

        # 3. Validate & Repair Config (Self-contained Checker)
        valid = True
        
        # Check missing keys
        for key, default_val in self.default_config.items():
            if key not in config:
                print(f"⚠️ [ExamplePlugin] Missing key '{key}', adding default.")
                config[key] = default_val
                valid = False 
        
        # Check types (Simple Validation)
        if not isinstance(config.get("welcome_message"), str):
            print("❌ [ExamplePlugin] 'welcome_message' must be a string! Resetting to default.")
            config["welcome_message"] = self.default_config["welcome_message"]
            valid = False
            
        if not isinstance(config.get("admin_role_id"), int):
            print("❌ [ExamplePlugin] 'admin_role_id' must be an integer! Resetting to 0.")
            config["admin_role_id"] = 0
            valid = False

        # Save if modified/fixed
        if not valid:
            self._save_config(config)
            print(f"✅ [ExamplePlugin] Config repaired and saved.")
        else:
            print(f"✅ [ExamplePlugin] Config loaded and validated successfully.")

        return config

    def _save_config(self, config):
        """Helper per salvare la configurazione"""
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=4)

    @commands.command()
    async def example(self, ctx):
        """Un comando di esempio che usa la configurazione."""
        msg = self.config["welcome_message"].format(user=ctx.author.mention)
        await ctx.send(f"👋 {msg}")

    @commands.command()
    async def check_config(self, ctx):
        """Comando admin per ricaricare/verificare la config."""
        # Esempio di check permessi basato su config
        admin_role_id = self.config.get("admin_role_id")
        
        if admin_role_id != 0:
            role = ctx.guild.get_role(admin_role_id)
            if not role or role not in ctx.author.roles:
                await ctx.send("❌ Non hai il ruolo admin configurato per questo plugin!")
                return

        self.config = self._load_and_validate_config()
        await ctx.send("✅ Configurazione ricaricata e verificata!")

async def setup(bot):
    await bot.add_cog(ExamplePlugin(bot))
