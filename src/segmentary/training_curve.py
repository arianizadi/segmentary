"""Terminal line chart with optimizer-step coordinates and explicit value axes."""

from itertools import pairwise

from rich.text import Text
from textual.widgets import Static


class TrainingCurve(Static):
    def __init__(self, title, tag, *, percent=False, **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.tag = tag
        self.percent = percent
        self.points = []

    def render(self):
        result = Text(self.title + "\n", style="bold #66e3c4")
        points = self.points
        if not points:
            result.append("\nWaiting for recorded metrics…", style="dim")
            return result
        fmt = ".1%" if self.percent else ".3g"
        low, high = min(p.value for p in points), max(p.value for p in points)
        result.append(
            f"Latest {points[-1].value:{fmt}}   Min {low:{fmt}}   Max {high:{fmt}}\n",
            style="#97abc7",
        )
        width, height = max(8, self.size.width - 14), 7
        start, end = points[0].step + 1, points[-1].step + 1
        span = high - low
        if span == 0:
            low -= max(abs(low) * 0.05, 0.01)
            high += max(abs(high) * 0.05, 0.01)
            span = high - low
        grid = [[" " for _ in range(width)] for _ in range(height)]
        coords = [
            (
                round((p.step + 1 - start) / max(1, end - start) * (width - 1)),
                round((high - p.value) / span * (height - 1)),
            )
            for p in points
        ]
        for (x0, y0), (x1, y1) in pairwise(coords):
            for i in range(max(abs(x1 - x0), abs(y1 - y0)) + 1):
                fraction = i / max(1, abs(x1 - x0), abs(y1 - y0))
                grid[round(y0 + (y1 - y0) * fraction)][round(x0 + (x1 - x0) * fraction)] = "·"
        for x, y in coords:
            grid[y][x] = "●"
        for i, row in enumerate(grid):
            label = format(high - i * span / (height - 1), fmt) if i in (0, 3, 6) else ""
            result.append(f"{label:>9} │", style="#97abc7")
            result.append("".join(row) + "\n", style="#66e3c4")
        result.append("          └" + "─" * width + "\n", style="#97abc7")
        labels = (
            f"{start:,}" + " " * max(1, width - len(f"{start:,}") - len(f"{end:,}")) + f"{end:,}"
        )
        result.append("           " + labels + "\n", style="#97abc7")
        result.append("           Optimizer step · points = recorded samples", style="dim")
        return result
