from __future__ import annotations

import pygame

from sim import blueprint
from sim.config import CONFIG
from sim.robots import Robot
from sim.world import World


BG = (12, 12, 18)
GRID = (30, 30, 40)
POD = (80, 200, 120)
ANCHOR = (255, 90, 90)
BLOCK = (80, 130, 220)
AIRLOCK = (90, 220, 255)
FOUNDATION_OK = (80, 200, 120)
TEXT = (230, 230, 240)


class Renderer:
    def __init__(self, world: World, fleet: list[Robot]):
        pygame.init()
        pygame.display.set_caption("moon_base_sim")
        self.world = world
        self.fleet = fleet
        self.cell = CONFIG.cell_size
        self.panel_w = 260
        self.w = world.w * self.cell + self.panel_w
        self.h = world.h * self.cell
        self.screen = pygame.display.set_mode((self.w, self.h))
        self.font = pygame.font.SysFont("monospace", 14)
        self.big = pygame.font.SysFont("monospace", 18, bold=True)
        self.clock = pygame.time.Clock()

    def _cell_rect(self, x: int, y: int) -> pygame.Rect:
        return pygame.Rect(x * self.cell, y * self.cell, self.cell, self.cell)

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
        pygame.display.flip()
        self.clock.tick(CONFIG.target_fps)
        return True

    def _draw_terrain(self) -> None:
        foundation = set(self.world.foundation_cells())
        tol = CONFIG.elevation_tolerance_cm
        for y in range(self.world.h):
            for x in range(self.world.w):
                dev = abs(self.world.elevation[y][x])
                g = min(255, int(dev / 15.0 * 255))
                pygame.draw.rect(self.screen, (g, g, g), self._cell_rect(x, y))
                if (x, y) in foundation and dev <= tol:
                    pygame.draw.rect(
                        self.screen, FOUNDATION_OK, self._cell_rect(x, y), 1
                    )

    def _draw_pod(self) -> None:
        cx, cy = CONFIG.pod_center
        center_px = (cx * self.cell + self.cell // 2, cy * self.cell + self.cell // 2)
        radius_px = (CONFIG.dome_radius - 2) * self.cell
        pygame.draw.circle(self.screen, POD, center_px, max(6, radius_px // 2), 2)

    def _draw_anchors(self) -> None:
        planned = blueprint.anchor_cells()
        for (x, y) in planned:
            rect = self._cell_rect(x, y).inflate(-self.cell // 2, -self.cell // 2)
            placed = (x, y) in self.world.anchors
            color = ANCHOR if placed else (80, 40, 40)
            pygame.draw.rect(self.screen, color, rect)

    def _draw_blocks(self) -> None:
        for (x, y) in self.world.blocks:
            pygame.draw.rect(self.screen, BLOCK, self._cell_rect(x, y))

    def _draw_airlock(self) -> None:
        x, y = blueprint.airlock_cell()
        color = AIRLOCK if self.world.airlock_docked else (40, 80, 100)
        pygame.draw.rect(self.screen, color, self._cell_rect(x, y))

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
            cx = r.x * self.cell + self.cell // 2
            cy = r.y * self.cell + self.cell // 2
            pygame.draw.circle(self.screen, r.color, (cx, cy), self.cell // 2 - 2)
            label = self.font.render(r.rid, True, TEXT)
            self.screen.blit(label, (cx - 8, cy - 22))

    def _draw_panel(self, sim_time: float) -> None:
        x0 = self.world.w * self.cell + 12
        y = 12

        def line(text: str, font=None) -> None:
            nonlocal y
            surf = (font or self.font).render(text, True, TEXT)
            self.screen.blit(surf, (x0, y))
            y += surf.get_height() + 4

        line(f"Phase {self.world.phase}: {self.world.phase_label}", self.big)
        line(f"t = {sim_time:6.1f}s")
        line("")
        line(f"Foundation dev : {self.world.foundation_variance_cm():5.2f} cm")
        line(f"Anchors        : {len(self.world.anchors)} / {CONFIG.num_anchors}")
        line(
            f"Blocks placed  : {len(self.world.blocks)} / {len(blueprint.dome_ring_cells())}"
        )
        line(f"Airlock docked : {self.world.airlock_docked}")
        line("")
        line("Fleet:", self.big)
        for r in self.fleet:
            line(f" {r.rid} {r.kind:9s} {r.state:10s} {r.battery:4.0f}%")

        self._draw_legend(x0)

    def _draw_legend(self, x0: int) -> None:
        from sim.robots import Assembler, Loader, Producer

        entries: list[tuple[str, tuple[int, int, int], str]] = [
            ("Loader",       Loader.color,    "circle"),
            ("Producer",     Producer.color,  "circle"),
            ("Assembler",    Assembler.color, "circle"),
            ("Pod",          POD,             "ring"),
            ("Anchor",       ANCHOR,          "square"),
            ("Block",        BLOCK,           "square"),
            ("Airlock",      AIRLOCK,         "square"),
            ("Foundation",   FOUNDATION_OK,   "outline"),
        ]
        line_h = self.font.get_height() + 4
        sw = 14  # swatch size
        block_h = self.big.get_height() + 6 + len(entries) * line_h
        y = self.h - block_h - 8

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
