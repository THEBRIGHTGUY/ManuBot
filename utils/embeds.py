"""Rich embed builders + a generic paginated view for Discord responses."""

from __future__ import annotations

import discord

from utils.helpers import chunk, truncate

INFO = 0x5865F2
SUCCESS = 0x00C49A
ERROR = 0xED4245
WARN = 0xFEE75C
NEUTRAL = 0x99AAB5
CHAT = 0x9B59B6
TRAIN = 0x1ABC9C


def make_embed(
    title: str = "",
    description: str = "",
    color: int = NEUTRAL,
    author: str = "ManuBot",
    footer: str = "ManuBot",
    fields=None,
    thumbnail: str = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    if author:
        embed.set_author(name=author)
    if footer:
        embed.set_footer(text=footer)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    for name, value, inline in (fields or []):
        embed.add_field(name=name, value=value, inline=inline)
    return embed


def error_embed(message: str, title: str = "Something went wrong") -> discord.Embed:
    return make_embed(title=title, description=message, color=ERROR)


def success_embed(message: str, title: str = "Done") -> discord.Embed:
    return make_embed(title=title, description=message, color=SUCCESS)


def info_embed(message: str, title: str = "Info") -> discord.Embed:
    return make_embed(title=title, description=message, color=INFO)


class Paginator(discord.ui.View):
    """Simple paginated embed viewer. Page size defaults to 12 lines/chunks."""

    def __init__(self, title: str, items, page_size: int = 10, color: int = INFO, author: str = "ManuBot", timeout: float = 120):
        super().__init__(timeout=timeout)
        self.title = title
        self.color = color
        self.author = author
        self.pages = chunk(list(items), page_size)
        self.index = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev.disabled = self.index <= 0
        self.next.disabled = self.index >= len(self.pages) - 1

    def _embed(self) -> discord.Embed:
        current = self.pages[self.index]
        description = []
        for i, item in enumerate(current, start=self.index * len(current) + 1):
            description.append(f"{i}. {truncate(str(item), 150)}")
        embed = make_embed(
            title=self.title,
            description="\n".join(description) or "_Empty_",
            color=self.color,
            author=self.author,
            footer=f"Page {self.index + 1} / {len(self.pages)}",
        )
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index > 0:
            self.index -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self._embed(), view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index < len(self.pages) - 1:
            self.index += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self._embed(), view=self)