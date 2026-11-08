import math
import os
from pathlib import Path
import re
import subprocess
import sys

# ==========================================
# AUTO .VENV CHECK & BOOTSTRAPPER
# ==========================================
SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent
VENV_DIR = SCRIPT_DIR / ".venv"

if sys.platform == "win32":
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"

# Verify whether we're currently executing inside the local .venv
is_inside_venv = Path(sys.prefix).resolve() == VENV_DIR.resolve()

if not is_inside_venv:
    if not VENV_DIR.exists() or not VENV_PYTHON.exists():
        print("[⚙️] First run detected. Creating '.venv' virtual environment...")
        import venv

        venv.create(VENV_DIR, with_pip=True)

        print("[📦] Installing dependencies ('requests', 'rich')...")
        subprocess.check_call(
            [str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "--upgrade", "pip"]
        )
        subprocess.check_call(
            [str(VENV_PYTHON), "-m", "pip", "install", "--quiet", "requests", "rich"]
        )
        print("[✓] Environment initialized!\n")

    try:
        proc = subprocess.run([str(VENV_PYTHON), str(SCRIPT_PATH)] + sys.argv[1:])
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        sys.exit(0)

# ==========================================
# MAIN APPLICATION (Runs inside .venv)
# ==========================================
import webbrowser
import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

console = Console()

MEDIA_COLORS = {
    "texts": "cyan",
    "movies": "magenta",
    "audio": "green",
    "software": "yellow",
    "image": "blue",
    "etree": "spring_green1",
}


def print_banner():
    banner = Text(
        "🏛️  INTERNET ARCHIVE EXPLORER & DOWNLOADER  🏛️",
        style="bold white on dark_blue",
        justify="center",
    )
    console.print(
        Panel(
            banner,
            subtitle="[dim]Interactive Search & Streamed Downloader[/dim]",
            border_style="bright_blue",
        )
    )


