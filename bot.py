
import os
import io
import re
import random
import sqlite3
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# CONFIGURAÇÃO / BANCO
# =========================================================

APPLICATION_ID = "1535116053649162300"
INVITE_PERMISSIONS = "1374658096214"
INVITE_URL = (
    "https://discord.com/oauth2/authorize"
    f"?client_id={APPLICATION_ID}"
    "&scope=bot%20applications.commands"
    f"&permissions={INVITE_PERMISSIONS}"
)
SUPPORT_URL = "https://discord.gg/SvZHVPdbR"
SITE_URL = "https://heitormeire.github.io/honradinho-site/"
PRIVACY_URL = f"{SITE_URL}privacy.html"
TERMS_URL = f"{SITE_URL}terms.html"

DB_PATH = os.getenv("HONRADINHO_DB_PATH", "honradinho.db")
BOT_STARTED_AT = discord.utils.utcnow()
XP_COOLDOWN_SECONDS = 60
xp_cooldowns: dict[tuple[int, int], datetime.datetime] = {}

db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
cur = db.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    ticket_staff_role_id INTEGER,
    ticket_logs_channel_id INTEGER,
    ticket_category_id INTEGER,
    welcome_channel_id INTEGER,
    goodbye_channel_id INTEGER,
    autorole_id INTEGER,
    welcome_message TEXT DEFAULT 'Bem-vindo(a) {user} ao **{server}**! 🎉 Você é o membro #{members}.',
    goodbye_message TEXT DEFAULT '{user} saiu do **{server}**. 👋',
    suggestions_channel_id INTEGER,
    moderation_logs_channel_id INTEGER
);

