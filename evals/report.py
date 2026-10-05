"""Render a Scorecard as a terminal table, a Markdown table, and an SVG bar chart.

The SVG is hand-rolled (no matplotlib) so it renders identically on GitHub and needs no
extra dependency. It is regenerated on every eval run and committed, so the chart in the
README is always the real, current number.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from evals.scoring import Metrics, Scorecard


def print_terminal(card: Scorecard) -> None:
    console = Console()
    table = Table(title=f"Scorecard: {card.reviewer}")
    table.add_column("clause type")
    table.add_column("n", justify="right")
    table.add_column("presence acc", justify="right")
    table.add_column("span recall", justify="right")
    table.add_column("citation prec", justify="right")
    table.add_column("false refusal", justify="right")
    table.add_column("hallucinated", justify="right")

    def row(label: str, m: Metrics, bold: bool = False) -> None:
        style = "bold" if bold else ""
        table.add_row(
            label,
            str(m.n),
            f"{m.presence_accuracy:.0%}",
            f"{m.span_recall:.0%}",
            f"{m.citation_precision:.0%}",
            f"{m.false_refusal_rate:.0%}",
            f"{m.hallucinated_presence_rate:.0%}",
            style=style,
        )

    for ct, m in sorted(card.by_clause_type.items()):
        row(ct, m)
    table.add_section()
    row("OVERALL", card.overall, bold=True)
    console.print(table)


def to_markdown(card: Scorecard) -> str:
    lines = [
        f"### Scorecard: `{card.reviewer}`",
        "",
        "| clause type | n | presence acc | span recall | citation prec | false refusal | hallucinated |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for ct, m in sorted(card.by_clause_type.items()):
        lines.append(
            f"| {ct} | {m.n} | {m.presence_accuracy:.0%} | {m.span_recall:.0%} | "
            f"{m.citation_precision:.0%} | {m.false_refusal_rate:.0%} | "
            f"{m.hallucinated_presence_rate:.0%} |"
        )
    m = card.overall
    lines.append(
        f"| **overall** | **{m.n}** | **{m.presence_accuracy:.0%}** | **{m.span_recall:.0%}** | "
        f"**{m.citation_precision:.0%}** | **{m.false_refusal_rate:.0%}** | "
        f"**{m.hallucinated_presence_rate:.0%}** |"
    )
    return "\n".join(lines) + "\n"


_COLORS = {
    "presence_accuracy": "#2f80ed",
    "span_recall": "#27ae60",
    "citation_precision": "#f2994a",
}
_LABELS = {
    "presence_accuracy": "presence accuracy",
    "span_recall": "span recall",
    "citation_precision": "citation precision",
}


def to_svg(card: Scorecard) -> str:
    rows = sorted(card.by_clause_type.items()) + [("OVERALL", card.overall)]
    metrics = list(_COLORS)
    left, top, right, bottom = 190, 60, 30, 40
    row_h, bar_h, gap = 26, 6, 1
    width = 760
    plot_w = width - left - right
    height = top + row_h * len(rows) + bottom

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Segoe UI, Helvetica, Arial, sans-serif" '
        f'font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#ffffff" rx="8"/>',
        f'<text x="{left}" y="24" font-size="15" font-weight="600" fill="#1a1a1a">'
        f"Eval scorecard | reviewer: {card.reviewer} | {card.overall.n} cases</text>",
    ]
    # legend
    lx = left
    for m in metrics:
        out.append(f'<rect x="{lx}" y="36" width="10" height="10" fill="{_COLORS[m]}" rx="2"/>')
        out.append(f'<text x="{lx + 14}" y="45" fill="#444">{_LABELS[m]}</text>')
        lx += 150
    # gridlines
    for pct in (0, 25, 50, 75, 100):
        x = left + plot_w * pct / 100
        out.append(f'<line x1="{x:.1f}" y1="{top - 4}" x2="{x:.1f}" y2="{height - bottom + 4}" stroke="#e6e6e6"/>')
        out.append(f'<text x="{x:.1f}" y="{height - bottom + 18}" text-anchor="middle" fill="#888">{pct}%</text>')
    # bars
    for i, (label, m) in enumerate(rows):
        y = top + i * row_h
        weight = ' font-weight="600"' if label == "OVERALL" else ""
        out.append(f'<text x="{left - 8}" y="{y + 14}" text-anchor="end" fill="#1a1a1a"{weight}>{label}</text>')
        for j, name in enumerate(metrics):
            value = getattr(m, name)
            w = plot_w * value
            by = y + 2 + j * (bar_h + gap)
            out.append(f'<rect x="{left}" y="{by}" width="{w:.1f}" height="{bar_h}" fill="{_COLORS[name]}" rx="1"/>')
    out.append("</svg>")
    return "\n".join(out)


def write_reports(card: Scorecard, svg_path: Path, md_path: Path) -> None:
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(to_svg(card), encoding="utf-8")
    md_path.write_text(to_markdown(card), encoding="utf-8")
