from __future__ import annotations

import pygame

from ..mission.blueprint import Blueprint
from ..mission.goals import GOALS
from ..sim.config import SimConfig
from ..sim.robots import Robot
from ..sim.world import World


BG = (12, 12, 18)
GRID = (30, 30, 40)
POD = (50, 240, 240)
ANCHOR = (255, 90, 90)
BLOCK = (80, 130, 220)
AIRLOCK = (80, 220, 120)
TEXT = (230, 230, 240)
LABEL = (255, 80, 80)


class Renderer:
    def __init__(
        self,
        world: World,
        fleet: list[Robot],
        blueprint: Blueprint,
        sim: SimConfig,
        landing_zone: tuple[int, int],
    ):
        pygame.init()
        pygame.display.set_caption("moon_base_sim")
        self.world = world
        self.fleet = fleet
        self.pod = next((r for r in fleet if r.kind == "pod"), None)
        self.blueprint = blueprint
        self.sim = sim
        self.landing_zone = landing_zone
        self._latched: dict[str, str] = {}   # goal.name -> reason, kept once OK
        self.cell = sim.cell_size
        self._elev_lo = sim.elev_display_min_m
        self._elev_span = sim.elev_display_max_m - sim.elev_display_min_m
        self.panel_w = 340
        self.w = world.w * self.cell + self.panel_w
        self.h = world.h * self.cell
        self.screen = pygame.display.set_mode((self.w, self.h))
        self.font = pygame.font.SysFont("monospace", 14)
        self.big = pygame.font.SysFont("monospace", 18, bold=True)
        self.clock = pygame.time.Clock()

    def _cell_rect(self, x: int, y: int) -> pygame.Rect:
        return pygame.Rect(x * self.cell, y * self.cell, self.cell, self.cell)

    def _shade(self, e: float) -> int:
        """Elevation → gray byte over the configured display range (clamped)."""
        return max(0, min(255, int((e - self._elev_lo) / self._elev_span * 255)))

    def draw(self, sim_time: float) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False

        self.screen.fill(BG)
        self._draw_terrain()
        self._draw_pod()
        self._draw_anchors()
        self._draw_blocks()
        self._draw_airlock()
        self._draw_grid()
        self._draw_robots()
        self._draw_panel(sim_time)
        self._draw_colorbar()
        pygame.display.flip()
        self.clock.tick(self.sim.target_fps)
        return True

    def _draw_terrain(self) -> None:
        for y in range(self.world.h):
            for x in range(self.world.w):
                g = self._shade(self.world.elevation[y][x])
                pygame.draw.rect(self.screen, (g, g, g), self._cell_rect(x, y))

    def _draw_pod(self) -> None:
        if self.pod is None:
            return
        center_px = (self.pod.x * self.cell + self.cell // 2, self.pod.y * self.cell + self.cell // 2)
        t = self.world.pod_inflation
        deflated = self.cell
        inflated = self.blueprint.dome_radius * self.cell
        r = int(deflated + (inflated - deflated) * t)
        pygame.draw.circle(self.screen, POD, center_px, max(6, r), 2)

    def _draw_anchors(self) -> None:
        for (x, y) in self.world.anchors:
            rect = self._cell_rect(x, y).inflate(-self.cell // 2, -self.cell // 2)
            pygame.draw.rect(self.screen, ANCHOR, rect)

    def _draw_blocks(self) -> None:
        for (x, y) in self.world.blocks:
            pygame.draw.rect(self.screen, BLOCK, self._cell_rect(x, y))

    def _draw_airlock(self) -> None:
        # Staged at the landing zone until an assembler docks it at the dock cell.
        x, y = self.blueprint.airlock_cell() if self.world.airlock_docked else self.landing_zone
        pygame.draw.rect(self.screen, AIRLOCK, self._cell_rect(x, y))

    def _draw_grid(self) -> None:
        for x in range(self.world.w + 1):
            pygame.draw.line(
                self.screen, GRID, (x * self.cell, 0), (x * self.cell, self.h), 1
            )
        for y in range(self.world.h + 1):
            pygame.draw.line(
                self.screen,
                GRID,
                (0, y * self.cell),
                (self.world.w * self.cell, y * self.cell),
                1,
            )

    def _draw_robots(self) -> None:
        for r in self.fleet:
            if r.kind == "pod":
                continue   # drawn as the inflating ring by _draw_pod
            cx = r.x * self.cell + self.cell // 2
            cy = r.y * self.cell + self.cell // 2
            pygame.draw.circle(self.screen, r.color, (cx, cy), self.cell // 2 - 2)
            label = self.font.render(r.rid, True, LABEL)
            self.screen.blit(label, (cx - 8, cy - 22))

    def _goal_statuses(self) -> dict[str, tuple[bool, str]]:
        """Evaluate every goal directly against the sim world, latching each OK."""
        out: dict[str, tuple[bool, str]] = {}
        for goal in GOALS:
            if goal.name in self._latched:
                out[goal.name] = (True, self._latched[goal.name])
                continue
            ok, reason = goal.is_done(self.world, self.blueprint)
            if ok:
                self._latched[goal.name] = reason
            out[goal.name] = (ok, reason)
        return out

    def _draw_panel(self, sim_time: float) -> None:
        x0 = self.world.w * self.cell + 12
        y = 12

        def line(text: str, font=None) -> None:
            """Blit one panel line, word-wrapping to the panel width."""
            nonlocal y
            f = font or self.font
            if not text:
                y += f.get_height() + 4
                return
            max_w = self.panel_w - 24
            indent = 0
            cur = ""
            for word in text.split(" "):
                trial = word if not cur else f"{cur} {word}"
                if not cur or f.size(trial)[0] <= max_w:
                    cur = trial
                    continue
                surf = f.render(cur, True, TEXT)
                self.screen.blit(surf, (x0 + indent, y))
                y += surf.get_height() + 4
                indent = 12          # hanging indent for wrapped continuations
                cur = word
            surf = f.render(cur, True, TEXT)
            self.screen.blit(surf, (x0 + indent, y))
            y += surf.get_height() + 4

        line(f"t = {sim_time:6.1f}s")
        line("")
        line("Goals:", self.big)
        statuses = self._goal_statuses()
        for goal in GOALS:
            ok, reason = statuses[goal.name]
            mark = "OK" if ok else "X "
            line(f" {goal.label} {mark} {reason}")
        line("")
        line("Fleet:", self.big)
        line(f" {'id':<2} {'type':<9} {'status':<10} {'bat':>4}")
        for r in self.fleet:
            line(f" {r.rid:<2} {r.kind:9s} {r.state:10s} {r.battery:4.0f}%")

        line("")
        self._draw_legend(x0, y)

    def _draw_colorbar(self) -> None:
        bar_w = 18
        bar_h = 200
        x = self.world.w * self.cell + self.panel_w - bar_w - 36
        y = self.h - bar_h - 24

        hi = self._elev_lo + self._elev_span
        for i in range(bar_h):
            # top → display max (white), bottom → display min (black)
            e = hi - (i / max(1, bar_h - 1)) * self._elev_span
            g = self._shade(e)
            pygame.draw.line(self.screen, (g, g, g), (x, y + i), (x + bar_w, y + i))
        pygame.draw.rect(self.screen, TEXT, (x, y, bar_w, bar_h), 1)

        title = self.font.render("elev", True, TEXT)
        self.screen.blit(title, (x - 4, y - 18))
        unit = self.font.render("m", True, TEXT)
        self.screen.blit(unit, (x + 4, y + bar_h + 4))

        n_ticks = 7
        for i in range(n_ticks):
            val = hi - self._elev_span * i / (n_ticks - 1)
            ty = y + int((1 - (val - self._elev_lo) / self._elev_span) * bar_h)
            surf = self.font.render(f"{val:+.2f}", True, TEXT)
            pygame.draw.line(
                self.screen, TEXT, (x + bar_w, ty), (x + bar_w + 3, ty), 1
            )
            self.screen.blit(surf, (x + bar_w + 6, ty - surf.get_height() // 2))

    def _draw_legend(self, x0: int, y: int) -> None:
        from ..sim.robots import Assembler, Loader, Producer

        entries: list[tuple[str, tuple[int, int, int], str]] = [
            ("Loader",       Loader.color,    "circle"),
            ("Producer",     Producer.color,  "circle"),
            ("Assembler",    Assembler.color, "circle"),
            ("Pod",          POD,             "ring"),
            ("Anchor",       ANCHOR,          "square"),
            ("Block",        BLOCK,           "square"),
            ("Airlock",      AIRLOCK,         "square"),
        ]
        line_h = self.font.get_height() + 4
        sw = 14  # swatch size

        title = self.big.render("Legend", True, TEXT)
        self.screen.blit(title, (x0, y))
        y += self.big.get_height() + 6

        for name, color, shape in entries:
            sx, sy = x0, y + (line_h - sw) // 2
            rect = pygame.Rect(sx, sy, sw, sw)
            if shape == "square":
                pygame.draw.rect(self.screen, color, rect)
            elif shape == "outline":
                pygame.draw.rect(self.screen, color, rect, 1)
            elif shape == "ring":
                pygame.draw.circle(self.screen, color, rect.center, sw // 2, 2)
            else:  # circle
                pygame.draw.circle(self.screen, color, rect.center, sw // 2 - 1)
            label = self.font.render(name, True, TEXT)
            self.screen.blit(label, (x0 + sw + 8, y))
            y += line_h