CREATE TABLE IF NOT EXISTS user_stats (
    guild_id INTEGER,
    user_id INTEGER,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 0,
    balance INTEGER DEFAULT 0,
    last_daily TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    user_id INTEGER,
    moderator_id INTEGER,
    reason TEXT,
    created_at TEXT
);
""")
db.commit()


def ensure_guild(guild_id: int):
    cur.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
    db.commit()


def get_guild_config(guild_id: int):
    ensure_guild(guild_id)
    cur.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
    return cur.fetchone()


def set_guild_config(guild_id: int, field: str, value):
    allowed = {
        "ticket_staff_role_id",
        "ticket_logs_channel_id",
        "ticket_category_id",
        "welcome_channel_id",
        "goodbye_channel_id",
        "autorole_id",
        "welcome_message",
        "goodbye_message",
        "suggestions_channel_id",
        "moderation_logs_channel_id",
    }
    if field not in allowed:
        raise ValueError("Campo de configuração inválido.")
    ensure_guild(guild_id)
    cur.execute(f"UPDATE guild_config SET {field} = ? WHERE guild_id = ?", (value, guild_id))
    db.commit()


def ensure_user(guild_id: int, user_id: int):
    cur.execute(
        "INSERT OR IGNORE INTO user_stats (guild_id, user_id) VALUES (?, ?)",
        (guild_id, user_id),
    )
    db.commit()


def get_user_stats(guild_id: int, user_id: int):
    ensure_user(guild_id, user_id)
    cur.execute(
        "SELECT * FROM user_stats WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    return cur.fetchone()


def format_duration(total_seconds: int) -> str:
    days, remainder = divmod(max(total_seconds, 0), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


# =========================================================
# INTENTS / BOT
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class HonraDinho(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(TicketPanelView())
        self.add_view(TicketActionsView())
        self.add_view(SuggestionView())

        self.tree.add_command(ticket_config_group)
        self.tree.add_command(welcome_config_group)
        self.tree.add_command(logs_config_group)
        self.tree.add_command(suggestions_config_group)
        self.tree.add_command(economy_group)

        synced = await self.tree.sync()
        print(f"{len(synced)} comandos sincronizados com o Discord.")


bot = HonraDinho()


# =========================================================
# AUXILIARES
# =========================================================

def safe_name(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9-]", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return (text or "usuario")[:40]


def topic_value(topic: Optional[str], key: str):
    if not topic:
        return None
    for part in topic.split("|"):
        part = part.strip()
        if part.startswith(key + ":"):
            return part.split(":", 1)[1].strip()
    return None


def ticket_for_user(guild: discord.Guild, user_id: int):
    for channel in guild.text_channels:
        if topic_value(channel.topic, "ticket_user") == str(user_id):
            return channel
    return None


def update_topic_field(topic: Optional[str], key: str, value: str):
    parts = []
    if topic:
        for part in topic.split("|"):
            part = part.strip()
            if not part.startswith(key + ":"):
                parts.append(part)
    parts.append(f"{key}:{value}")
    return " | ".join(parts)


async def make_transcript(channel: discord.TextChannel):
    lines = [
        "HONRADINHO - TRANSCRIPT DE TICKET",
        "=" * 60,
        f"Servidor: {channel.guild.name}",
        f"Canal: #{channel.name}",
        f"Canal ID: {channel.id}",
        "=" * 60,
        "",
    ]
    async for msg in channel.history(limit=None, oldest_first=True):
        ts = msg.created_at.strftime("%d/%m/%Y %H:%M:%S UTC")
        content = msg.content or ""
        lines.append(f"[{ts}] {msg.author} ({msg.author.id}): {content}")
        for att in msg.attachments:
            lines.append(f"  [ANEXO] {att.url}")
    data = "\n".join(lines).encode("utf-8")
    return io.BytesIO(data)


async def send_ticket_log(guild: discord.Guild, embed: discord.Embed, file=None, filename=None):
    cfg = get_guild_config(guild.id)
    channel_id = cfg["ticket_logs_channel_id"]
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return
    try:
        if file:
            await channel.send(embed=embed, file=discord.File(file, filename=filename))
        else:
            await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def send_mod_log(guild: discord.Guild, embed: discord.Embed):
    cfg = get_guild_config(guild.id)
    channel_id = cfg["moderation_logs_channel_id"]
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass


def format_template(text: str, member: discord.Member):
    return (
        text.replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{server}", member.guild.name)
        .replace("{members}", str(member.guild.member_count))
    )


# =========================================================
# EVENTOS
# =========================================================

@bot.event
async def on_ready():
    print("=" * 50)
    print(f"BOT ONLINE: {bot.user}")
    print(f"ID: {bot.user.id if bot.user else 'N/A'}")
    print("=" * 50)
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="/ajuda | HonraDinho")
    )


@bot.event
async def on_guild_remove(guild: discord.Guild):
    cur.execute("DELETE FROM guild_config WHERE guild_id = ?", (guild.id,))
    cur.execute("DELETE FROM user_stats WHERE guild_id = ?", (guild.id,))
    cur.execute("DELETE FROM warnings WHERE guild_id = ?", (guild.id,))
    db.commit()

    stale_keys = [key for key in xp_cooldowns if key[0] == guild.id]
    for key in stale_keys:
        xp_cooldowns.pop(key, None)


@bot.event
async def on_member_join(member: discord.Member):
    cfg = get_guild_config(member.guild.id)

    if cfg["autorole_id"]:
        role = member.guild.get_role(cfg["autorole_id"])
        if role:
            try:
                await member.add_roles(role, reason="Autorole HonraDinho")
            except discord.Forbidden:
                pass

    if cfg["welcome_channel_id"]:
        channel = member.guild.get_channel(cfg["welcome_channel_id"])
        if isinstance(channel, discord.TextChannel):
            embed = discord.Embed(
                title="👋 Novo membro!",
                description=format_template(cfg["welcome_message"], member),
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)

    embed = discord.Embed(
        title="📥 Membro entrou",
        description=f"{member.mention} entrou no servidor.",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="ID", value=str(member.id))
    await send_mod_log(member.guild, embed)


@bot.event
async def on_member_remove(member: discord.Member):
    cfg = get_guild_config(member.guild.id)

    if cfg["goodbye_channel_id"]:
        channel = member.guild.get_channel(cfg["goodbye_channel_id"])
        if isinstance(channel, discord.TextChannel):
            text = (
                cfg["goodbye_message"]
                .replace("{user}", member.name)
                .replace("{username}", member.name)
                .replace("{server}", member.guild.name)
                .replace("{members}", str(member.guild.member_count))
            )
            embed = discord.Embed(
                title="👋 Membro saiu",
                description=text,
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)

    embed = discord.Embed(
        title="📤 Membro saiu",
        description=f"**{member}** saiu do servidor.",
        color=discord.Color.red(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="ID", value=str(member.id))
    await send_mod_log(member.guild, embed)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    now = discord.utils.utcnow()
    cooldown_key = (message.guild.id, message.author.id)
    last_gain = xp_cooldowns.get(cooldown_key)
    if last_gain and (now - last_gain).total_seconds() < XP_COOLDOWN_SECONDS:
        await bot.process_commands(message)
        return

    xp_cooldowns[cooldown_key] = now
    ensure_user(message.guild.id, message.author.id)
    stats = get_user_stats(message.guild.id, message.author.id)

    gain = random.randint(5, 12)
    new_xp = stats["xp"] + gain
    current_level = stats["level"]
    needed = (current_level + 1) * 100

    if new_xp >= needed:
        current_level += 1
        new_xp -= needed
        cur.execute(
            "UPDATE user_stats SET xp = ?, level = ? WHERE guild_id = ? AND user_id = ?",
            (new_xp, current_level, message.guild.id, message.author.id),
        )
        db.commit()
        try:
            await message.channel.send(
                f"🎉 {message.author.mention}, você chegou ao **nível {current_level}**!"
            )
        except discord.HTTPException:
            pass
    else:
        cur.execute(
            "UPDATE user_stats SET xp = ? WHERE guild_id = ? AND user_id = ?",
            (new_xp, message.guild.id, message.author.id),
        )
        db.commit()

    await bot.process_commands(message)


@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    embed = discord.Embed(
        title="🗑️ Mensagem apagada",
        color=discord.Color.orange(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Autor", value=message.author.mention, inline=False)
    embed.add_field(name="Canal", value=message.channel.mention, inline=False)
    embed.add_field(name="Conteúdo", value=(message.content or "*sem texto*")[:1024], inline=False)
    await send_mod_log(message.guild, embed)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot or before.content == after.content:
        return
    embed = discord.Embed(
        title="✏️ Mensagem editada",
        color=discord.Color.gold(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Autor", value=before.author.mention, inline=False)
    embed.add_field(name="Antes", value=(before.content or "*vazio*")[:1024], inline=False)
    embed.add_field(name="Depois", value=(after.content or "*vazio*")[:1024], inline=False)
    await send_mod_log(before.guild, embed)


# =========================================================
# TICKETS V2
# =========================================================

async def create_ticket(interaction: discord.Interaction, ticket_type: str, emoji: str):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ Use em um servidor.", ephemeral=True)
        return

    existing = ticket_for_user(guild, interaction.user.id)
    if existing:
        await interaction.response.send_message(
            f"⚠️ Você já possui um ticket aberto: {existing.mention}",
            ephemeral=True
        )
        return

    cfg = get_guild_config(guild.id)
    staff_role = guild.get_role(cfg["ticket_staff_role_id"]) if cfg["ticket_staff_role_id"] else None

    if not staff_role:
        await interaction.response.send_message(
            "❌ O cargo da Staff ainda não foi configurado.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    category = guild.get_channel(cfg["ticket_category_id"]) if cfg["ticket_category_id"] else None
    if not isinstance(category, discord.CategoryChannel):
        try:
            category = await guild.create_category("TICKETS", reason="HonraDinho Tickets")
            set_guild_config(guild.id, "ticket_category_id", category.id)
        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão para criar categoria.", ephemeral=True)
            return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            attach_files=True, embed_links=True
        ),
        staff_role: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            attach_files=True, embed_links=True
        )
    }

    if guild.me:
        overwrites[guild.me] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            manage_channels=True, manage_messages=True
        )

    name = f"{safe_name(ticket_type)}-{safe_name(interaction.user.name)}"
    topic = f"ticket_user:{interaction.user.id} | tipo:{ticket_type} | staff:0"

    try:
        channel = await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            topic=topic,
            reason=f"Ticket {ticket_type} aberto por {interaction.user}",
        )
    except discord.Forbidden:
        await interaction.followup.send("❌ Não tenho permissão para criar o canal.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"{emoji} Ticket de {ticket_type}",
        description=(
            f"Olá {interaction.user.mention}!\n\n"
            "Explique abaixo o motivo do atendimento.\n"
            f"{staff_role.mention}, há um novo ticket aguardando."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="👤 Usuário", value=interaction.user.mention)
    embed.add_field(name="📂 Categoria", value=ticket_type)
    embed.add_field(name="🙋 Atendimento", value="Aguardando Staff", inline=False)
    embed.set_footer(text="HonraDinho • Tickets V2")

    await channel.send(
        content=f"{interaction.user.mention} {staff_role.mention}",
        embed=embed,
        view=TicketActionsView(),
        allowed_mentions=discord.AllowedMentions(users=True, roles=True),
    )

    await interaction.followup.send(f"✅ Ticket criado: {channel.mention}", ephemeral=True)

    log = discord.Embed(
        title="🎫 Ticket aberto",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )
    log.add_field(name="Usuário", value=interaction.user.mention)
    log.add_field(name="Tipo", value=ticket_type)
    log.add_field(name="Canal", value=channel.mention)
    await send_ticket_log(guild, log)


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Suporte", description="Ajuda e dúvidas.", emoji="🆘", value="Suporte"),
            discord.SelectOption(label="Denúncia", description="Denunciar membro ou problema.", emoji="🚨", value="Denúncia"),
            discord.SelectOption(label="Compra", description="Assuntos comerciais.", emoji="🛒", value="Compra"),
            discord.SelectOption(label="Parceria", description="Parcerias e propostas.", emoji="🤝", value="Parceria"),
        ]
        super().__init__(
            placeholder="Selecione o motivo do ticket...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="honradinho:ticket_select",
        )

    async def callback(self, interaction: discord.Interaction):
        ticket_type = self.values[0]
        emojis = {"Suporte": "🆘", "Denúncia": "🚨", "Compra": "🛒", "Parceria": "🤝"}
        await create_ticket(interaction, ticket_type, emojis[ticket_type])


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


class TicketActionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Assumir", emoji="🙋",
        style=discord.ButtonStyle.success,
        custom_id="honradinho:ticket_claim"
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not isinstance(channel, discord.TextChannel):
            return

        user_id = topic_value(channel.topic, "ticket_user")
        current_staff = topic_value(channel.topic, "staff")
        if not user_id:
            await interaction.response.send_message("❌ Este canal não é um ticket.", ephemeral=True)
            return

        cfg = get_guild_config(guild.id)
        staff_role = guild.get_role(cfg["ticket_staff_role_id"]) if cfg["ticket_staff_role_id"] else None
        member = interaction.user

        authorized = member.guild_permissions.manage_channels or (staff_role and staff_role in member.roles)
        if not authorized:
            await interaction.response.send_message("❌ Apenas a Staff pode assumir tickets.", ephemeral=True)
            return

        if current_staff and current_staff != "0":
            existing = guild.get_member(int(current_staff))
            await interaction.response.send_message(
                f"⚠️ Já assumido por {existing.mention if existing else current_staff}.",
                ephemeral=True
            )
            return

        await channel.edit(
            topic=update_topic_field(channel.topic, "staff", str(member.id)),
            reason="Ticket assumido",
        )
        await interaction.response.send_message(f"🙋 Ticket assumido por {member.mention}.")

    @discord.ui.button(
        label="Transcript", emoji="📄",
        style=discord.ButtonStyle.secondary,
        custom_id="honradinho:ticket_transcript"
    )
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) or not topic_value(channel.topic, "ticket_user"):
            await interaction.response.send_message("❌ Este canal não é um ticket.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        data = await make_transcript(channel)
        await interaction.followup.send(
            "📄 Transcript:",
            file=discord.File(data, filename=f"{channel.name}.txt"),
            ephemeral=True
        )

    @discord.ui.button(
        label="Fechar", emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="honradinho:ticket_close"
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not isinstance(channel, discord.TextChannel):
            return

        user_id = topic_value(channel.topic, "ticket_user")
        staff_id = topic_value(channel.topic, "staff")
        ticket_type = topic_value(channel.topic, "tipo")
        if not user_id:
            await interaction.response.send_message("❌ Este canal não é um ticket.", ephemeral=True)
            return

        cfg = get_guild_config(guild.id)
        staff_role = guild.get_role(cfg["ticket_staff_role_id"]) if cfg["ticket_staff_role_id"] else None
        can_close = (
            interaction.user.id == int(user_id)
            or interaction.user.guild_permissions.manage_channels
            or (staff_role and staff_role in interaction.user.roles)
        )
        if not can_close:
            await interaction.response.send_message("❌ Você não pode fechar este ticket.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 Salvando transcript e fechando ticket...")

        transcript = await make_transcript(channel)
        data = transcript.getvalue()

        opener = guild.get_member(int(user_id))
        staff = guild.get_member(int(staff_id)) if staff_id and staff_id != "0" else None

        log = discord.Embed(
            title="🔒 Ticket fechado",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        log.add_field(name="Usuário", value=opener.mention if opener else user_id)
        log.add_field(name="Categoria", value=ticket_type or "Desconhecida")
        log.add_field(name="Atendido por", value=staff.mention if staff else "Não assumido")
        log.add_field(name="Fechado por", value=interaction.user.mention, inline=False)

        await send_ticket_log(
            guild,
            log,
            io.BytesIO(data),
            f"{channel.name}.txt"
        )

        if opener:
            try:
                await opener.send(
                    embed=discord.Embed(
                        title="🎫 Seu ticket foi fechado",
                        description=f"Servidor: **{guild.name}**\nCategoria: **{ticket_type or 'Desconhecida'}**",
                        color=discord.Color.blurple(),
                    ),
                    file=discord.File(io.BytesIO(data), filename=f"{channel.name}.txt"),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=3))
        try:
            await channel.delete(reason=f"Ticket fechado por {interaction.user}")
        except discord.Forbidden:
            pass


# =========================================================
# SUGESTÕES
# =========================================================

class SuggestionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Aprovar", emoji="✅", style=discord.ButtonStyle.success, custom_id="honradinho:suggest_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Apenas moderadores podem aprovar.", ephemeral=True)
            return
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.set_footer(text=f"Aprovada por {interaction.user}")
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message("✅ Sugestão aprovada.", ephemeral=True)

    @discord.ui.button(label="Recusar", emoji="❌", style=discord.ButtonStyle.danger, custom_id="honradinho:suggest_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Apenas moderadores podem recusar.", ephemeral=True)
            return
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"Recusada por {interaction.user}")
        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message("❌ Sugestão recusada.", ephemeral=True)


# =========================================================
# GRUPOS DE CONFIGURAÇÃO
# =========================================================

ticket_config_group = app_commands.Group(
    name="ticket-config",
    description="Configura o sistema de tickets."
)

welcome_config_group = app_commands.Group(
    name="welcome-config",
    description="Configura boas-vindas, despedida e autorole."
)

logs_config_group = app_commands.Group(
    name="logs-config",
    description="Configura logs do servidor."
)

suggestions_config_group = app_commands.Group(
    name="sugestoes-config",
    description="Configura o sistema de sugestões."
)

economy_group = app_commands.Group(
    name="economia",
    description="Comandos de economia."
)


# =========================================================
# CONFIG: TICKETS
# =========================================================

@ticket_config_group.command(name="staff", description="Define o cargo da Staff.")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_staff(interaction: discord.Interaction, cargo: discord.Role):
    set_guild_config(interaction.guild.id, "ticket_staff_role_id", cargo.id)
    await interaction.response.send_message(f"✅ Staff: {cargo.mention}", ephemeral=True)


@ticket_config_group.command(name="logs", description="Define o canal de logs de tickets.")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_logs(interaction: discord.Interaction, canal: discord.TextChannel):
    set_guild_config(interaction.guild.id, "ticket_logs_channel_id", canal.id)
    await interaction.response.send_message(f"✅ Logs de tickets: {canal.mention}", ephemeral=True)


@ticket_config_group.command(name="categoria", description="Define a categoria dos tickets.")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_category(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    set_guild_config(interaction.guild.id, "ticket_category_id", categoria.id)
    await interaction.response.send_message(f"✅ Categoria: **{categoria.name}**", ephemeral=True)


# =========================================================
# CONFIG: WELCOME
# =========================================================

@welcome_config_group.command(name="canal", description="Define o canal de boas-vindas.")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_channel(interaction: discord.Interaction, canal: discord.TextChannel):
    set_guild_config(interaction.guild.id, "welcome_channel_id", canal.id)
    await interaction.response.send_message(f"✅ Boas-vindas: {canal.mention}", ephemeral=True)


@welcome_config_group.command(name="cargo", description="Define o autorole.")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_role(interaction: discord.Interaction, cargo: discord.Role):
    set_guild_config(interaction.guild.id, "autorole_id", cargo.id)
    await interaction.response.send_message(f"✅ Autorole: {cargo.mention}", ephemeral=True)


@welcome_config_group.command(name="mensagem", description="Define a mensagem de boas-vindas.")
@app_commands.checks.has_permissions(administrator=True)
async def welcome_message(interaction: discord.Interaction, mensagem: str):
    set_guild_config(interaction.guild.id, "welcome_message", mensagem)
    await interaction.response.send_message(
        "✅ Mensagem salva. Variáveis: `{user}` `{username}` `{server}` `{members}`",
        ephemeral=True
    )


@welcome_config_group.command(name="despedida-canal", description="Define o canal de despedidas.")
@app_commands.checks.has_permissions(administrator=True)
async def goodbye_channel(interaction: discord.Interaction, canal: discord.TextChannel):
    set_guild_config(interaction.guild.id, "goodbye_channel_id", canal.id)
    await interaction.response.send_message(f"✅ Despedidas: {canal.mention}", ephemeral=True)


@welcome_config_group.command(name="despedida-mensagem", description="Define a mensagem de despedida.")
@app_commands.checks.has_permissions(administrator=True)
async def goodbye_message(interaction: discord.Interaction, mensagem: str):
    set_guild_config(interaction.guild.id, "goodbye_message", mensagem)
    await interaction.response.send_message("✅ Mensagem de despedida salva.", ephemeral=True)


# =========================================================
# CONFIG: LOGS / SUGESTÕES
# =========================================================

@logs_config_group.command(name="moderacao", description="Define o canal de logs de moderação.")
@app_commands.checks.has_permissions(administrator=True)
async def moderation_logs(interaction: discord.Interaction, canal: discord.TextChannel):
    set_guild_config(interaction.guild.id, "moderation_logs_channel_id", canal.id)
    await interaction.response.send_message(f"✅ Logs de moderação: {canal.mention}", ephemeral=True)


@suggestions_config_group.command(name="canal", description="Define o canal de sugestões.")
@app_commands.checks.has_permissions(administrator=True)
async def suggestions_channel(interaction: discord.Interaction, canal: discord.TextChannel):
    set_guild_config(interaction.guild.id, "suggestions_channel_id", canal.id)
    await interaction.response.send_message(f"✅ Sugestões: {canal.mention}", ephemeral=True)


@bot.tree.command(name="configuracao", description="Mostra a configuração atual do HonraDinho.")
@app_commands.checks.has_permissions(administrator=True)
async def configuration(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
        return
    cfg = get_guild_config(guild.id)

    def channel_value(field: str) -> str:
        return f"<#{cfg[field]}>" if cfg[field] else "Não configurado"

    def role_value(field: str) -> str:
        return f"<@&{cfg[field]}>" if cfg[field] else "Não configurado"

    embed = discord.Embed(
        title="⚙️ Configuração do HonraDinho",
        description="Resumo dos sistemas configuráveis deste servidor.",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="🎫 Tickets",
        value=(
            f"Staff: {role_value('ticket_staff_role_id')}\n"
            f"Logs: {channel_value('ticket_logs_channel_id')}\n"
            f"Categoria: {channel_value('ticket_category_id')}"
        ),
        inline=False,
    )
    embed.add_field(
        name="👋 Comunidade",
        value=(
            f"Boas-vindas: {channel_value('welcome_channel_id')}\n"
            f"Despedidas: {channel_value('goodbye_channel_id')}\n"
            f"Autorole: {role_value('autorole_id')}"
        ),
        inline=False,
    )
    embed.add_field(
        name="🧾 Canais",
        value=(
            f"Moderação: {channel_value('moderation_logs_channel_id')}\n"
            f"Sugestões: {channel_value('suggestions_channel_id')}"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================================
# COMANDOS: TICKET / INFO
# =========================================================

@bot.tree.command(name="ticket", description="Envia o painel de tickets.")
@app_commands.checks.has_permissions(manage_channels=True)
async def ticket(interaction: discord.Interaction):
    cfg = get_guild_config(interaction.guild.id)
    if not cfg["ticket_staff_role_id"]:
        await interaction.response.send_message(
            "❌ Configure primeiro `/ticket-config staff`.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="🎫 Central de Atendimento",
        description="Selecione abaixo o motivo do seu ticket.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="🆘 Suporte", value="Ajuda e dúvidas.", inline=True)
    embed.add_field(name="🚨 Denúncia", value="Denúncias e problemas.", inline=True)
    embed.add_field(name="🛒 Compra", value="Assuntos comerciais.", inline=True)
    embed.add_field(name="🤝 Parceria", value="Parcerias e propostas.", inline=True)
    await interaction.response.send_message(embed=embed, view=TicketPanelView())


@bot.tree.command(name="ping", description="Mostra a latência do HonraDinho.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=discord.Embed(
            title="🏓 Pong!",
            description=f"Latência: **{round(bot.latency * 1000)}ms**",
            color=discord.Color.blurple(),
        )
    )


@bot.tree.command(name="botinfo", description="Mostra informações do HonraDinho.")
async def botinfo(interaction: discord.Interaction):
    users = sum(g.member_count or 0 for g in bot.guilds)
    embed = discord.Embed(title="🤖 HonraDinho", color=discord.Color.blurple())
    embed.add_field(name="Servidores", value=str(len(bot.guilds)))
    embed.add_field(name="Usuários", value=str(users))
    embed.add_field(name="Latência", value=f"{round(bot.latency * 1000)}ms")
    embed.add_field(name="Biblioteca", value=f"discord.py {discord.__version__}", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="uptime", description="Mostra há quanto tempo o HonraDinho está online.")
async def uptime(interaction: discord.Interaction):
    seconds = int((discord.utils.utcnow() - BOT_STARTED_AT).total_seconds())
    await interaction.response.send_message(
        embed=discord.Embed(
            title="⏱️ Uptime",
            description=f"Online há **{format_duration(seconds)}**.",
            color=discord.Color.green(),
        )
    )


@bot.tree.command(name="convite", description="Mostra os links oficiais do HonraDinho.")
async def invite(interaction: discord.Interaction):
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Adicionar ao servidor", emoji="🚀", url=INVITE_URL))
    view.add_item(discord.ui.Button(label="Servidor de suporte", emoji="💬", url=SUPPORT_URL))
    view.add_item(discord.ui.Button(label="Site oficial", emoji="🌐", url=SITE_URL))
    await interaction.response.send_message(
        embed=discord.Embed(
            title="🤖 HonraDinho",
            description="Links oficiais para instalar o bot, pedir ajuda e acompanhar o projeto.",
            color=discord.Color.blurple(),
        ),
        view=view,
        ephemeral=True,
    )


@bot.tree.command(name="privacidade", description="Mostra a política de privacidade e os termos do bot.")
async def privacy(interaction: discord.Interaction):
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Privacidade", emoji="🔒", url=PRIVACY_URL))
    view.add_item(discord.ui.Button(label="Termos", emoji="📄", url=TERMS_URL))
    view.add_item(discord.ui.Button(label="Solicitar suporte", emoji="💬", url=SUPPORT_URL))
    await interaction.response.send_message(
        "Consulte como o HonraDinho trata dados ou peça ajuda para uma solicitação de dados.",
        view=view,
        ephemeral=True,
    )


@bot.tree.command(name="dados", description="Mostra um resumo dos seus dados salvos neste servidor.")
async def my_data(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
        return

    cur.execute(
        "SELECT xp, level, balance, last_daily FROM user_stats WHERE guild_id = ? AND user_id = ?",
        (guild.id, interaction.user.id),
    )
    stats = cur.fetchone()
    cur.execute(
        "SELECT COUNT(*) AS total FROM warnings WHERE guild_id = ? AND user_id = ?",
        (guild.id, interaction.user.id),
    )
    warning_count = cur.fetchone()["total"]

    embed = discord.Embed(
        title="🔐 Seus dados no HonraDinho",
        description=f"Resumo do que está associado a você em **{guild.name}**.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="ID do usuário", value=str(interaction.user.id), inline=False)
    if stats:
        embed.add_field(name="Nível / XP", value=f"{stats['level']} / {stats['xp']}")
        embed.add_field(name="Saldo", value=f"{stats['balance']} moedas")
        embed.add_field(name="Último daily", value=stats["last_daily"] or "Nunca", inline=False)
    else:
        embed.add_field(name="Níveis e economia", value="Nenhum registro salvo.", inline=False)
    embed.add_field(name="Advertências", value=str(warning_count))
    embed.add_field(
        name="Privacidade e exclusão",
        value=f"[Política de Privacidade]({PRIVACY_URL}) • [Servidor de suporte]({SUPPORT_URL})",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="server", description="Mostra informações do servidor.")
async def server(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("❌ Use em um servidor.", ephemeral=True)
        return
    embed = discord.Embed(title=f"📊 {guild.name}", color=discord.Color.blurple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👑 Dono", value=guild.owner.mention if guild.owner else "Desconhecido")
    embed.add_field(name="👥 Membros", value=str(guild.member_count))
    embed.add_field(name="💬 Canais", value=str(len(guild.channels)))
    embed.add_field(name="🎭 Cargos", value=str(len(guild.roles)))
    embed.add_field(name="🆔 ID", value=str(guild.id))
    embed.add_field(name="📅 Criado", value=discord.utils.format_dt(guild.created_at, style="D"))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="userinfo", description="Mostra informações de um membro.")
async def userinfo(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    membro = membro or interaction.user
    embed = discord.Embed(title=f"👤 {membro}", color=discord.Color.blurple())
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.add_field(name="Nome", value=membro.name)
    embed.add_field(name="ID", value=str(membro.id))
    embed.add_field(name="Conta criada", value=discord.utils.format_dt(membro.created_at, style="D"), inline=False)
    if membro.joined_at:
        embed.add_field(name="Entrou no servidor", value=discord.utils.format_dt(membro.joined_at, style="D"), inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="Mostra o avatar de um usuário.")
async def avatar(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    membro = membro or interaction.user
    embed = discord.Embed(title=f"🖼️ Avatar de {membro.display_name}", color=discord.Color.blurple())
    embed.set_image(url=membro.display_avatar.url)
    await interaction.response.send_message(embed=embed)


# =========================================================
# MODERAÇÃO
# =========================================================

@bot.tree.command(name="clear", description="Apaga mensagens do canal.")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, quantidade: app_commands.Range[int, 1, 100]):
    channel = interaction.channel
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        await interaction.response.send_message("❌ Não funciona aqui.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await channel.purge(limit=quantidade)
    await interaction.followup.send(f"🧹 **{len(deleted)} mensagens** apagadas.", ephemeral=True)


@bot.tree.command(name="kick", description="Expulsa um membro.")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não informado."):
    try:
        await membro.kick(reason=motivo)
        embed = discord.Embed(title="👢 Membro expulso", color=discord.Color.orange())
        embed.add_field(name="Usuário", value=str(membro))
        embed.add_field(name="Moderador", value=interaction.user.mention)
        embed.add_field(name="Motivo", value=motivo, inline=False)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(interaction.guild, embed)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissão para expulsar.", ephemeral=True)


@bot.tree.command(name="ban", description="Bane um membro.")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não informado."):
    try:
        await membro.ban(reason=motivo)
        embed = discord.Embed(title="🔨 Membro banido", color=discord.Color.red())
        embed.add_field(name="Usuário", value=str(membro))
        embed.add_field(name="Moderador", value=interaction.user.mention)
        embed.add_field(name="Motivo", value=motivo, inline=False)
        await interaction.response.send_message(embed=embed)
        await send_mod_log(interaction.guild, embed)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissão para banir.", ephemeral=True)


@bot.tree.command(name="unban", description="Desbane um usuário pelo ID.")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, usuario_id: str, motivo: str = "Não informado."):
    try:
        user = await bot.fetch_user(int(usuario_id))
        await interaction.guild.unban(user, reason=motivo)
        await interaction.response.send_message(f"🔓 **{user}** foi desbanido.")
    except (ValueError, discord.NotFound):
        await interaction.response.send_message("❌ Usuário/ID não encontrado.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissão para desbanir.", ephemeral=True)


@bot.tree.command(name="timeout", description="Aplica timeout em um membro.")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(
    interaction: discord.Interaction,
    membro: discord.Member,
    minutos: app_commands.Range[int, 1, 40320],
    motivo: str = "Não informado."
):
    until = discord.utils.utcnow() + datetime.timedelta(minutes=minutos)
    try:
        await membro.timeout(until, reason=motivo)
        await interaction.response.send_message(
            f"🔇 {membro.mention} recebeu timeout por **{minutos} minuto(s)**."
        )
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não consigo aplicar timeout nesse membro.", ephemeral=True)


@bot.tree.command(name="untimeout", description="Remove o timeout de um membro.")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, membro: discord.Member):
    try:
        await membro.timeout(None, reason=f"Timeout removido por {interaction.user}")
        await interaction.response.send_message(f"🔊 Timeout de {membro.mention} removido.")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não consigo remover o timeout.", ephemeral=True)


@bot.tree.command(name="warn", description="Adiciona um aviso a um membro.")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, membro: discord.Member, motivo: str):
    cur.execute(
        "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            interaction.guild.id,
            membro.id,
            interaction.user.id,
            motivo,
            discord.utils.utcnow().isoformat(),
        ),
    )
    db.commit()
    await interaction.response.send_message(f"⚠️ {membro.mention} recebeu um aviso: **{motivo}**")


@bot.tree.command(name="warnings", description="Mostra os avisos de um membro.")
@app_commands.checks.has_permissions(moderate_members=True)
async def warnings(interaction: discord.Interaction, membro: discord.Member):
    cur.execute(
        "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 10",
        (interaction.guild.id, membro.id),
    )
    rows = cur.fetchall()
    if not rows:
        await interaction.response.send_message("✅ Esse membro não possui avisos.", ephemeral=True)
        return
    text = "\n".join(
        f"`#{r['id']}` • {r['reason']} • moderador <@{r['moderator_id']}>"
        for r in rows
    )
    await interaction.response.send_message(
        embed=discord.Embed(title=f"⚠️ Avisos de {membro}", description=text, color=discord.Color.orange())
    )


@bot.tree.command(name="unwarn", description="Remove uma advertência pelo número.")
@app_commands.checks.has_permissions(moderate_members=True)
async def unwarn(interaction: discord.Interaction, aviso_id: int):
    cur.execute(
        "SELECT user_id FROM warnings WHERE id = ? AND guild_id = ?",
        (aviso_id, interaction.guild.id),
    )
    warning = cur.fetchone()
    if not warning:
        await interaction.response.send_message("❌ Advertência não encontrada neste servidor.", ephemeral=True)
        return
    cur.execute("DELETE FROM warnings WHERE id = ? AND guild_id = ?", (aviso_id, interaction.guild.id))
    db.commit()
    await interaction.response.send_message(
        f"✅ Advertência `#{aviso_id}` de <@{warning['user_id']}> removida.",
        ephemeral=True,
    )


@bot.tree.command(name="clearwarnings", description="Remove todas as advertências de um membro.")
@app_commands.checks.has_permissions(moderate_members=True)
async def clearwarnings(interaction: discord.Interaction, membro: discord.Member):
    cur.execute(
        "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
        (interaction.guild.id, membro.id),
    )
    removed = cur.rowcount
    db.commit()
    await interaction.response.send_message(
        f"✅ {removed} advertência(s) removida(s) de {membro.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="slowmode", description="Define o modo lento do canal em segundos.")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, segundos: app_commands.Range[int, 0, 21600]):
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ Use este comando em um canal de texto.", ephemeral=True)
        return
    try:
        await channel.edit(slowmode_delay=segundos, reason=f"Alterado por {interaction.user}")
        status = "desativado" if segundos == 0 else f"definido para **{segundos}s**"
        await interaction.response.send_message(f"⏱️ Modo lento {status}.")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissão para editar este canal.", ephemeral=True)


@bot.tree.command(name="lock", description="Bloqueia o envio de mensagens no canal para @everyone.")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock_channel(interaction: discord.Interaction):
    channel = interaction.channel
    guild = interaction.guild
    if not guild or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ Use este comando em um canal de texto.", ephemeral=True)
        return
    overwrite = channel.overwrites_for(guild.default_role)
    overwrite.send_messages = False
    try:
        await channel.set_permissions(
            guild.default_role,
            overwrite=overwrite,
            reason=f"Canal bloqueado por {interaction.user}",
        )
        await interaction.response.send_message("🔒 Canal bloqueado para `@everyone`.")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissão para bloquear este canal.", ephemeral=True)


@bot.tree.command(name="unlock", description="Remove o bloqueio de mensagens do canal para @everyone.")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock_channel(interaction: discord.Interaction):
    channel = interaction.channel
    guild = interaction.guild
    if not guild or not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ Use este comando em um canal de texto.", ephemeral=True)
        return
    overwrite = channel.overwrites_for(guild.default_role)
    overwrite.send_messages = None
    try:
        await channel.set_permissions(
            guild.default_role,
            overwrite=overwrite,
            reason=f"Canal desbloqueado por {interaction.user}",
        )
        await interaction.response.send_message("🔓 Bloqueio do canal removido para `@everyone`.")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Não tenho permissão para desbloquear este canal.", ephemeral=True)


# =========================================================
# NÍVEIS
# =========================================================

@bot.tree.command(name="rank", description="Mostra seu nível e XP.")
async def rank(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    membro = membro or interaction.user
    stats = get_user_stats(interaction.guild.id, membro.id)
    needed = (stats["level"] + 1) * 100
    embed = discord.Embed(title=f"🏆 Rank de {membro.display_name}", color=discord.Color.blurple())
    embed.add_field(name="Nível", value=str(stats["level"]))
    embed.add_field(name="XP", value=f"{stats['xp']}/{needed}")
    embed.set_thumbnail(url=membro.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="leaderboard", description="Mostra o ranking de níveis.")
async def leaderboard(interaction: discord.Interaction):
    cur.execute(
        "SELECT user_id, level, xp FROM user_stats WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10",
        (interaction.guild.id,),
    )
    rows = cur.fetchall()
    if not rows:
        await interaction.response.send_message("Ainda não há ranking.", ephemeral=True)
        return
    lines = []
    for i, row in enumerate(rows, 1):
        member = interaction.guild.get_member(row["user_id"])
        name = member.display_name if member else str(row["user_id"])
        lines.append(f"**{i}.** {name} — nível **{row['level']}** ({row['xp']} XP)")
    await interaction.response.send_message(
        embed=discord.Embed(title="🏆 Leaderboard", description="\n".join(lines), color=discord.Color.gold())
    )


# =========================================================
# ECONOMIA
# =========================================================

@economy_group.command(name="saldo", description="Mostra seu saldo.")
async def balance(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    membro = membro or interaction.user
    stats = get_user_stats(interaction.guild.id, membro.id)
    await interaction.response.send_message(f"💰 {membro.mention} possui **{stats['balance']} moedas**.")


@economy_group.command(name="daily", description="Recebe sua recompensa diária.")
async def daily(interaction: discord.Interaction):
    stats = get_user_stats(interaction.guild.id, interaction.user.id)
    today = datetime.date.today().isoformat()
    if stats["last_daily"] == today:
        await interaction.response.send_message("⏳ Você já recebeu sua recompensa de hoje.", ephemeral=True)
        return
    amount = random.randint(100, 250)
    cur.execute(
        "UPDATE user_stats SET balance = balance + ?, last_daily = ? WHERE guild_id = ? AND user_id = ?",
        (amount, today, interaction.guild.id, interaction.user.id),
    )
    db.commit()
    await interaction.response.send_message(f"🎁 Você recebeu **{amount} moedas**!")


@economy_group.command(name="pagar", description="Transfere moedas para outro membro.")
async def pay(interaction: discord.Interaction, membro: discord.Member, quantidade: app_commands.Range[int, 1, 1000000]):
    if membro.bot or membro.id == interaction.user.id:
        await interaction.response.send_message("❌ Destinatário inválido.", ephemeral=True)
        return
    sender = get_user_stats(interaction.guild.id, interaction.user.id)
    if sender["balance"] < quantidade:
        await interaction.response.send_message("❌ Saldo insuficiente.", ephemeral=True)
        return
    ensure_user(interaction.guild.id, membro.id)
    cur.execute(
        "UPDATE user_stats SET balance = balance - ? WHERE guild_id = ? AND user_id = ?",
        (quantidade, interaction.guild.id, interaction.user.id),
    )
    cur.execute(
        "UPDATE user_stats SET balance = balance + ? WHERE guild_id = ? AND user_id = ?",
        (quantidade, interaction.guild.id, membro.id),
    )
    db.commit()
    await interaction.response.send_message(f"💸 Você enviou **{quantidade} moedas** para {membro.mention}.")


# =========================================================
# SUGESTÕES / ENQUETES
# =========================================================

@bot.tree.command(name="sugerir", description="Envia uma sugestão.")
async def suggest(interaction: discord.Interaction, sugestao: str):
    cfg = get_guild_config(interaction.guild.id)
    channel = interaction.guild.get_channel(cfg["suggestions_channel_id"]) if cfg["suggestions_channel_id"] else None
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("❌ O canal de sugestões não foi configurado.", ephemeral=True)
        return

    embed = discord.Embed(
        title="💡 Nova sugestão",
        description=sugestao,
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
    msg = await channel.send(embed=embed, view=SuggestionView())
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")
    await interaction.response.send_message(f"✅ Sugestão enviada em {channel.mention}.", ephemeral=True)


@bot.tree.command(name="enquete", description="Cria uma enquete simples.")
@app_commands.checks.has_permissions(manage_messages=True)
async def poll(
    interaction: discord.Interaction,
    pergunta: str,
    opcao1: str,
    opcao2: str,
    opcao3: Optional[str] = None,
    opcao4: Optional[str] = None,
):
    options = [opcao1, opcao2]
    if opcao3:
        options.append(opcao3)
    if opcao4:
        options.append(opcao4)

    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    description = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))

    embed = discord.Embed(
        title=f"📊 {pergunta}",
        description=description,
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=f"Enquete criada por {interaction.user}")
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])


# =========================================================
# AJUDA
# =========================================================

@bot.tree.command(name="ajuda", description="Mostra os comandos do HonraDinho.")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 HonraDinho — Central de Ajuda",
        description="Principais comandos disponíveis:",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="📊 Informações",
        value="`/ping` `/botinfo` `/server` `/userinfo` `/avatar` `/uptime` `/convite` `/privacidade` `/dados`",
        inline=False,
    )
    embed.add_field(
        name="🛡️ Moderação",
        value=(
            "`/clear` `/kick` `/ban` `/unban` `/timeout` `/untimeout` "
            "`/warn` `/warnings` `/unwarn` `/clearwarnings` `/slowmode` `/lock` `/unlock`"
        ),
        inline=False,
    )
    embed.add_field(
        name="🎫 Tickets",
        value="`/ticket` + `/ticket-config ...`",
        inline=False,
    )
    embed.add_field(
        name="👋 Comunidade",
        value="`/welcome-config ...` `/logs-config moderacao` `/sugestoes-config canal` `/configuracao`",
        inline=False,
    )
    embed.add_field(
        name="🏆 Níveis",
        value="`/rank` `/leaderboard`",
        inline=False,
    )
    embed.add_field(
        name="💰 Economia",
        value="`/economia saldo` `/economia daily` `/economia pagar`",
        inline=False,
    )
    embed.add_field(
        name="💡 Interação",
        value="`/sugerir` `/enquete`",
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


# =========================================================
# ERROS GLOBAIS
# =========================================================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        message = "❌ Você não possui as permissões necessárias."
    else:
        print(f"Erro em comando: {repr(error)}")
        message = "❌ Ocorreu um erro ao executar este comando."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


# =========================================================
# TOKEN
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("A variável DISCORD_TOKEN não foi configurada.")

bot.run(TOKEN)
