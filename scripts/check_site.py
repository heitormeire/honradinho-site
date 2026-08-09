from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
HTML_FILES = ["index.html", "comandos.html", "terms.html", "privacy.html", "404.html"]


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.links: list[dict[str, str]] = []
        self.command_cards = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {key: value or "" for key, value in attrs}
        if element_id := data.get("id"):
            self.ids.append(element_id)
        if tag == "a" and "href" in data:
            self.links.append(data)
        if "data-command-card" in data:
            self.command_cards += 1


def local_target(href: str) -> Path | None:
    if not href or href.startswith("#"):
        return None
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        return None
    path = parsed.path
    if not path:
        return None
    return ROOT / path


def bot_command_count() -> int:
    source = (ROOT / "bot.py").read_text(encoding="utf-8")
    roots = re.findall(r'@bot\.tree\.command\(name="[^"]+"', source)
    grouped = re.findall(r'@\w+_group\.command\(name="[^"]+"', source)
    return len(roots) + len(grouped)


def main() -> int:
    errors: list[str] = []
    command_cards = 0

    for filename in HTML_FILES:
        path = ROOT / filename
        if not path.exists():
            errors.append(f"{filename}: arquivo ausente")
            continue

        parser = PageParser()
        parser.feed(path.read_text(encoding="utf-8"))
        command_cards += parser.command_cards

        duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
        if duplicates:
            errors.append(f"{filename}: IDs duplicados: {', '.join(duplicates)}")

        for link in parser.links:
            href = link.get("href", "")
            target = local_target(href)
            if target is not None and not target.exists():
                errors.append(f"{filename}: link local ausente -> {href}")
            if link.get("target") == "_blank":
                rel = set(link.get("rel", "").split())
                if "noopener" not in rel:
                    errors.append(f"{filename}: target=_blank sem rel=noopener -> {href}")

    expected = bot_command_count()
    if command_cards != expected:
        errors.append(f"comandos.html: {command_cards} cards para {expected} comandos do bot")

    if errors:
        print("Site check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Site check OK: {len(HTML_FILES)} páginas e {expected} comandos sincronizados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
