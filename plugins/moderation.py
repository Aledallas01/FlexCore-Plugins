"""
Advanced Moderation Plugin

Sistema completo di moderazione con database SQLite, logging automatico,
ban/mute temporanei, rate limiting e controllo permessi avanzato.

Comandi disponibili:
- /warn - Avverte un utente
- /unwarn - Rimuove un warn
- /kick - Espelle un utente
- /ban - Bandisce un utente (permanente o temporaneo)
- /unban - Rimuove un ban
- /mute - Silenzia un utente (permanente o temporaneo)
- /unmute - Rimuove il silenziamento
"""


import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import asyncio
import re
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Union, Any
from collections import defaultdict

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
import sqlite3
from utils.language_manager import get_text

class ModerationDatabase:
    """Gestisce il database SQLite per il sistema di moderazione"""
    
    def __init__(self, db_path: str = "data/moderation.db"):
        self.db_path = db_path
        self._ensure_data_directory()
        self._initialize_database()
    
    def _ensure_data_directory(self):
        """Crea la directory data se non esiste"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Ottiene una connessione al database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Accesso per nome colonna
        return conn
    
    def _initialize_database(self):
        """Inizializza il database con le tabelle necessarie"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Tabella warns
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabella bans
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                reason TEXT,
                duration INTEGER,
                expires_at DATETIME,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1
            )
        """)
        
        # Tabella mutes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                reason TEXT,
                duration INTEGER,
                expires_at DATETIME,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                active BOOLEAN DEFAULT 1
            )
        """)
        
        # Tabella kicks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabella mod_log (audit generale)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mod_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    # ===== WARNS =====
    
    def add_warn(self, user_id: int, moderator_id: int, guild_id: int, reason: Optional[str] = None) -> int:
        """Aggiunge un warn e ritorna l'ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO warns (user_id, moderator_id, guild_id, reason)
            VALUES (?, ?, ?, ?)
        """, (user_id, moderator_id, guild_id, reason))
        
        warn_id = cursor.lastrowid
        
        # Log nell'audit
        self._add_log(cursor, "WARN", user_id, moderator_id, guild_id, 
                     f"Warn #{warn_id}: {reason or 'Nessun motivo'}")
        
        conn.commit()
        conn.close()
        return warn_id
    
    def remove_warn(self, warn_id: Optional[int] = None, user_id: Optional[int] = None, 
                    guild_id: Optional[int] = None) -> bool:
        """Rimuove un warn specifico o l'ultimo warn di un utente"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if warn_id:
            cursor.execute("DELETE FROM warns WHERE id = ?", (warn_id,))
        elif user_id and guild_id:
            # Rimuovi l'ultimo warn
            cursor.execute("""
                DELETE FROM warns WHERE id = (
                    SELECT id FROM warns 
                    WHERE user_id = ? AND guild_id = ?
                    ORDER BY timestamp DESC LIMIT 1
                )
            """, (user_id, guild_id))
        else:
            conn.close()
            return False
        
        removed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return removed
    
    def get_user_warns(self, user_id: int, guild_id: int) -> List[Dict]:
        """Ottiene tutti i warn di un utente"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM warns 
            WHERE user_id = ? AND guild_id = ?
            ORDER BY timestamp DESC
        """, (user_id, guild_id))
        
        warns = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return warns
    
    def get_warn_count(self, user_id: int, guild_id: int) -> int:
        """Conta i warn di un utente"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM warns 
            WHERE user_id = ? AND guild_id = ?
        """, (user_id, guild_id))
        
        count = cursor.fetchone()['count']
        conn.close()
        return count
    
    # ===== BANS =====
    
    def add_ban(self, user_id: int, moderator_id: int, guild_id: int, 
                reason: Optional[str] = None, duration: Optional[int] = None) -> int:
        """Aggiunge un ban (duration in secondi, None = permanente)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        expires_at = None
        if duration:
            expires_at = datetime.now() + timedelta(seconds=duration)
        
        cursor.execute("""
            INSERT INTO bans (user_id, moderator_id, guild_id, reason, duration, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, moderator_id, guild_id, reason, duration, expires_at))
        
        ban_id = cursor.lastrowid
        
        # Log
        ban_type = "temporaneo" if duration else "permanente"
        self._add_log(cursor, "BAN", user_id, moderator_id, guild_id,
                     f"Ban {ban_type}: {reason or 'Nessun motivo'}")
        
        conn.commit()
        conn.close()
        return ban_id
    
    def remove_ban(self, user_id: int, guild_id: int) -> bool:
        """Rimuove un ban (setta active = 0)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE bans SET active = 0 
            WHERE user_id = ? AND guild_id = ? AND active = 1
        """, (user_id, guild_id))
        
        removed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return removed
    
    def get_active_bans(self, guild_id: Optional[int] = None) -> List[Dict]:
        """Ottiene tutti i ban attivi (opzionalmente filtrati per guild)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if guild_id:
            cursor.execute("""
                SELECT * FROM bans 
                WHERE guild_id = ? AND active = 1
                ORDER BY timestamp DESC
            """, (guild_id,))
        else:
            cursor.execute("""
                SELECT * FROM bans 
                WHERE active = 1
                ORDER BY timestamp DESC
            """)
        
        bans = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return bans
    
    # ===== MUTES =====
    
    def add_mute(self, user_id: int, moderator_id: int, guild_id: int,
                 reason: Optional[str] = None, duration: Optional[int] = None) -> int:
        """Aggiunge un mute (duration in secondi, None = permanente)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        expires_at = None
        if duration:
            expires_at = datetime.now() + timedelta(seconds=duration)
        
        cursor.execute("""
            INSERT INTO mutes (user_id, moderator_id, guild_id, reason, duration, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, moderator_id, guild_id, reason, duration, expires_at))
        
        mute_id = cursor.lastrowid
        
        # Log
        mute_type = "temporaneo" if duration else "permanente"
        self._add_log(cursor, "MUTE", user_id, moderator_id, guild_id,
                     f"Mute {mute_type}: {reason or 'Nessun motivo'}")
        
        conn.commit()
        conn.close()
        return mute_id
    
    def remove_mute(self, user_id: int, guild_id: int) -> bool:
        """Rimuove un mute (setta active = 0)"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE mutes SET active = 0 
            WHERE user_id = ? AND guild_id = ? AND active = 1
        """, (user_id, guild_id))
        
        removed = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return removed
    
    def get_active_mutes(self, guild_id: Optional[int] = None) -> List[Dict]:
        """Ottiene tutti i mute attivi"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if guild_id:
            cursor.execute("""
                SELECT * FROM mutes 
                WHERE guild_id = ? AND active = 1
                ORDER BY timestamp DESC
            """, (guild_id,))
        else:
            cursor.execute("""
                SELECT * FROM mutes 
                WHERE active = 1
                ORDER BY timestamp DESC
            """)
        
        mutes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return mutes
    
    # ===== KICKS =====
    
    def add_kick(self, user_id: int, moderator_id: int, guild_id: int, 
                 reason: Optional[str] = None) -> int:
        """Aggiunge un kick"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO kicks (user_id, moderator_id, guild_id, reason)
            VALUES (?, ?, ?, ?)
        """, (user_id, moderator_id, guild_id, reason))
        
        kick_id = cursor.lastrowid
        
        # Log
        self._add_log(cursor, "KICK", user_id, moderator_id, guild_id,
                     f"Kick: {reason or 'Nessun motivo'}")
        
        conn.commit()
        conn.close()
        return kick_id
    
    # ===== UTILITIES =====
    
    def _add_log(self, cursor: sqlite3.Cursor, action_type: str, user_id: int, 
                 moderator_id: int, guild_id: int, details: str):
        """Aggiunge un entry nel log di moderazione"""
        cursor.execute("""
            INSERT INTO mod_log (action_type, user_id, moderator_id, guild_id, details)
            VALUES (?, ?, ?, ?, ?)
        """, (action_type, user_id, moderator_id, guild_id, details))
    
    def cleanup_expired(self) -> Dict[str, int]:
        """Rimuove ban e mute scaduti, ritorna conteggi"""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.now()
        
        # Conta ban scaduti
        cursor.execute("""
            SELECT COUNT(*) as count FROM bans 
            WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ?
        """, (now,))
        expired_bans = cursor.fetchone()['count']
        
        # Rimuovi ban scaduti
        cursor.execute("""
            UPDATE bans SET active = 0 
            WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ?
        """, (now,))
        
        # Conta mute scaduti
        cursor.execute("""
            SELECT COUNT(*) as count FROM mutes 
            WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ?
        """, (now,))
        expired_mutes = cursor.fetchone()['count']
        
        # Rimuovi mute scaduti
        cursor.execute("""
            UPDATE mutes SET active = 0 
            WHERE active = 1 AND expires_at IS NOT NULL AND expires_at <= ?
        """, (now,))
        
        conn.commit()
        conn.close()
        
        return {"bans": expired_bans, "mutes": expired_mutes}
    
    def get_user_history(self, user_id: int, guild_id: int) -> Dict[str, Any]:
        """Ottiene tutto lo storico di moderazione di un utente"""
        return {
            "warns": self.get_user_warns(user_id, guild_id),
            "bans": self._get_user_bans(user_id, guild_id),
            "mutes": self._get_user_mutes(user_id, guild_id),
            "kicks": self._get_user_kicks(user_id, guild_id)
        }
    
    def _get_user_bans(self, user_id: int, guild_id: int) -> List[Dict]:
        """Ottiene tutti i ban di un utente"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM bans 
            WHERE user_id = ? AND guild_id = ?
            ORDER BY timestamp DESC
        """, (user_id, guild_id))
        
        bans = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return bans
    
    def _get_user_mutes(self, user_id: int, guild_id: int) -> List[Dict]:
        """Ottiene tutti i mute di un utente"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM mutes 
            WHERE user_id = ? AND guild_id = ?
            ORDER BY timestamp DESC
        """, (user_id, guild_id))
        
        mutes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return mutes
    
    def _get_user_kicks(self, user_id: int, guild_id: int) -> List[Dict]:
        """Ottiene tutti i kick di un utente"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM kicks 
            WHERE user_id = ? AND guild_id = ?
            ORDER BY timestamp DESC
        """, (user_id, guild_id))
        
        kicks = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return kicks


class ModerationCog(commands.Cog):
    """Plugin avanzato di moderazione con database e logging"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = ModerationDatabase()
        self.config = self._load_and_validate_config()
        
        # Setup Logging
        self.logger = self._setup_logger()
        
        # Rate limiting: {user_id: [timestamps]}
        self.rate_limit_tracker = defaultdict(list)
        
        # Task manager per ban/mute temporanei
        self.temp_actions = {}  # {action_id: task}
        
        # Avvia task di pulizia periodica
        self.cleanup_task.start()
        self.restore_temp_actions.start()

    def _setup_logger(self):
        """Configura il logger su file"""
        logger = logging.getLogger('moderation')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            # Crea directory logs se non esiste
            os.makedirs('logs', exist_ok=True)
            
            handler = RotatingFileHandler(
                'logs/moderation.log',
                maxBytes=5*1024*1024,  # 5MB
                backupCount=5,
                encoding='utf-8'
            )
            
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def _log_to_file(self, action: str, user: Union[discord.User, discord.Member], 
                     moderator: Union[discord.User, discord.Member], reason: str, 
                     details: str = ""):
        """Scrive un log strutturato su file"""
        if not self.config.get("log_file_enabled", True):
            return
            
        log_msg = f"ACTION={action} | USER={user} ({user.id}) | MOD={moderator} ({moderator.id}) | REASON={reason}"
        if details:
            log_msg += f" | DETAILS={details}"
            
        self.logger.info(log_msg)
    
    def _load_and_validate_config(self) -> Dict:
        """
        Gestisce il ciclo di vita della configurazione:
        1. Auto-Create se non esiste
        2. Load
        3. Validate & Repair (Deep Check)
        """
        config_path = os.path.join('config', 'moderation.json')
        default_config = self._default_config()
        
        # 1. Auto-Create
        if not os.path.exists(config_path):
            print(f"⚙️ [Moderation] Creazione config default in {config_path}...")
            try:
                self._save_config(default_config, config_path)
                return default_config
            except Exception as e:
                print(f"❌ [Moderation] Errore creazione config: {e}")
                return default_config

        # 2. Load
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"❌ [Moderation] Errore caricamento config (JSON corrotto): {e}")
            print(f"⚠️ [Moderation] Uso configurazione di default (file non sovrascritto)")
            return default_config

        # 3. Validate & Repair
        valid = True
        
        # Check Top-Level Keys
        for key, default_val in default_config.items():
            if key not in config:
                print(f"⚠️ [Moderation] Chiave mancante '{key}', aggiunta default.")
                config[key] = default_val
                valid = False
        
        # Deep Check: embed_colors
        if "embed_colors" in config and isinstance(config["embed_colors"], dict):
            for key, val in default_config["embed_colors"].items():
                if key not in config["embed_colors"]:
                    print(f"⚠️ [Moderation] Colore mancante '{key}', aggiunto default.")
                    config["embed_colors"][key] = val
                    valid = False
        else:
            print(f"⚠️ [Moderation] 'embed_colors' invalido, ripristinato default.")
            config["embed_colors"] = default_config["embed_colors"]
            valid = False
            
        # Deep Check: rate_limit
        if "rate_limit" in config and isinstance(config["rate_limit"], dict):
            for key, val in default_config["rate_limit"].items():
                if key not in config["rate_limit"]:
                    config["rate_limit"][key] = val
                    valid = False
        else:
            config["rate_limit"] = default_config["rate_limit"]
            valid = False

        # Deep Check: auto_actions
        if "auto_actions" in config and isinstance(config["auto_actions"], dict):
            for key, val in default_config["auto_actions"].items():
                if key not in config["auto_actions"]:
                    config["auto_actions"][key] = val
                    valid = False
        else:
            config["auto_actions"] = default_config["auto_actions"]
            valid = False
            
        # Type Checks (Basic)
        if not isinstance(config.get("staff_roles"), list):
            config["staff_roles"] = []
            valid = False
            
        if not isinstance(config.get("admin_roles"), list):
            config["admin_roles"] = []
            valid = False

        # Save if repaired
        if not valid:
            print(f"🔧 [Moderation] Configurazione riparata e salvata.")
            self._save_config(config, config_path)
        else:
            print(f"✅ [Moderation] Configurazione caricata e validata.")

        return config

    def _save_config(self, config: Dict, path: str):
        """Helper per salvare la configurazione"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    
    def _default_config(self) -> Dict:
        """Configurazione di default"""
        return {
            "staff_roles": ["STAFF_ROLE_ID_HERE"],
            "admin_roles": ["ADMIN_ROLE_ID_HERE"],
            "log_channel_id": "LOG_CHANNEL_ID_HERE",
            "mute_role_id": "MUTED_ROLE_ID_HERE",
            "mute_role_name": "null",
            "embed_colors": {
                "warn": "#FFA500",
                "unwarn": "#90EE90",
                "kick": "#FF6347",
                "ban": "#DC143C",
                "unban": "#32CD32",
                "mute": "#FFD700",
                "unmute": "#ADFF2F",
                "success": "#00FF00",
                "error": "#FF0000",
                "info": "#00BFFF"
            },
            "rate_limit": {
                "enabled": True,
                "max_commands": "5",
                "per_seconds": "60"
            },
            "auto_actions": {
                "enabled": True,
                "auto_ban_warns": "5",
                "auto_mute_warns": "3"
            },
            "dm_users": True,
            "show_warn_count": True,
            "log_file_enabled": True,
            "backup": {
                "enabled": True,
                "interval_hours": "24",
                "keep_backups": "3"
            }
        }

    
    def cog_unload(self):
        """Cleanup quando il cog viene scaricato"""
        self.cleanup_task.cancel()
        self.restore_temp_actions.cancel()
        
        # Cancella tutti i task temporanei
        for task in self.temp_actions.values():
            task.cancel()
    
    # ===== UTILITY FUNCTIONS =====
    
    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """
        Parse durata flessibile in formato Nt dove N=numero, t=tipo
        Supporta: s (secondi), m (minuti), h (ore), d (giorni), w (settimane), M (mesi), y (anni)
        
        Esempi:
        - "30s" = 30 secondi
        - "45m" = 45 minuti
        - "2h" = 2 ore
        - "7d" = 7 giorni
        - "2w" = 2 settimane
        - "3M" = 3 mesi (approssimati a 30 giorni)
        - "1y" = 1 anno (approssimato a 365 giorni)
        
        Returns:
            int: Durata in secondi, None se formato invalido
        """
        if not duration_str:
            return None
        
        # Regex per catturare numero + unità
        pattern = r'^(\d+)([smhdwMy])$'
        match = re.match(pattern, duration_str)
        
        if not match:
            return None
        
        amount = int(match.group(1))
        unit = match.group(2)
        
        # Conversioni in secondi
        conversions = {
            's': 1,              # secondi
            'm': 60,             # minuti
            'h': 3600,           # ore
            'd': 86400,          # giorni
            'w': 604800,         # settimane (7 giorni)
            'M': 2592000,        # mesi (30 giorni)
            'y': 31536000        # anni (365 giorni)
        }
        
        return amount * conversions[unit]
    
    def _format_duration(self, seconds: int) -> str:
        """Formatta secondi in stringa leggibile"""
        if seconds >= 31536000:  # >= 1 anno
            years = seconds // 31536000
            return f"{years} anno/i"
        elif seconds >= 2592000:  # >= 1 mese
            months = seconds // 2592000
            return f"{months} mese/i"
        elif seconds >= 604800:  # >= 1 settimana
            weeks = seconds // 604800
            return f"{weeks} settimana/e"
        elif seconds >= 86400:  # >= 1 giorno
            days = seconds // 86400
            return f"{days} giorno/i"
        elif seconds >= 3600:  # >= 1 ora
            hours = seconds // 3600
            return f"{hours} ora/e"
        elif seconds >= 60:  # >= 1 minuto
            minutes = seconds // 60
            return f"{minutes} minuto/i"
        else:
            return f"{seconds} secondo/i"
    
    def _check_permissions(self, member: discord.Member, required_level: str = "staff") -> bool:
        """
        Verifica i permessi di un membro
        
        Args:
            member: Membro da verificare
            required_level: "staff" o "admin"
        
        Returns:
            bool: True se ha i permessi
        """
        # Owner del bot bypassa tutto
        if member.id == self.bot.owner_id:
            return True
        
        # Amministratori server hanno sempre permesso
        if member.guild_permissions.administrator:
            return True
        
        # Controlla ruoli configurati
        member_role_ids = [role.id for role in member.roles]
        
        if required_level == "admin":
            return any(role_id in self.config.get("admin_roles", []) for role_id in member_role_ids)
        else:  # staff
            staff_check = any(role_id in self.config.get("staff_roles", []) for role_id in member_role_ids)
            admin_check = any(role_id in self.config.get("admin_roles", []) for role_id in member_role_ids)
            return staff_check or admin_check
    
    def _check_rate_limit(self, user_id: int) -> bool:
        """
        Verifica rate limiting
        
        Returns:
            bool: True se può procedere, False se rate limited
        """
        if not self.config.get("rate_limit", {}).get("enabled", False):
            return True
        
        now = datetime.now()
        max_commands = int(self.config["rate_limit"]["max_commands"])
        time_window = int(self.config["rate_limit"]["per_seconds"])
        
        # Rimuovi timestamp vecchi
        cutoff = now - timedelta(seconds=time_window)
        self.rate_limit_tracker[user_id] = [
            ts for ts in self.rate_limit_tracker[user_id] if ts > cutoff
        ]
        
        # Controlla limite
        if len(self.rate_limit_tracker[user_id]) >= max_commands:
            return False
        
        # Aggiungi nuovo timestamp
        self.rate_limit_tracker[user_id].append(now)
        return True
    
    def _create_embed(self, action_type: str, title: str, description: str, 
                      color: Optional[int] = None, 
                      user: Optional[Union[discord.User, discord.Member]] = None) -> discord.Embed:
        """Crea un embed personalizzato per le azioni di moderazione"""
        if color is None:
            color_hex = self.config.get("embed_colors", {}).get(action_type, "#5865F2")
            color = int(color_hex.replace("#", ""), 16)
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        
        # Aggiungi thumbnail se c'è un utente
        if user:
            if user.avatar:
                embed.set_thumbnail(url=user.avatar.url)
            else:
                embed.set_thumbnail(url=user.default_avatar.url)
                
        # Footer professionale
        embed.set_footer(text="🛡️ Moderation System", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        
        return embed
    
    async def _send_to_log(self, guild: discord.Guild, embed: discord.Embed):
        """Invia embed al canale log se configurato"""
        log_channel_id = self.config.get("log_channel_id")
        if not log_channel_id:
            return
            
        try:
            log_channel_id = int(log_channel_id)
        except (ValueError, TypeError):
            return
        
        log_channel = guild.get_channel(log_channel_id)
        if log_channel and isinstance(log_channel, discord.TextChannel):
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                print(f"⚠️  {get_text('moderation.log_send_error', channel_id=log_channel_id)}")
            except Exception as e:
                print(f"❌ {get_text('moderation.log_error', error=e)}")
    
    async def _send_dm(self, user: discord.User, embed: discord.Embed) -> bool:
        """Invia DM all'utente se abilitato"""
        if not self.config.get("dm_users", True):
            return False
        
        try:
            await user.send(embed=embed)
            return True
        except discord.Forbidden:
            return False
        except Exception:
            return False
    
    async def _get_or_create_mute_role(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Ottiene o crea il ruolo mute"""
        # Controlla se configurato
        mute_role_id = self.config.get("mute_role_id")
        if mute_role_id:
            try:
                role = guild.get_role(int(mute_role_id))
                if role:
                    return role
            except (ValueError, TypeError):
                pass
        
        # Cerca per nome
        mute_role_name = self.config.get("mute_role_name", "Muted")
        role = discord.utils.get(guild.roles, name=mute_role_name)
        if role:
            return role
        
        # Crea nuovo ruolo
        try:
            role = await guild.create_role(
                name=mute_role_name,
                color=discord.Color.dark_gray(),
                reason="Ruolo mute auto-creato dal sistema di moderazione"
            )
            
            # Imposta permessi per tutti i canali
            for channel in guild.channels:
                try:
                    await channel.set_permissions(
                        role,
                        send_messages=False,
                        send_messages_in_threads=False,
                        create_public_threads=False,
                        create_private_threads=False,
                        add_reactions=False,
                        speak=False
                    )
                except:
                    pass  # Ignora errori su canali specifici
            
            return role
        except discord.Forbidden:
            return None
    
    # ===== TASK MANAGEMENT =====
    
    @tasks.loop(minutes=5)
    async def cleanup_task(self):
        """Task periodico per pulizia ban/mute scaduti"""
        try:
            result = self.db.cleanup_expired()
            if result["bans"] > 0 or result["mutes"] > 0:
                print(f"🧹 {get_text('moderation.cleanup', bans=result['bans'], mutes=result['mutes'])}")
        except Exception as e:
            print(f"❌ {get_text('moderation.cleanup_error', error=e)}")
    
    @cleanup_task.before_loop
    async def before_cleanup(self):
        """Attendi che il bot sia pronto prima di iniziare il task"""
        await self.bot.wait_until_ready()
    @tasks.loop(count=1)
    async def restore_temp_actions(self):
        """Ripristina ban/mute temporanei dopo restart del bot"""
        await self.bot.wait_until_ready()
        
        try:
            # Ripristina ban temporanei
            active_bans = self.db.get_active_bans()
            for ban in active_bans:
                if ban['expires_at'] and ban['duration']:
                    expires_at = datetime.fromisoformat(ban['expires_at'])
                    if expires_at > datetime.now():
                        # Crea task per auto-unban
                        delay = (expires_at - datetime.now()).total_seconds()
                        task = asyncio.create_task(self._auto_unban(
                            ban['user_id'], 
                            ban['guild_id'], 
                            delay
                        ))
                        self.temp_actions[f"ban_{ban['id']}"] = task
            
            # Ripristina mute temporanei
            active_mutes = self.db.get_active_mutes()
            for mute in active_mutes:
                if mute['expires_at'] and mute['duration']:
                    expires_at = datetime.fromisoformat(mute['expires_at'])
                    if expires_at > datetime.now():
                        # Crea task per auto-unmute
                        delay = (expires_at - datetime.now()).total_seconds()
                        task = asyncio.create_task(self._auto_unmute(
                            mute['user_id'], 
                            mute['guild_id'], 
                            delay
                        ))
                        self.temp_actions[f"mute_{mute['id']}"] = task
            
            if active_bans or active_mutes:
                print(f"🔄 {get_text('moderation.restore', bans=len(active_bans), mutes=len(active_mutes))}")
                
        except Exception as e:
            print(f"❌ {get_text('moderation.restore_error', error=e)}")
    
    async def _auto_unban(self, user_id: int, guild_id: int, delay: float):
        """Task per auto-unban dopo delay"""
        await asyncio.sleep(delay)
        
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            
            user = await self.bot.fetch_user(user_id)
            if not user:
                return
            
            # Rimuovi ban
            await guild.unban(user, reason="Ban temporaneo scaduto")
            self.db.remove_ban(user_id, guild_id)
            
            # Log
            embed = self._create_embed(
                "success",
                "🔓 Auto-Unban",
                f"**Utente:** {user.mention} ({user.id})\n"
                f"**Motivo:** Ban temporaneo scaduto",
                user=user
            )
            
            # Log su file
            self._log_to_file("AUTO-UNBAN", user, self.bot.user, "Ban temporaneo scaduto")
            
            await self._send_to_log(guild, embed)
            
        except Exception as e:
            print(f"❌ {get_text('moderation.auto_unban_error', error=e)}")
    
    async def _auto_unmute(self, user_id: int, guild_id: int, delay: float):
        """Task per auto-unmute dopo delay"""
        await asyncio.sleep(delay)
        
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            
            member = guild.get_member(user_id)
            if not member:
                return
            
            mute_role = await self._get_or_create_mute_role(guild)
            if not mute_role:
                return
            
            # Rimuovi ruolo
            await member.remove_roles(mute_role, reason="Mute temporaneo scaduto")
            self.db.remove_mute(user_id, guild_id)
            
            # Log
            embed = self._create_embed(
                "success",
                "🔊 Auto-Unmute",
                f"**Utente:** {member.mention} ({member.id})\n"
                f"**Motivo:** Mute temporaneo scaduto",
                user=member
            )
            
            # Log su file
            self._log_to_file("AUTO-UNMUTE", member, self.bot.user, "Mute temporaneo scaduto")
            
            await self._send_to_log(guild, embed)
            
        except Exception as e:
            print(f"❌ {get_text('moderation.auto_unmute_error', error=e)}")
    
    # ===== SLASH COMMANDS =====
    
    @app_commands.command(name="warn", description="Avverte un utente")
    @app_commands.describe(
        user="L'utente da avvertire",
        reason="Motivo del warn (opzionale)"
    )
    async def warn_command(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        """Comando /warn - Avverte un utente"""
        
        # Controlla permessi
        if not self._check_permissions(interaction.user, "staff"):
            await interaction.response.send_message("❌ Non hai i permessi per usare questo comando!", ephemeral=True)
            return
        
        # Rate limiting
        if not self._check_rate_limit(interaction.user.id):
            await interaction.response.send_message(
                "⏱️ Stai usando troppi comandi di moderazione! Riprova tra qualche secondo.",
                ephemeral=True
            )
            return
        
        # Non può warnare se stesso
        if user == interaction.user:
            await interaction.response.send_message("❌ Non puoi warnare te stesso!", ephemeral=True)
            return
        
        # Non può warnare il bot
        if user.bot:
            await interaction.response.send_message("❌ Non puoi warnare un bot!", ephemeral=True)
            return
        
        try:
            # Aggiungi warn al database
            warn_id = self.db.add_warn(user.id, interaction.user.id, interaction.guild.id, reason)
            warn_count = self.db.get_warn_count(user.id, interaction.guild.id)
            
            # Embed per conferma
            reason_text = reason or "Nessun motivo specificato"
            warn_info = f"⚠️ **Warn #{warn_id}**\n\n"
            warn_info += f"**Utente:** {user.mention} ({user.id})\n"
            warn_info += f"**Moderatore:** {interaction.user.mention}\n"
            warn_info += f"**Motivo:** {reason_text}\n"
            if self.config.get("show_warn_count", True):
                warn_info += f"**Warn Totali:** {warn_count}"
            
            embed = self._create_embed("warn", "🚨 Warn Assegnato", warn_info, user=user)
            await interaction.response.send_message(embed=embed)
            
            # DM all'utente
            dm_embed = self._create_embed(
                "warn",
                f"🚨 Warn Ricevuto in {interaction.guild.name}",
                f"**Moderatore:** {interaction.user.name}\n"
                f"**Motivo:** {reason_text}\n"
                f"**Warn Totali:** {warn_count}\n\n"
                f"⚠️ Comportati meglio per evitare ulteriori sanzioni!",
                user=user
            )
            dm_sent = await self._send_dm(user, dm_embed)
            
            # Log su file
            self._log_to_file("WARN", user, interaction.user, reason_text, f"Warn Count: {warn_count}")
            
            # Log su canale
            log_embed = embed.copy()
            log_embed.add_field(name="DM Inviato", value="✅ Sì" if dm_sent else "❌ No", inline=True)
            await self._send_to_log(interaction.guild, log_embed)
            
            # Auto-actions se abilitati
            if self.config.get("auto_actions", {}).get("enabled", False):
                auto_ban_warns = int(self.config["auto_actions"].get("auto_ban_warns", 5))
                auto_mute_warns = int(self.config["auto_actions"].get("auto_mute_warns", 3))
                
                if warn_count >= auto_ban_warns:
                    # Auto-ban
                    try:
                        await user.ban(reason=f"Auto-ban: raggiunti {warn_count} warn")
                        self.db.add_ban(user.id, self.bot.user.id, interaction.guild.id, 
                                      f"Auto-ban per {warn_count} warn")
                        
                        auto_embed = self._create_embed(
                            "ban",
                            "🔨 Auto-Ban",
                            f"{user.mention} è stato bannato automaticamente per aver raggiunto {warn_count} warn",
                            user=user
                        )
                        
                        # Log su file
                        self._log_to_file("AUTO-BAN", user, self.bot.user, f"Raggiunti {warn_count} warn")
                        
                        await interaction.followup.send(embed=auto_embed)
                        await self._send_to_log(interaction.guild, auto_embed)
                    except:
                        pass
                
                elif warn_count >= auto_mute_warns:
                    # Auto-mute
                    mute_role = await self._get_or_create_mute_role(interaction.guild)
                    if mute_role and mute_role not in user.roles:
                        try:
                            await user.add_roles(mute_role, reason=f"Auto-mute: raggiunti {warn_count} warn")
                            self.db.add_mute(user.id, self.bot.user.id, interaction.guild.id,
                                           f"Auto-mute per {warn_count} warn", 3600)  # 1 ora
                            
                            auto_embed = self._create_embed(
                                "mute",
                                "🔇 Auto-Mute",
                                f"{user.mention} è stato mutato automaticamente per 1 ora (raggiunti {warn_count} warn)",
                                user=user
                            )
                            
                            # Log su file
                            self._log_to_file("AUTO-MUTE", user, self.bot.user, f"Raggiunti {warn_count} warn", "Duration: 1h")
                            
                            await interaction.followup.send(embed=auto_embed)
                            await self._send_to_log(interaction.guild, auto_embed)
                        except:
                            pass
        
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)
    
    @app_commands.command(name="unwarn", description="Rimuove un warn da un utente")
    @app_commands.describe(
        user="L'utente da cui rimuovere il warn",
        warn_id="ID del warn da rimuovere (opzionale, rimuove l'ultimo se non specificato)"
    )
    async def unwarn_command(self, interaction: discord.Interaction, user: discord.Member, warn_id: Optional[int] = None):
        """Comando /unwarn - Rimuove un warn"""
        
        # Controlla permessi (solo admin)
        if not self._check_permissions(interaction.user, "admin"):
            await interaction.response.send_message("❌ Solo gli admin possono rimuovere warn!", ephemeral=True)
            return
        
        try:
            # Rimuovi warn
            if warn_id:
                removed = self.db.remove_warn(warn_id=warn_id)
                warn_text = f"Warn #{warn_id}"
            else:
                removed = self.db.remove_warn(user_id=user.id, guild_id=interaction.guild.id)
                warn_text = "ultimo warn"
            
            if not removed:
                await interaction.response.send_message(
                    f"❌ Nessun warn trovato per {user.mention}!",
                    ephemeral=True
                )
                return
            
            # Conta warn rimanenti
            remaining_warns = self.db.get_warn_count(user.id, interaction.guild.id)
            
            # Embed
            embed = self._create_embed(
                "unwarn",
                "✅ Warn Rimosso",
                f"**Utente:** {user.mention}\n"
                f"**Moderatore:** {interaction.user.mention}\n"
                f"**Warn Rimosso:** {warn_text}\n"
                f"**Warn Rimanenti:** {remaining_warns}",
                user=user
            )
            
            # Log su file
            self._log_to_file("UNWARN", user, interaction.user, "N/A", f"Removed: {warn_text}")
            
            await interaction.response.send_message(embed=embed)
            await self._send_to_log(interaction.guild, embed)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)
    
    @app_commands.command(name="kick", description="Espelle un utente dal server")
    @app_commands.describe(
        user="L'utente da espellere",
        reason="Motivo del kick (opzionale)"
    )
    async def kick_command(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        """Comando /kick - Espelle un utente"""
        
        # Controlla permessi
        if not self._check_permissions(interaction.user, "staff"):
            await interaction.response.send_message("❌ Non hai i permessi per usare questo comando!", ephemeral=True)
            return
        
        # Controlli di sicurezza
        if user == interaction.user:
            await interaction.response.send_message("❌ Non puoi kickare te stesso!", ephemeral=True)
            return
        
        if user.bot and user.id == self.bot.user.id:
            await interaction.response.send_message("❌ Non puoi kickare il bot!", ephemeral=True)
            return
        
        if user.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ Non puoi kickare qualcuno con un ruolo superiore o uguale al tuo!", ephemeral=True)
            return
        
        try:
            reason_text = reason or "Nessun motivo specificato"
            
            # DM prima del kick
            dm_embed = self._create_embed(
                "kick",
                f"👢 Espulso da {interaction.guild.name}",
                f"**Moderatore:** {interaction.user.name}\n"
                f"**Motivo:** {reason_text}"
            )
            await self._send_dm(user, dm_embed)
            
            # Esegui kick
            await user.kick(reason=reason_text)
            
            # Salva in DB
            self.db.add_kick(user.id, interaction.user.id, interaction.guild.id, reason)
            
            # Embed conferma
            embed = self._create_embed(
                "kick",
                "👢 Utente Espulso",
                f"**Utente:** {user.mention} ({user.id})\n"
                f"**Moderatore:** {interaction.user.mention}\n"
                f"**Motivo:** {reason_text}",
                user=user
            )
            
            # Log su file
            self._log_to_file("KICK", user, interaction.user, reason_text)
            
            await interaction.response.send_message(embed=embed)
            await self._send_to_log(interaction.guild, embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ Non ho i permessi per kickare questo utente!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)
    
    @app_commands.command(name="ban", description="Bandisce un utente dal server")
    @app_commands.describe(
        user="L'utente da bannare",
        duration="Durata del ban (es: 30m, 2h, 7d) - lascia vuoto per permanente",
        reason="Motivo del ban (opzionale)"
    )
    async def ban_command(self, interaction: discord.Interaction, user: discord.Member, 
                         duration: Optional[str] = None, reason: Optional[str] = None):
        """Comando /ban - Bandisce un utente (permanente o temporaneo)"""
        
        # Controlla permessi
        if not self._check_permissions(interaction.user, "admin"):
            await interaction.response.send_message("❌ Solo gli admin possono bannare!", ephemeral=True)
            return
        
        # Controlli di sicurezza
        if user == interaction.user:
            await interaction.response.send_message("❌ Non puoi bannare te stesso!", ephemeral=True)
            return
        
        if user.bot and user.id == self.bot.user.id:
            await interaction.response.send_message("❌ Non puoi bannare il bot!", ephemeral=True)
            return
        
        if user.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ Non puoi bannare qualcuno con un ruolo superiore o uguale al tuo!", ephemeral=True)
            return
        
        try:
            reason_text = reason or "Nessun motivo specificato"
            
            # Parse durata
            duration_seconds = None
            duration_text = "permanente"
            if duration:
                duration_seconds = self._parse_duration(duration)
                if not duration_seconds:
                    await interaction.response.send_message(
                        f"❌ Formato durata invalido! Usa: `30s`, `45m`, `2h`, `7d`, ecc.",
                        ephemeral=True
                    )
                    return
                duration_text = self._format_duration(duration_seconds)
            
            # DM prima del ban
            dm_embed = self._create_embed(
                "ban",
                f"🔨 Bannato da {interaction.guild.name}",
                f"**Moderatore:** {interaction.user.name}\n"
                f"**Durata:** {duration_text}\n"
                f"**Motivo:** {reason_text}"
            )
            await self._send_dm(user, dm_embed)
            
            # Esegui ban
            await user.ban(reason=reason_text, delete_message_days=1)
            
            # Salva in DB
            ban_id = self.db.add_ban(user.id, interaction.user.id, interaction.guild.id, reason, duration_seconds)
            
            # Se temporaneo, crea task per auto-unban
            if duration_seconds:
                task = asyncio.create_task(self._auto_unban(user.id, interaction.guild.id, duration_seconds))
                self.temp_actions[f"ban_{ban_id}"] = task
            
            # Embed conferma
            embed = self._create_embed(
                "ban",
                "🔨 Utente Bannato",
                f"**Utente:** {user.mention} ({user.id})\n"
                f"**Moderatore:** {interaction.user.mention}\n"
                f"**Durata:** {duration_text}\n"
                f"**Motivo:** {reason_text}",
                user=user
            )
            
            # Log su file
            self._log_to_file("BAN", user, interaction.user, reason_text, f"Duration: {duration_text}")
            
            await interaction.response.send_message(embed=embed)
            await self._send_to_log(interaction.guild, embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ Non ho i permessi per bannare questo utente!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)
    
    @app_commands.command(name="unban", description="Rimuove il ban di un utente")
    @app_commands.describe(
        user_id="L'ID dell'utente da sbannare",
        reason="Motivo dello unban (opzionale)"
    )
    async def unban_command(self, interaction: discord.Interaction, user_id: str, reason: Optional[str] = None):
        """Comando /unban - Rimuove un ban"""
        
        # Controlla permessi
        if not self._check_permissions(interaction.user, "admin"):
            await interaction.response.send_message("❌ Solo gli admin possono sbannare!", ephemeral=True)
            return
        
        try:
            # Converti ID
            try:
                uid = int(user_id)
            except ValueError:
                await interaction.response.send_message("❌ ID utente invalido!", ephemeral=True)
                return
            
            # Fetch utente
            user = await self.bot.fetch_user(uid)
            if not user:
                await interaction.response.send_message("❌ Utente non trovato!", ephemeral=True)
                return
            
            reason_text = reason or "Nessun motivo specificato"
            
            # Rimuovi ban
            await interaction.guild.unban(user, reason=reason_text)
            self.db.remove_ban(uid, interaction.guild.id)
            
            # Embed
            embed = self._create_embed(
                "unban",
                "🔓 Utente Sbannato",
                f"**Utente:** {user.mention} ({user.id})\n"
                f"**Moderatore:** {interaction.user.mention}\n"
                f"**Motivo:** {reason_text}",
                user=user
            )
            
            # Log su file
            self._log_to_file("UNBAN", user, interaction.user, reason_text)
            
            await interaction.response.send_message(embed=embed)
            await self._send_to_log(interaction.guild, embed)
            
        except discord.NotFound:
            await interaction.response.send_message("❌ Utente non bannato!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Non ho i permessi per sbannare!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)
    
    @app_commands.command(name="mute", description="Silenzia un utente")
    @app_commands.describe(
        user="L'utente da silenziare",
        duration="Durata del mute (es: 30m, 2h, 7d) - lascia vuoto per permanente",
        reason="Motivo del mute (opzionale)"
    )
    async def mute_command(self, interaction: discord.Interaction, user: discord.Member,
                          duration: Optional[str] = None, reason: Optional[str] = None):
        """Comando /mute - Silenzia un utente"""
        
        # Controlla permessi
        if not self._check_permissions(interaction.user, "staff"):
            await interaction.response.send_message("❌ Non hai i permessi per usare questo comando!", ephemeral=True)
            return
        
        # Controlli di sicurezza
        if user == interaction.user:
            await interaction.response.send_message("❌ Non puoi mutare te stesso!", ephemeral=True)
            return
        
        if user.bot and user.id == self.bot.user.id:
            await interaction.response.send_message("❌ Non puoi mutare il bot!", ephemeral=True)
            return
        
        if user.top_role >= interaction.user.top_role:
            await interaction.response.send_message("❌ Non puoi mutare qualcuno con un ruolo superiore o uguale al tuo!", ephemeral=True)
            return
        
        try:
            # Ottieni ruolo mute
            mute_role = await self._get_or_create_mute_role(interaction.guild)
            if not mute_role:
                await interaction.response.send_message("❌ Impossibile ottenere il ruolo mute!", ephemeral=True)
                return
            
            # Controlla se già mutato
            if mute_role in user.roles:
                await interaction.response.send_message(f"❌ {user.mention} è già mutato!", ephemeral=True)
                return
            
            reason_text = reason or "Nessun motivo specificato"
            
            # Parse durata
            duration_seconds = None
            duration_text = "permanente"
            if duration:
                duration_seconds = self._parse_duration(duration)
                if not duration_seconds:
                    await interaction.response.send_message(
                        f"❌ Formato durata invalido! Usa: `30s`, `45m`, `2h`, `7d`, ecc.",
                        ephemeral=True
                    )
                    return
                duration_text = self._format_duration(duration_seconds)
            
            # Applica mute
            await user.add_roles(mute_role, reason=reason_text)
            
            # Salva in DB
            mute_id = self.db.add_mute(user.id, interaction.user.id, interaction.guild.id, reason, duration_seconds)
            
            # Se temporaneo, crea task per auto-unmute
            if duration_seconds:
                task = asyncio.create_task(self._auto_unmute(user.id, interaction.guild.id, duration_seconds))
                self.temp_actions[f"mute_{mute_id}"] = task
            
            # DM all'utente
            dm_embed = self._create_embed(
                "mute",
                f"🔇 Silenziato in {interaction.guild.name}",
                f"**Moderatore:** {interaction.user.name}\n"
                f"**Durata:** {duration_text}\n"
                f"**Motivo:** {reason_text}"
            )
            await self._send_dm(user, dm_embed)
            
            # Embed conferma
            embed = self._create_embed(
                "mute",
                "🔇 Utente Silenziato",
                f"**Utente:** {user.mention} ({user.id})\n"
                f"**Moderatore:** {interaction.user.mention}\n"
                f"**Durata:** {duration_text}\n"
                f"**Motivo:** {reason_text}",
                user=user
            )
            
            # Log su file
            self._log_to_file("MUTE", user, interaction.user, reason_text, f"Duration: {duration_text}")
            
            await interaction.response.send_message(embed=embed)
            await self._send_to_log(interaction.guild, embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ Non ho i permessi per mutare questo utente!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)
    
    @app_commands.command(name="unmute", description="Rimuove il silenziamento di un utente")
    @app_commands.describe(
        user="L'utente da cui rimuovere il mute",
        reason="Motivo del unmute (opzionale)"
    )
    async def unmute_command(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        """Comando /unmute - Rimuove il silenziamento"""
        
        # Controlla permessi
        if not self._check_permissions(interaction.user, "staff"):
            await interaction.response.send_message("❌ Non hai i permessi per usare questo comando!", ephemeral=True)
            return
        
        try:
            # Ottieni ruolo mute
            mute_role = await self._get_or_create_mute_role(interaction.guild)
            if not mute_role:
                await interaction.response.send_message("❌ Ruolo mute non trovato!", ephemeral=True)
                return
            
            # Controlla se è mutato
            if mute_role not in user.roles:
                await interaction.response.send_message(f"❌ {user.mention} non è mutato!", ephemeral=True)
                return
            
            reason_text = reason or "Nessun motivo specificato"
            
            # Rimuovi ruolo
            await user.remove_roles(mute_role, reason=reason_text)
            self.db.remove_mute(user.id, interaction.guild.id)
            
            # Embed
            embed = self._create_embed(
                "unmute",
                "🔊 Utente Smutato",
                f"**Utente:** {user.mention} ({user.id})\n"
                f"**Moderatore:** {interaction.user.mention}\n"
                f"**Motivo:** {reason_text}",
                user=user
            )
            
            # Log su file
            self._log_to_file("UNMUTE", user, interaction.user, reason_text)
            
            await interaction.response.send_message(embed=embed)
            await self._send_to_log(interaction.guild, embed)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ Non ho i permessi per smutare questo utente!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Errore: {e}", ephemeral=True)


async def setup(bot):
    """Funzione per caricare il cog"""
    await bot.add_cog(ModerationCog(bot))