def format_bytes(size_bytes):
    """Converts raw bytes to human-readable format."""
    try:
        size = float(size_bytes)
    except (ValueError, TypeError):
        return "Unknown"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def fetch_archive_page(
    query: str, page: int = 1, page_size: int = 50, media_type: str = None
):
    endpoint = "https://archive.org/advancedsearch.php"

    q = query.strip()
    if media_type:
        q += f" AND mediatype:{media_type}"

    params = {
        "q": q,
        "fl[]": ["identifier", "title", "mediatype", "year", "downloads"],
        "sort[]": "downloads desc",
        "rows": page_size,
        "page": page,
        "output": "json",
    }

    with console.status(
        f"[bold yellow]Fetching page {page}...[/bold yellow]", spinner="dots"
    ):
        try:
            resp = requests.get(endpoint, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json().get("response", {})
            return data.get("docs", []), data.get("numFound", 0)
        except requests.RequestException as e:
            console.print(f"[bold red]✗ Connection Error:[/bold red] {e}")
            return [], 0


def render_page_table(results, current_page, total_pages, total_found, page_size):
    table = Table(
        title=(
            f"\n[bold green]Page {current_page} of {total_pages:,}[/bold green] "
            f"[dim]({total_found:,} total results)[/dim]"
        ),
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )

    table.add_column("#", style="bold yellow", width=4, justify="right")
    table.add_column("Global #", style="dim", width=9, justify="right")
    table.add_column("Title", style="bold white", min_width=30, ratio=2)
    table.add_column("Type", justify="center", width=12)
    table.add_column("Year", justify="center", width=6)
    table.add_column("Views", justify="right", width=10)
    table.add_column("Identifier", style="dim cyan", ratio=1)

    start_offset = (current_page - 1) * page_size

    for idx, item in enumerate(results, 1):
        global_idx = start_offset + idx
        identifier = item.get("identifier", "")
        title = item.get("title", "Untitled")
        media = str(item.get("mediatype", "unknown")).lower()
        year = str(item.get("year", "—"))
        downloads = f"{item.get('downloads', 0):,}"

        color = MEDIA_COLORS.get(media, "white")
        badge = f"[{color}]{media.upper()}[/{color}]"

        table.add_row(
            str(idx), str(global_idx), title, badge, year, downloads, identifier
        )

    console.print(table)


def download_single_file(url: str, dest_path: Path):
    """Downloads a file with a live progress bar."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))

            progress = Progress(
                TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
                BarColumn(bar_width=None),
                "[progress.percentage]{task.percentage:>3.1f}%",
                "•",
                DownloadColumn(),
                "•",
                TransferSpeedColumn(),
                "•",
                TimeRemainingColumn(),
                console=console,
            )

            with progress:
                task_id = progress.add_task(
                    "download",
                    filename=dest_path.name,
                    total=total_size if total_size > 0 else None,
                )
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            f.write(chunk)
                            progress.update(task_id, advance=len(chunk))

        console.print(f"[bold green]✓ Saved:[/bold green] {dest_path}")
    except Exception as e:
        console.print(f"[bold red]✗ Download Failed:[/bold red] {e}")


def handle_download(item: dict):
    """Fetches file metadata for an item and prompts user to pick what to download."""
    identifier = item.get("identifier")
    if not identifier:
        console.print("[red]Missing identifier for this item.[/red]")
        return

    meta_url = f"https://archive.org/metadata/{identifier}"
    with console.status(
        f"[bold yellow]Inspecting files for '{identifier}'...[/bold yellow]",
        spinner="dots",
    ):
        try:
            resp = requests.get(meta_url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            raw_files = data.get("files", [])
        except requests.RequestException as e:
            console.print(f"[bold red]✗ Metadata Error:[/bold red] {e}")
            return

    if not raw_files:
        console.print("[yellow]No downloadable files found for this item.[/yellow]")
        return

    # Filter out archive-internal metadata/system files
    ignored_formats = {
        "Metadata",
        "Archive BitTorrent",
        "Item Tile",
        "Item Image",
    }
    clean_files = []
    for f in raw_files:
        fmt = f.get("format", "")
        name = f.get("name", "")
        # Skip internal XMLs / SQLite index caches
        if fmt in ignored_formats or name.endswith(
            ("_meta.xml", "_files.xml", "_meta.sqlite")
        ):
            continue
        clean_files.append(f)

    # If everything was filtered out, fallback to showing all files
    display_files = clean_files if clean_files else raw_files

    # Display files table
    table = Table(
        title=f"\n[bold green]Files in '{item.get('title', identifier)}'[/bold green]",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("#", style="bold yellow", width=4, justify="right")
    table.add_column("Filename", style="bold white", ratio=3)
    table.add_column("Format", style="cyan", ratio=1)
    table.add_column("Size", justify="right", width=12)

    for idx, f in enumerate(display_files, 1):
        table.add_row(
            str(idx),
            f.get("name", "Unknown"),
            f.get("format", "Unknown"),
            format_bytes(f.get("size")),
        )

    console.print(table)
    console.print(
        "\n[dim]Choose a file number to download, type 'all' to get everything, or press Enter to cancel.[/dim]"
    )

    choice = Prompt.ask("[bold]Select file to download[/bold]", default="").strip().lower()

    if not choice:
        return

    download_dir = SCRIPT_DIR / "downloads" / identifier

    if choice == "all":
        confirm = Prompt.ask(
            f"[bold yellow]Download all {len(display_files)} files?[/bold yellow] (y/n)",
            choices=["y", "n"],
            default="n",
        )
        if confirm == "y":
            for f in display_files:
                fname = f.get("name")
                file_url = f"https://archive.org/download/{identifier}/{fname}"
                dest = download_dir / fname
                download_single_file(file_url, dest)
    elif choice.isdigit() and 1 <= int(choice) <= len(display_files):
        target_file = display_files[int(choice) - 1]
        fname = target_file.get("name")
        file_url = f"https://archive.org/download/{identifier}/{fname}"
        dest = download_dir / fname
        download_single_file(file_url, dest)
    else:
        console.print("[red]Invalid selection.[/red]")


def browse_results(query: str, page_size: int = 50, media_type: str = None):
    current_page = 1

    while True:
        results, total_found = fetch_archive_page(
            query, page=current_page, page_size=page_size, media_type=media_type
        )

        if total_found == 0:
            console.print(
                Panel(
                    "[yellow]No results matched your query. Try broader keywords.[/yellow]",
                    title="[bold]Empty Result[/bold]",
                    border_style="yellow",
                )
            )
            return

        total_pages = max(1, math.ceil(total_found / page_size))
        render_page_table(
            results, current_page, total_pages, total_found, page_size
        )

        # Pagination & Action Control Loop
        while True:
            console.print(
                "\n[bold white]Controls:[/bold white] "
                "[bold green](Enter/n)[/bold green] Next Page │ "
                "[bold cyan](p)[/bold cyan] Prev Page │ "
                "[bold magenta](g)[/bold magenta] Jump to Page │ "
                f"[bold yellow](1-{len(results)})[/bold yellow] Open in Browser │ "
                f"[bold green](d 1-{len(results)})[/bold green] Download Item │ "
                "[bold red](q)[/bold red] New Search"
            )

            raw_input = (
                Prompt.ask("[bold]Command[/bold]", default="n").strip().lower()
            )

            # 1. Quit / New search
            if raw_input in (
                "q",
                "quit",
                "exit",
                "new",
                "search",
                "new search",
                "s",
                "back",
                "b",
            ):
                return

            # 2. Next page
            elif raw_input in ("n", "next", ""):
                if current_page < total_pages:
                    current_page += 1
                    break
                else:
                    console.print("[yellow]You are already on the last page![/yellow]")

            # 3. Previous page
            elif raw_input in ("p", "prev", "previous"):
                if current_page > 1:
                    current_page -= 1
                    break
                else:
                    console.print("[yellow]You are on the first page![/yellow]")

            # 4. Jump directly to a page
            elif raw_input in ("g", "goto", "jump", "page"):
                target = IntPrompt.ask(
                    f"Enter page number (1 - {total_pages:,})"
                )
                if 1 <= target <= total_pages:
                    current_page = target
                    break
                else:
                    console.print("[red]Page number is out of range.[/red]")

            # 5. Download item (e.g., 'd 1', 'download 2', 'dl 3')
            elif (
                raw_input.startswith("d ")
                or raw_input.startswith("dl ")
                or raw_input.startswith("download ")
            ):
                parts = raw_input.split()
                if len(parts) == 2 and parts[1].isdigit():
                    idx = int(parts[1])
                    if 1 <= idx <= len(results):
                        handle_download(results[idx - 1])
                    else:
                        console.print("[red]Item number out of range.[/red]")
                else:
                    console.print("[red]Usage: d <item number> (e.g. d 1)[/red]")

            # 6. Open item in browser (e.g., '1', 'open 1')
            elif (
                raw_input.isdigit() and 1 <= int(raw_input) <= len(results)
            ) or (
                raw_input.startswith("open ")
                and raw_input.split()[-1].isdigit()
                and 1 <= int(raw_input.split()[-1]) <= len(results)
            ):
                item_idx = (
                    int(raw_input)
                    if raw_input.isdigit()
                    else int(raw_input.split()[-1])
                )
                target_url = f"https://archive.org/details/{results[item_idx - 1]['identifier']}"
                console.print(
                    f"[green]Opening[/green] {target_url} in your browser..."
                )
                webbrowser.open(target_url)

            else:
                console.print(
                    "[red]Invalid command. Press Enter for Next, 'p' for Prev, 'd #' to Download, or enter an item # to Open in browser.[/red]"
                )


def main():
    print_banner()

    while True:
        try:
            query = Prompt.ask(
                "\n[bold yellow]🔍 Search query[/bold yellow] (or [bold red]'q'[/bold red] to quit)"
            ).strip()

            if not query or query.lower() in ("q", "quit", "exit"):
                console.print(
                    "\n[bold green]Thanks for exploring! Goodbye 👋[/bold green]\n"
                )
                break

            page_size = IntPrompt.ask(
                "[bold cyan]📄 Items per page[/bold cyan]", default=50
            )

            console.print(
                "[dim]Media types: texts, movies, audio, software (press Enter to search all)[/dim]"
            )
            media_type = (
                Prompt.ask(
                    "[bold magenta]📁 Filter by media type[/bold magenta]",
                    default="",
                ).strip()
                or None
            )

            browse_results(
                query, page_size=page_size, media_type=media_type
            )

        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]\nSession cancelled. Bye![/yellow]")
            sys.exit(0)


if __name__ == "__main__":
    main()