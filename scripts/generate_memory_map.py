"""Generate detailed textual and graphical (PDF) memory maps for Atari 8-bit executable (.xex).

Target: Atari 800XL / 65XE (MOS 6502, 64 KB RAM)
Reports:
1. Terminal breakdown of all memory segments, sizes, and free gaps.
2. Zero Page allocation details ($00-$FF).
3. Publication-quality vector PDF diagram showing full 64 KB address space,
   zoomed User RAM ($2000-$BFFF), Zero Page bar, and sidebar legend with key metrics.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Sequence

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for headless CLI / build environments
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch
import matplotlib.patheffects as path_effects


@dataclass
class MemorySegment:
    start: int
    end: int
    size: int
    name: str
    category: str
    color: str
    is_free: bool = False
    details: str = ""


# Color palette for memory categories
COLORS: dict[str, str] = {
    "CODE": "#2563EB",         # Royal Blue
    "GRAPHICS": "#059669",     # Emerald Green (VRAM)
    "BITMAPS": "#0D9488",      # Teal (Tilesets)
    "DLIST": "#D97706",        # Amber
    "AUDIO": "#7C3AED",        # Violet
    "PMG": "#DB2777",          # Pink / Magenta
    "METADATA": "#0284C7",     # Sky Blue
    "FREE": "#10B981",         # Bright Mint Green (Free User RAM)
    "SYSTEM": "#64748B",       # Slate Gray (Low RAM / OS)
    "HARDWARE": "#DC2626",     # Crimson Red ($D000-$DFFF)
    "ROM": "#475569",          # Dark Slate ($C000-$CFFF, $E000-$FFFF)
}


def parse_xex_segments(data: bytes) -> list[tuple[int, int, int]]:
    """Parse segments from an Atari DOS XEX binary file."""
    segments: list[tuple[int, int, int]] = []
    pos = 2 if len(data) >= 2 and data[:2] == b"\xff\xff" else 0

    while pos + 4 <= len(data):
        start = data[pos] | (data[pos + 1] << 8)
        end = data[pos + 2] | (data[pos + 3] << 8)
        pos += 4

        if start == 0xFFFF:
            if pos + 4 > len(data):
                break
            start = data[pos] | (data[pos + 1] << 8)
            end = data[pos + 2] | (data[pos + 3] << 8)
            pos += 4

        size = end - start + 1
        if size <= 0 or pos + size > len(data):
            break

        segments.append((start, end, size))
        pos += size

    return sorted(segments, key=lambda s: s[0])


def identify_segment(start: int, end: int, size: int) -> tuple[str, str, str, str]:
    """Map segment address range to name, category, color, and description."""
    if start == 0x02E0 or start == 0x02E2:
        return "Vector (RUNAD/INITAD)", "SYSTEM", COLORS["SYSTEM"], "DOS Loader Run/Init Address"
    if start == 0x2000:
        return "Engine & State Code", "CODE", COLORS["CODE"], "Main loop, Game state machine, Game Over logic"
    if start == 0x2400:
        return "Intro Font & VRAM", "GRAPHICS", COLORS["GRAPHICS"], "Custom 1 KB font ($2400) + Intro text ($2800)"
    if start == 0x2A00:
        return "Intro Display List", "DLIST", COLORS["DLIST"], "10-line ANTIC Mode 2 Display List"
    if start in (0x2A30, 0x2B00):
        return "Tileset Metadata, Status Line & SFX", "METADATA", COLORS["METADATA"], "Row offset lookup tables, HUD status line & victory fanfare"
    if start == 0x3000:
        return "Gameplay VRAM & DLISTs", "GRAPHICS", COLORS["GRAPHICS"], "Mode D 160x96 ($3000) + dlist_game & dlist_scene_title"
    if start == 0x3F00:
        return "Gameplay Display List", "DLIST", COLORS["DLIST"], "96-line ANTIC Mode D Display List + Title Card DLIST"
    if start == 0x4000:
        return "Title VScroll VRAM & Text", "GRAPHICS", COLORS["GRAPHICS"], "Vertical scroll VRAM ($4000) + Centered text lines ($4078)"
    if start in (0x5000, 0x2C30, 0x2D00):
        return "Scene Runtime Engine", "METADATA", COLORS["METADATA"], "Secrets (+sprite channel dispatch), enemies & SFX runtime engine"
    if start in (0xA800, 0xA400, 0xA300):
        return "Scene SoA Tables & DLI Blocks", "METADATA", COLORS["METADATA"], "Scene definitions, platforms, objects, pointer tables & per-scene DLI blocks (grows with the scene count)"
    if start == 0x6000:
        return "Title Display List", "DLIST", COLORS["DLIST"], "Procedural 2bpp Title Display List with Mode 2 VScroller"
    if start == 0x6100:
        return "Unified DLI Engine & Buffers", "CODE", COLORS["CODE"], "Double-buffered DLI tables and 3-phase DLI interrupt handler"
    if start == 0x6800:
        return "Render Tables + Intro Handler", "CODE", COLORS["CODE"], "2bpp flip LUT + row offsets (MEM-006) and the relocated Intro screen code"
    if start == 0x69C0:
        return "Intro Screen Handler", "CODE", COLORS["CODE"], "Intro text screen init/run (relocated out of the $2000 block)"
    if start == 0x6B00:
        return "Player-Missile & Audio", "PMG", COLORS["PMG"], "1.25 KB active PMG buffer ($6B00) + Audio Player & Music ($7000)"
    if start == 0x7000:
        return "Audio Player & Music", "AUDIO", COLORS["AUDIO"], "POKEY Player engine & Title track"
    if start in (0x79D0, 0x7A00):
        return "Playfield Blitter & Sprites", "CODE", COLORS["CODE"], "Playfield blitter engine & sprite bitmaps"
    if start == 0x8000:
        return "ANTIC Mode E Tilesets", "BITMAPS", COLORS["BITMAPS"], "Bitmapped sheets: Castles, Depths, Hell, Trees (16.2 KB)"

    return f"Segment ${start:04X}", "DATA", COLORS["METADATA"], f"Data segment ({size} bytes)"


def describe_free_gap(start: int, end: int, size: int) -> str:
    """Provide clear human-readable context for what borders this free gap."""
    if end == 0x2FFF:
        return "Low RAM gap before Gameplay VRAM ($3000) — vacated by scenes data"
    if end == 0x5FFF:
        return "Free expansion headroom in the $5000 block before Title DLIST ($6000)"
    if start in (0xA800, 0xA400, 0xA300) or end in (0xA7FF, 0xA3FF, 0xA2FF):
        return "Tile headroom before the Scene Data Tables — keep the tilesets below"
    if end == 0x6AFF or start == 0x69C0:
        return "Free headroom in PMG block ($6800-$6AFF) before PMG missiles ($6B00)"
    if end == 0x7FFF:
        return "Free headroom in $7000 block before ANTIC Mode E Tilesets ($8000)"
    if end == 0x23FF:
        return "Free headroom in $2000 block before Intro Font ($2400) — vacated by title code"
    if start == 0x606D or end == 0x60FF:
        return "Free space after Title DLIST before DLI double buffers ($6100)"
    if end == 0xBFFF:
        return "Headroom below OS ROM Kernel boundary ($C000)"
    if end == 0x3EFF or start == 0x3F89:
        return "Free headroom in $3000 block after Gameplay DLIST"
    if end == 0x4FFF or start == 0x4FC7:
        return "Free space after Title Scroller before $5000 boundary"
    return f"Unallocated headroom: {size} bytes"


def build_memory_map(
    raw_segments: list[tuple[int, int, int]]
) -> tuple[list[MemorySegment], list[MemorySegment]]:
    """Build complete list of user segments and free memory gaps between $2000 and $BFFF."""
    # Filter out DOS vectors
    user_segs = [s for s in raw_segments if s[0] != 0x02E0 and s[0] != 0x02E2]
    user_segs.sort(key=lambda s: s[0])

    all_regions: list[MemorySegment] = []
    free_gaps: list[MemorySegment] = []

    curr_addr = 0x2000

    for start, end, size in user_segs:
        if start > curr_addr:
            gap_size = start - curr_addr
            gap_end = start - 1
            gap_seg = MemorySegment(
                start=curr_addr,
                end=gap_end,
                size=gap_size,
                name=f"FREE RAM ({gap_size} B)",
                category="FREE",
                color=COLORS["FREE"],
                is_free=True,
                details=describe_free_gap(curr_addr, gap_end, gap_size),
            )
            all_regions.append(gap_seg)
            free_gaps.append(gap_seg)

        name, cat, col, details = identify_segment(start, end, size)
        all_regions.append(
            MemorySegment(
                start=start,
                end=end,
                size=size,
                name=name,
                category=cat,
                color=col,
                is_free=False,
                details=details,
            )
        )
        curr_addr = end + 1

    if curr_addr <= 0xBFFF:
        gap_size = 0xBFFF - curr_addr + 1
        gap_seg = MemorySegment(
            start=curr_addr,
            end=0xBFFF,
            size=gap_size,
            name=f"FREE RAM ({gap_size} B)",
            category="FREE",
            color=COLORS["FREE"],
            is_free=True,
            details=describe_free_gap(curr_addr, 0xBFFF, gap_size),
        )
        all_regions.append(gap_seg)
        free_gaps.append(gap_seg)

    return all_regions, free_gaps


def print_text_report(
    xex_path: Path,
    all_regions: list[MemorySegment],
    free_gaps: list[MemorySegment],
) -> None:
    """Print formatted terminal report of memory segments and free areas."""
    print("=" * 82)
    print(f"ATARI 8-BIT MEMORY MAP REPORT: {xex_path.name}")
    print("=" * 82)
    print(f"{'Address Range':^19} | {'Size':^8} | {'Type':^10} | {'Segment Name / Description'}")
    print("-" * 82)

    total_allocated = 0
    total_free = 0

    for reg in all_regions:
        addr_str = f"${reg.start:04X} - ${reg.end:04X}"
        size_str = f"{reg.size:5d} B"
        if reg.is_free:
            total_free += reg.size
            print(f"\033[32m{addr_str:19} | {size_str:8} | {'[FREE]':^10} | {reg.name:<35}\033[0m")
        else:
            total_allocated += reg.size
            print(f"{addr_str:19} | {size_str:8} | {reg.category:^10} | {reg.name:<35}")

    print("-" * 82)
    print(f"Total User RAM ($2000-$BFFF):  40,960 bytes (100.0%)")
    print(f"Total Allocated Memory:        {total_allocated:5d} bytes ({total_allocated / 40960 * 100:5.1f}%)")
    print(f"Total Free Memory (Headroom):  {total_free:5d} bytes ({total_free / 40960 * 100:5.1f}%)")
    print("-" * 82)

    # Top free blocks
    sorted_free = sorted(free_gaps, key=lambda g: g.size, reverse=True)
    print("\nTOP FREE MEMORY REGIONS:")
    for idx, g in enumerate(sorted_free, 1):
        print(f"  {idx}. ${g.start:04X} - ${g.end:04X} : {g.size:5d} bytes ({g.size / 1024:4.2f} KB) — {g.details}")

    # Zero Page Breakdown
    print("\n" + "=" * 82)
    print("ZERO PAGE ALLOCATION ($00 - $FF / 256 bytes):")
    print("=" * 82)
    zp_info = [
        ("$00 - $7F", 128, "SYSTEM (OS)", "Reserved for Atari OS Kernel"),
        ("$80 - $87", 8, "ENGINE", "Registers & temporary pointers (zp_temp, zp_ptr_src/dst)"),
        ("$88 - $8F", 8, "STATE", "Game states, title card fade counters, fire debouncing"),
        ("$90 - $99", 10, "AUDIO", "POKEY Audio Player base pointers (PLAYER_ZP_BASE)"),
        ("$9A - $B7", 30, "RENDERER", "Scene renderer table pointers & parameters"),
        ("$B8 - $C0", 9, "DLI ENGINE", "DLI registers save, pas counters & PMG pattern ptr"),
        ("$C1 - $FF", 63, "FREE", "Available for player physics, enemies AI & collision"),
    ]
    for rng, sz, cat, desc in zp_info:
        cat_str = f"[{cat}]"
        col_prefix = "\033[32m" if cat == "FREE" else ""
        col_suffix = "\033[0m" if cat == "FREE" else ""
        print(f"  {col_prefix}{rng:11} ({sz:3d} B) {cat_str:12} : {desc}{col_suffix}")
    print("=" * 82 + "\n")


def generate_graphical_pdf(
    pdf_path: Path,
    xex_name: str,
    all_regions: list[MemorySegment],
    free_gaps: list[MemorySegment],
) -> None:
    """Generate high-resolution graphical vector PDF visualizing the 64 KB memory space."""
    fig = plt.figure(figsize=(16, 10), dpi=300)
    fig.patch.set_facecolor("#0F172A")  # Modern dark background: Slate-900

    # Grid layout: 
    # Left: Full 64 KB bar (x=0.06..0.16)
    # Center: Zoomed User RAM ($2000-$BFFF) (x=0.23..0.60)
    # Right: Summary & Detailed Legend Cards (x=0.64..0.95)

    # 1. Header Title
    plt.text(
        0.06, 0.94,
        "ATARI 8-BIT MEMORY MAP — CALL OF THE WINTERMON",
        fontsize=20,
        fontweight="bold",
        color="#F8FAFC",
        transform=fig.transFigure,
    )
    plt.text(
        0.06, 0.915,
        f"File: {xex_name}  |  Target: Atari 800XL / 65XE (MOS 6502)  |  RAM: 64 KB  |  User RAM: $2000–$BFFF (40 KB)",
        fontsize=11,
        color="#94A3B8",
        transform=fig.transFigure,
    )

    # --------------------------------------------------------------------------
    # 2. Left Column: Full 64 KB Space ($0000 - $FFFF)
    # --------------------------------------------------------------------------
    ax_full = fig.add_axes([0.06, 0.10, 0.10, 0.77])
    ax_full.set_facecolor("#1E293B")
    ax_full.set_ylim(0x0000, 0x10000)
    ax_full.set_xlim(0, 1)
    ax_full.set_xticks([])

    full_yticks = [0x0000, 0x0800, 0x2000, 0x4000, 0x6000, 0x8000, 0xA000, 0xC000, 0xD000, 0xE000, 0xFFFF]
    ax_full.set_yticks(full_yticks)
    ax_full.set_yticklabels([f"${y:04X}" for y in full_yticks], fontsize=9, color="#94A3B8", fontfamily="monospace")
    ax_full.tick_params(axis="y", colors="#64748B", length=6)
    for spine in ax_full.spines.values():
        spine.set_color("#334155")

    # Macro regions in Full 64 KB
    macro_blocks = [
        (0x0000, 0x07FF, "System RAM\n(ZP, Stack, OS)", COLORS["SYSTEM"]),
        (0x0800, 0x1FFF, "DOS / Low RAM", "#334155"),
        (0x2000, 0xBFFF, "USER PROGRAM\nSPACE (40 KB)\n[ZOOMED ->]", "#1E3A8A"),
        (0xC000, 0xCFFF, "OS ROM Kernel", COLORS["ROM"]),
        (0xD000, 0xDFFF, "Hardware I/O\n(GTIA/ANTIC/POKEY)", COLORS["HARDWARE"]),
        (0xE000, 0xFFFF, "OS ROM Kernel", COLORS["ROM"]),
    ]

    for start, end, label, col in macro_blocks:
        height = end - start + 1
        rect = Rectangle((0, start), 1, height, facecolor=col, edgecolor="#0F172A", linewidth=1.5)
        ax_full.add_patch(rect)
        mid_y = start + height / 2
        ax_full.text(
            0.5, mid_y, label,
            ha="center", va="center",
            fontsize=8, fontweight="bold",
            color="#FFFFFF" if col != "#334155" else "#94A3B8",
        )

    ax_full.set_title("64 KB Space", color="#CBD5E1", fontsize=11, fontweight="bold", pad=10)

    # --------------------------------------------------------------------------
    # 3. Center Column: Detailed User RAM ($2000 - $BFFF)
    # --------------------------------------------------------------------------
    ax_user = fig.add_axes([0.22, 0.10, 0.38, 0.77])
    ax_user.set_facecolor("#1E293B")
    ax_user.set_ylim(0x2000, 0xC000)
    ax_user.set_xlim(0, 100)
    ax_user.set_xticks([])

    user_yticks = [0x2000, 0x3000, 0x4000, 0x5000, 0x6000, 0x6800, 0x7000, 0x7A00, 0x8000, 0xA000, 0xA800, 0xC000]
    ax_user.set_yticks(user_yticks)
    ax_user.set_yticklabels([f"${y:04X}" for y in user_yticks], fontsize=9, color="#94A3B8", fontfamily="monospace")
    ax_user.tick_params(axis="y", colors="#64748B", length=6)
    for spine in ax_user.spines.values():
        spine.set_color("#334155")

    # Render each segment and free gap in user memory
    for reg in all_regions:
        start = reg.start
        end = reg.end
        height = reg.size

        if reg.is_free:
            facecol = "#064E3B"  # Deep dark emerald for free space
            edgecol = "#10B981"
            hatch = "//"
        else:
            facecol = reg.color
            edgecol = "#0F172A"
            hatch = None

        rect = Rectangle((0, start), 100, height, facecolor=facecol, edgecolor=edgecol, linewidth=1, hatch=hatch)
        ax_user.add_patch(rect)

        mid_y = start + height / 2

        # Decide text display depending on whether it is a free gap or occupied segment
        if reg.is_free:
            if height >= 200:
                txt = f"★ FREE: {reg.size:,} B  [${start:04X}–${end:04X}]"
                ax_user.text(
                    50, mid_y, txt,
                    ha="center", va="center",
                    fontsize=8, fontweight="bold",
                    color="#A7F3D0",
                    path_effects=[path_effects.withStroke(linewidth=2, foreground="#064E3B")],
                )
            elif height >= 60:
                txt = f"★ FREE: {reg.size} B"
                ax_user.text(
                    50, mid_y, txt,
                    ha="center", va="center",
                    fontsize=7, fontweight="bold",
                    color="#6EE7B7",
                    path_effects=[path_effects.withStroke(linewidth=2, foreground="#064E3B")],
                )
        else:
            if height >= 1200:
                txt = f"{reg.name}  [${start:04X}–${end:04X}]  ({reg.size:,} B)"
                ax_user.text(
                    50, mid_y, txt,
                    ha="center", va="center",
                    fontsize=9, fontweight="bold",
                    color="#FFFFFF",
                    path_effects=[path_effects.withStroke(linewidth=2, foreground="#0F172A")],
                )
            elif height >= 350:
                txt = f"{reg.name} ({reg.size:,} B)"
                ax_user.text(
                    50, mid_y, txt,
                    ha="center", va="center",
                    fontsize=8, fontweight="bold",
                    color="#FFFFFF",
                    path_effects=[path_effects.withStroke(linewidth=2, foreground="#0F172A")],
                )

    ax_user.set_title("User RAM Allocations & Free Gaps ($2000 – $BFFF)", color="#CBD5E1", fontsize=11, fontweight="bold", pad=10)

    # --------------------------------------------------------------------------
    # 4. Right Sidebar: Key Metrics, Legend & Details
    # --------------------------------------------------------------------------
    ax_sidebar = fig.add_axes([0.64, 0.10, 0.32, 0.77])
    ax_sidebar.set_facecolor("#1E293B")
    ax_sidebar.set_xticks([])
    ax_sidebar.set_yticks([])
    for spine in ax_sidebar.spines.values():
        spine.set_color("#334155")

    total_allocated = sum(r.size for r in all_regions if not r.is_free)
    total_free = sum(r.size for r in all_regions if r.is_free)
    pct_used = total_allocated / 40960 * 100
    pct_free = total_free / 40960 * 100

    y_pos = 0.96

    def draw_section_header(title: str, y: float) -> float:
        ax_sidebar.text(0.05, y, title, fontsize=12, fontweight="bold", color="#38BDF8")
        ax_sidebar.plot([0.05, 0.95], [y - 0.015, y - 0.015], color="#0284C7", linewidth=1.5)
        return y - 0.05

    # Card 1: Key Metrics Summary
    y_pos = draw_section_header("MEMORY UTILIZATION SUMMARY", y_pos)

    largest_gap = max(free_gaps, key=lambda g: g.size) if free_gaps else None
    largest_str = f"{largest_gap.size:,} Bytes (${largest_gap.start:04X}–${largest_gap.end:04X})" if largest_gap else "None"

    metrics = [
        ("User RAM Space ($2000–$BFFF):", "40,960 Bytes (40.0 KB)"),
        ("Allocated Memory:", f"{total_allocated:,} Bytes ({pct_used:.1f}%)"),
        ("Total Free Headroom:", f"{total_free:,} Bytes ({pct_free:.1f}%)"),
        ("Largest Free Block:", largest_str),
        ("Free Zero Page RAM:", "63 Bytes ($C1–$FF)"),
    ]

    for label, val in metrics:
        ax_sidebar.text(0.06, y_pos, label, fontsize=9, color="#94A3B8")
        ax_sidebar.text(0.94, y_pos, val, fontsize=9, fontweight="bold", color="#F8FAFC", ha="right")
        y_pos -= 0.035

    y_pos -= 0.02

    # Card 2: Legend of Categories
    y_pos = draw_section_header("CATEGORY LEGEND", y_pos)

    categories = [
        ("CODE", COLORS["CODE"], "Game Engine ($2000), DLI Engine ($6100), Render ($7A00)"),
        ("GRAPHICS", COLORS["GRAPHICS"], "Playfield VRAM ($3000) & Title/Scroller ($4000)"),
        ("BITMAPS", COLORS["BITMAPS"], "ANTIC Mode E Tileset Sheets ($8000)"),
        ("DLIST", COLORS["DLIST"], "Display Lists (Game $3F00, Title $6000, Intro $2A00)"),
        ("PMG / AUDIO", COLORS["PMG"], "Player-Missiles ($6800) & Audio Player ($7000)"),
        ("METADATA", COLORS["METADATA"], "Scene SoA Tables, Title Code & Intro Music ($5000)"),
        ("FREE RAM", COLORS["FREE"], "Available unallocated memory gaps"),
        ("HARDWARE / ROM", COLORS["HARDWARE"], "GTIA/ANTIC/POKEY ($D000) & OS ROM ($C000+)"),
    ]

    for cat_name, col, desc in categories:
        rect = Rectangle((0.06, y_pos - 0.005), 0.05, 0.02, facecolor=col, edgecolor="#FFFFFF", linewidth=0.5)
        ax_sidebar.add_patch(rect)
        ax_sidebar.text(0.13, y_pos, cat_name, fontsize=8.5, fontweight="bold", color="#F8FAFC")
        ax_sidebar.text(0.40, y_pos, desc, fontsize=7.5, color="#94A3B8")
        y_pos -= 0.032

    y_pos -= 0.02

    # Card 3: Top Free Blocks & Opportunities
    y_pos = draw_section_header("TOP FREE MEMORY REGIONS (HEADROOM)", y_pos)

    sorted_free = sorted(free_gaps, key=lambda g: g.size, reverse=True)[:5]
    for idx, g in enumerate(sorted_free, 1):
        line1 = f"{idx}. ${g.start:04X} – ${g.end:04X}  ({g.size:,} Bytes / {g.size/1024:.2f} KB)"
        ax_sidebar.text(0.06, y_pos, line1, fontsize=8.5, fontweight="bold", color="#34D399")
        y_pos -= 0.023
        ax_sidebar.text(0.10, y_pos, g.details, fontsize=7.5, color="#64748B")
        y_pos -= 0.030

    y_pos -= 0.01

    # Card 4: Zero Page Map
    y_pos = draw_section_header("ZERO PAGE BREAKDOWN ($00 – $FF)", y_pos)
    zp_lines = [
        ("$00 – $7F (128 B)", "Reserved for Atari OS Kernel", "#64748B"),
        ("$80 – $8F ( 16 B)", "Engine temporaries & state machine", "#38BDF8"),
        ("$90 – $99 ( 10 B)", "POKEY Audio Player base pointers", "#A855F7"),
        ("$9A – $B7 ( 30 B)", "Scene background renderer pointers", "#06B6D4"),
        ("$B8 – $C0 (  9 B)", "DLI engine registers & pattern pointers", "#E879F9"),
        ("$C1 – $FF ( 63 B)", "★ 100% FREE for Entities, AI, Physics", "#34D399"),
    ]
    for rng, desc, col in zp_lines:
        ax_sidebar.text(0.06, y_pos, rng, fontsize=8, fontweight="bold", color=col)
        ax_sidebar.text(0.42, y_pos, desc, fontsize=7.5, color="#94A3B8")
        y_pos -= 0.026

    # Save vector PDF
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(pdf_path, format="pdf", bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    print(f"\033[36mGenerated graphical memory map PDF: {pdf_path}\033[0m")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Atari 8-bit memory map report and graphical PDF.")
    parser.add_argument(
        "xex",
        type=Path,
        nargs="?",
        default=Path("call_of_the_wintermon.xex"),
        help="Path to Atari DOS executable (.xex)",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=Path("memory_map.pdf"),
        help="Output path for graphical PDF memory map (default: memory_map.pdf)",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip PDF generation and only print terminal report",
    )

    args = parser.parse_args()

    if not args.xex.is_file():
        print(f"Error: Executable file '{args.xex}' not found. Run 'make all' first.", file=sys.stderr)
        return 1

    data = args.xex.read_bytes()
    raw_segments = parse_xex_segments(data)
    all_regions, free_gaps = build_memory_map(raw_segments)

    # 1. Print formatted console report
    print_text_report(args.xex, all_regions, free_gaps)

    # 2. Generate vector PDF
    if not args.no_pdf:
        generate_graphical_pdf(args.pdf, args.xex.name, all_regions, free_gaps)

    return 0


if __name__ == "__main__":
    sys.exit(main())
