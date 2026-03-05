import json
import os
import random
import sys
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

import pygame

WIDTH, HEIGHT = 1100, 700
FPS = 60
MILES_TO_GOAL = 2000

WHITE = (245, 245, 245)
BLACK = (20, 20, 20)
GRAY = (210, 210, 210)
DARK = (45, 45, 45)
RED = (200, 60, 60)
GREEN = (60, 180, 90)
BLUE = (80, 140, 220)
YELLOW = (235, 200, 70)
ORANGE = (245, 160, 60)

pygame.init()
pygame.display.set_caption("Trail Game (Oregon-ish) - Complete")
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

FONT = pygame.font.SysFont("consolas", 18)
FONT_B = pygame.font.SysFont("consolas", 22, bold=True)
FONT_H = pygame.font.SysFont("consolas", 28, bold=True)

SAVE_PATH = "trail_save.json"

STARTING_CLASSES = {
    "Rich": 50000,
    "Middle Class": 10000,
    "Poor": 500
}

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def draw_text(surface, text, x, y, color=BLACK, font=FONT):
    surface.blit(font.render(text, True, color), (x, y))


def wrap_text(text: str, font: pygame.font.Font, max_width: int):
    """Return a list of wrapped lines that fit max_width."""
    words = text.split(" ")
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if not test:
            continue
        if font.size(test)[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            # Hard-split a single long token if needed
            if font.size(w)[0] > max_width:
                chunk = ""
                for ch in w:
                    t2 = chunk + ch
                    if font.size(t2)[0] <= max_width:
                        chunk = t2
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                cur = chunk
            else:
                cur = w
    if cur:
        lines.append(cur)
    return lines

def draw_text_clipped(surface, text, x, y, clip_rect: pygame.Rect, color=BLACK, font=FONT):
    prev_clip = surface.get_clip()
    surface.set_clip(clip_rect)
    surface.blit(font.render(text, True, color), (x, y))
    surface.set_clip(prev_clip)

def draw_wrapped_text(surface, text, x, y, clip_rect: pygame.Rect, color=BLACK, font=FONT, line_height=None, bullet_prefix=""):
    """Word-wrap text and draw inside clip_rect starting at (x,y). Returns final y."""
    if line_height is None:
        line_height = font.get_linesize()
    max_width = max(10, clip_rect.width - (x - clip_rect.x) - 8)
    lines = wrap_text(text, font, max_width)
    for i, line in enumerate(lines):
        prefix = bullet_prefix if (i == 0 and bullet_prefix) else (" " * len(bullet_prefix) if bullet_prefix else "")
        draw_text_clipped(surface, prefix + line, x, y, clip_rect, color=color, font=font)
        y += line_height
    return y

def weighted_choice(weighted_items):
    total = sum(w for _, w in weighted_items)
    r = random.uniform(0, total)
    upto = 0
    for item, weight in weighted_items:
        if upto + weight >= r:
            return item
        upto += weight
    return weighted_items[-1][0]

class Button:
    def __init__(self, rect, text, bg=GRAY, fg=BLACK):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.bg = bg
        self.fg = fg

    def draw(self, surface):
        mx, my = pygame.mouse.get_pos()
        hovered = self.rect.collidepoint(mx, my)
        color = tuple(clamp(c - 25, 0, 255) for c in self.bg) if hovered else self.bg
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, DARK, self.rect, 2, border_radius=10)

        label = FONT_B.render(self.text, True, self.fg)
        label_rect = label.get_rect(center=self.rect.center)
        surface.blit(label, label_rect)

    def clicked(self, event):
        return event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos)

class InputBox:
    def __init__(self, rect, text="", label="", digits_only=False, max_len=16):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.label = label
        self.active = False
        self.digits_only = digits_only
        self.max_len = max_len

    def value_int(self) -> int:
        try:
            return int(self.text) if self.text.strip() else 0
        except ValueError:
            return 0

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.active = self.rect.collidepoint(event.pos)

        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                self.active = False
            else:
                ch = event.unicode
                if self.digits_only and not ch.isdigit():
                    return
                if len(self.text) < self.max_len:
                    if self.digits_only and self.text == "0":
                        self.text = ch
                    else:
                        self.text += ch

            if self.digits_only and self.text == "":
                self.text = "0"

    def draw(self, surface):
        if self.label:
            draw_text(surface, self.label, self.rect.x, self.rect.y - 22, BLACK, FONT)

        bg = (255, 255, 255) if self.active else (245, 245, 245)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, BLUE if self.active else DARK, self.rect, 2, border_radius=8)
        draw_text(surface, self.text if self.text else "", self.rect.x + 10, self.rect.y + 8, BLACK, FONT_B)

@dataclass
class PartyMember:
    name: str
    health: int = 100
    status: str = "OK"  # OK / Sick / Injured / Dead

    def is_alive(self) -> bool:
        return self.health > 0 and self.status != "Dead"

    def apply_health(self, delta: int):
        if self.status == "Dead":
            return
        self.health = clamp(self.health + delta, 0, 100)
        if self.health <= 0:
            self.health = 0
            self.status = "Dead"

@dataclass
class Landmark:
    miles: int
    name: str
    kind: str  # town/landmark/river
    difficulty: int = 1

class HuntingMiniGame:
    def __init__(self):
        self.active = False
        self.time_left = 0.0
        self.hits = 0
        self.shots = 0
        self.food_gained = 0
        self.targets = []
        self.spawn_cooldown = 0.0

    def start(self, duration_sec=35):
        self.active = True
        self.time_left = float(duration_sec)
        self.hits = 0
        self.shots = 0
        self.food_gained = 0
        self.targets = []
        self.spawn_cooldown = 0.0

    def end(self):
        self.active = False

    def spawn_target(self):
        kind = random.choice(["rabbit", "deer", "bear"])
        if kind == "rabbit":
            radius = 16
            speed = random.uniform(220, 320)
            food = random.randint(15, 30)
            hp = 1
        elif kind == "deer":
            radius = 22
            speed = random.uniform(160, 240)
            food = random.randint(35, 60)
            hp = 1
        else:
            radius = 28
            speed = random.uniform(120, 180)
            food = random.randint(70, 110)
            hp = 2

        from_left = random.random() < 0.5
        y = random.randint(170, 520)
        x = -40 if from_left else WIDTH + 40
        vx = speed if from_left else -speed
        self.targets.append({"kind": kind, "x": float(x), "y": float(y), "vx": float(vx), "r": radius, "food": food, "hp": hp})

    def update(self, dt, weather="Clear"):
        self.time_left -= dt
        if self.time_left <= 0:
            self.time_left = 0
            self.end()
            return

        base_spawn = 0.55
        if weather in ("Storm", "Snow"):
            base_spawn *= 1.35
        elif weather in ("Rain", "Wind"):
            base_spawn *= 1.15

        self.spawn_cooldown -= dt
        if self.spawn_cooldown <= 0:
            self.spawn_target()
            self.spawn_cooldown = base_spawn * random.uniform(0.75, 1.25)

        for t in self.targets:
            t["x"] += t["vx"] * dt

        self.targets = [t for t in self.targets if -80 < t["x"] < WIDTH + 80]

    def try_shot(self, mx, my):
        hit_target = None
        best_dist = 10**18
        for t in self.targets:
            dx = mx - t["x"]
            dy = my - t["y"]
            dist2 = dx*dx + dy*dy
            if dist2 <= (t["r"] * t["r"]) and dist2 < best_dist:
                best_dist = dist2
                hit_target = t
        if not hit_target:
            return False, 0

        hit_target["hp"] -= 1
        if hit_target["hp"] <= 0:
            food = hit_target["food"]
            self.food_gained += food
            self.hits += 1
            self.targets.remove(hit_target)
            return True, food
        return True, 0

    def draw(self, surface):
        pygame.draw.rect(surface, (235, 235, 235), (60, 120, WIDTH-120, HEIGHT-240), border_radius=18)
        pygame.draw.rect(surface, DARK, (60, 120, WIDTH-120, HEIGHT-240), 2, border_radius=18)

        draw_text(surface, "Hunting", 80, 135, BLACK, FONT_H)
        draw_text(surface, f"Time: {self.time_left:0.1f}s", 80, 175, BLACK, FONT_B)
        draw_text(surface, f"Hits: {self.hits}  Shots: {self.shots}  Food gained: {self.food_gained}", 80, 205, BLACK, FONT)

        for t in self.targets:
            pygame.draw.circle(surface, (200, 200, 200), (int(t["x"]), int(t["y"])), t["r"])
            pygame.draw.circle(surface, DARK, (int(t["x"]), int(t["y"])), t["r"], 2)
            draw_text(surface, t["kind"], int(t["x"]) - t["r"], int(t["y"]) - t["r"] - 18, BLACK, FONT)

        mx, my = pygame.mouse.get_pos()
        pygame.draw.circle(surface, DARK, (mx, my), 14, 2)
        pygame.draw.line(surface, DARK, (mx - 18, my), (mx + 18, my), 2)
        pygame.draw.line(surface, DARK, (mx, my - 18), (mx, my + 18), 2)

class Game:
    def __init__(self):
        self.reset()

    def reset(self):
        self.day = 1
        self.season = "Spring"
        self.miles_traveled = 0
        self.weather = "Clear"

        self.player_class = "Middle Class"
        self.cash = STARTING_CLASSES[self.player_class]

        self.party: List[PartyMember] = []
        self.morale = 80
        self.wagon_condition = 100

        self.food = 500
        self.ammo = 40
        self.medicine = 6

        self.pace = "Steady"
        self.rations = "Normal"

        self.landmarks: List[Landmark] = self.build_landmarks()
        self.next_landmark_index = 0

        self.log = ["Welcome to the trail. Choose a class, then name your party.", "Tip: Press S to save, L to load."]
        self.game_over = False
        self.win = False

        self.mode = "START_CLASS"  # START_CLASS -> START_NAMES -> MAIN
        self.modal_title = ""
        self.modal_body: List[str] = []
        self.modal_actions: List[Tuple[str, str]] = []
        self.pending_river: Optional[Landmark] = None

        self.hunt_game = HuntingMiniGame()

    def build_landmarks(self) -> List[Landmark]:
        landmarks = [
            Landmark(120, "Independence Camp", "town"),
            Landmark(260, "Big Blue River", "river", difficulty=1),
            Landmark(400, "Fort Kearny", "town"),
            Landmark(540, "Chimney Rock", "landmark"),
            Landmark(650, "Platte River Crossing", "river", difficulty=2),
            Landmark(800, "Fort Laramie", "town"),
            Landmark(980, "Independence Rock", "landmark"),
            Landmark(1120, "Sweetwater River", "river", difficulty=2),
            Landmark(1300, "South Pass", "landmark"),
            Landmark(1440, "Fort Bridger", "town"),
            Landmark(1600, "Snake River", "river", difficulty=3),
            Landmark(1750, "Blue Mountains", "landmark"),
            Landmark(1860, "The Dalles", "town"),
        ]
        landmarks.sort(key=lambda l: l.miles)
        return landmarks

    def add_log(self, msg: str):
        self.log.append(msg)
        self.log = self.log[-12:]

    def alive_members(self) -> List[PartyMember]:
        return [m for m in self.party if m.is_alive()]

    def party_count_alive(self) -> int:
        return len(self.alive_members())

    def average_health(self) -> int:
        alive = self.alive_members()
        if not alive:
            return 0
        return int(sum(m.health for m in alive) / len(alive))

    def set_season(self):
        if self.day <= 30:
            self.season = "Spring"
        elif self.day <= 60:
            self.season = "Summer"
        elif self.day <= 90:
            self.season = "Fall"
        else:
            self.season = "Winter"

    def roll_weather(self):
        r = random.random()
        if self.season == "Winter":
            self.weather = "Snow" if r < 0.40 else ("Cold" if r < 0.75 else "Clear")
        elif self.season == "Fall":
            self.weather = "Rain" if r < 0.25 else ("Wind" if r < 0.45 else "Clear")
        elif self.season == "Summer":
            self.weather = "Hot" if r < 0.20 else ("Storm" if r < 0.30 else "Clear")
        else:
            self.weather = "Rain" if r < 0.25 else ("Storm" if r < 0.35 else "Clear")

    def price_multiplier(self):
        base = 1.0 + (self.day / 120.0) * 0.6
        if self.season == "Winter":
            base *= 1.15
        return base

    def shop_prices(self) -> Dict[str, int]:
        mult = self.price_multiplier()
        return {"food10": max(1, int(1 * mult)), "ammo1": max(1, int(2 * mult)), "med1": max(5, int(18 * mult)), "repair": max(10, int(20 * mult))}

    def buy_shop(self, food10: int, ammo1: int, med1: int, repair: int):
        prices = self.shop_prices()
        cost = food10 * prices["food10"] + ammo1 * prices["ammo1"] + med1 * prices["med1"] + repair * prices["repair"]
        if cost <= 0:
            return False, "Nothing to buy."
        if cost > self.cash:
            return False, "Not enough cash."
        self.cash -= cost
        self.food += food10 * 10
        self.ammo += ammo1
        self.medicine += med1
        if repair > 0:
            self.wagon_condition = clamp(self.wagon_condition + repair * 18, 0, 100)
        return True, f"Spent ${cost}. +{food10*10} food, +{ammo1} ammo, +{med1} med, +{repair*18}% wagon."

    def ration_factor(self):
        return {"Meager": 0.7, "Normal": 1.0, "Filling": 1.25}[self.rations]

    def pace_factor(self):
        return {"Leisurely": 0.8, "Steady": 1.0, "Grueling": 1.25}[self.pace]

    def daily_food_consumption(self):
        base = 8 * max(1, self.party_count_alive())
        return int(base * self.ration_factor())

    def consume_food(self):
        need = self.daily_food_consumption()
        if self.food >= need:
            self.food -= need
        else:
            self.food = 0
            for m in self.alive_members():
                m.apply_health(-6)
            self.morale = clamp(self.morale - 6, 0, 100)
            self.add_log("Food ran out! The party suffers badly.")

    def apply_daily_wear(self):
        wear = 1.0 * self.pace_factor()
        if self.weather in ("Storm", "Snow"):
            wear *= 1.8
        elif self.weather in ("Rain", "Wind", "Cold", "Hot"):
            wear *= 1.3
        self.wagon_condition = clamp(self.wagon_condition - int(wear), 0, 100)

    def apply_daily_health(self):
        for m in self.alive_members():
            delta = 0
            if self.rations == "Meager":
                delta -= 2
            elif self.rations == "Filling":
                delta += 1
            if self.morale < 30:
                delta -= 1
            elif self.morale > 70:
                delta += 1
            if self.weather == "Snow":
                delta -= 3
            elif self.weather == "Cold":
                delta -= 2
            elif self.weather == "Storm":
                delta -= 2
            elif self.weather == "Hot":
                delta -= 1
            if self.wagon_condition < 25:
                delta -= 2
            if m.status == "Sick":
                delta -= 2
            if m.status == "Injured":
                delta -= 1
            m.apply_health(delta)

    def apply_daily_morale(self):
        delta = 0
        if self.food <= 0:
            delta -= 5
        if self.rations == "Meager":
            delta -= 1
        if self.rations == "Filling":
            delta += 1
        if self.weather == "Clear":
            delta += 1
        if self.weather in ("Storm", "Snow"):
            delta -= 2
        if self.party_count_alive() <= 2:
            delta -= 2
        self.morale = clamp(self.morale + delta, 0, 100)

    def advance_day(self, context="travel"):
        if self.game_over:
            return
        self.day += 1
        self.set_season()
        self.roll_weather()
        self.consume_food()
        self.apply_daily_wear()
        self.apply_daily_health()
        self.apply_daily_morale()
        self.roll_event(context=context)
        self.check_end_conditions()

    def roll_event(self, context="travel"):
        if self.game_over or self.party_count_alive() <= 0:
            return
        chance = 0.22 if context == "travel" else 0.10
        if self.season == "Winter":
            chance += 0.07
        if self.pace == "Grueling":
            chance += 0.05
        if random.random() > chance:
            return

        event = weighted_choice([("illness", 22), ("wagon_damage", 18), ("bandits", 12), ("find_food", 12), ("bad_weather", 10), ("lose_way", 10), ("help_traveler", 8)])
        if event == "illness":
            victim = random.choice(self.alive_members())
            severity = random.choice([1, 2, 3])
            victim.status = "Sick"
            victim.apply_health(-(6 * severity))
            self.add_log(f"Event: {victim.name} fell ill (-{6*severity} health).")
            if self.medicine > 0 and victim.health < 70 and random.random() < 0.70:
                self.medicine -= 1
                victim.apply_health(+12)
                if victim.health >= 60 and victim.status != "Dead":
                    victim.status = "OK"
                self.add_log(f"You used medicine on {victim.name} (+12 health).")
        elif event == "wagon_damage":
            dmg = random.randint(6, 18)
            self.wagon_condition = clamp(self.wagon_condition - dmg, 0, 100)
            self.add_log(f"Event: Wagon damage (-{dmg}% condition).")
        elif event == "bandits":
            if self.ammo > 0:
                spent = min(random.randint(5, 12), self.ammo)
                self.ammo -= spent
                loss_cash = min(random.randint(10, 35), self.cash)
                self.cash -= loss_cash
                self.morale = clamp(self.morale - 6, 0, 100)
                self.add_log(f"Event: Bandits! You fought them off (-{spent} ammo, -${loss_cash}).")
            else:
                loss_cash = min(random.randint(30, 80), self.cash)
                self.cash -= loss_cash
                victim = random.choice(self.alive_members())
                victim.status = "Injured"
                victim.apply_health(-12)
                self.add_log(f"Event: Bandits! {victim.name} was injured (-12 health, -${loss_cash}).")
                self.morale = clamp(self.morale - 10, 0, 100)
        elif event == "find_food":
            found = random.randint(20, 70)
            self.food += found
            self.add_log(f"Event: Found supplies (+{found} food).")
        elif event == "bad_weather":
            self.weather = random.choice(["Storm", "Snow", "Rain"])
            self.add_log(f"Event: Weather turns bad ({self.weather}).")
        elif event == "lose_way":
            lost = random.randint(5, 20)
            self.miles_traveled = max(0, self.miles_traveled - lost)
            self.morale = clamp(self.morale - 4, 0, 100)
            self.add_log(f"Event: You lost the trail (-{lost} miles).")
        elif event == "help_traveler":
            if self.food >= 30 and random.random() < 0.6:
                self.food -= 30
                self.morale = clamp(self.morale + 8, 0, 100)
                self.add_log("Event: You helped a traveler (-30 food, +8 morale).")
            else:
                self.add_log("Event: You met a traveler, but couldn’t help much.")

    def toggle_pace(self):
        self.pace = "Steady" if self.pace == "Leisurely" else ("Grueling" if self.pace == "Steady" else "Leisurely")
        self.add_log(f"Pace set to: {self.pace}")

    def toggle_rations(self):
        self.rations = "Normal" if self.rations == "Meager" else ("Filling" if self.rations == "Normal" else "Meager")
        self.add_log(f"Rations set to: {self.rations}")

    def rest(self):
        for m in self.alive_members():
            m.apply_health(+6)
            if m.status in ("Sick", "Injured") and m.health >= 70 and random.random() < 0.5:
                m.status = "OK"
        self.morale = clamp(self.morale + 4, 0, 100)
        self.add_log("Rest: party recovers.")
        self.advance_day(context="rest")

    def hunt(self):
        if self.ammo <= 0:
            self.add_log("Hunt: No ammo.")
            self.morale = clamp(self.morale - 2, 0, 100)
            self.advance_day(context="rest")
            return
        self.mode = "HUNT"
        self.hunt_game.start(duration_sec=35)
        self.add_log("Hunt started: click animals to shoot (1 ammo per shot).")

    def travel(self):
        if self.party_count_alive() <= 0:
            return
        base = 18 * self.pace_factor()
        mod = 1.0 if self.weather == "Clear" else (0.85 if self.weather in ("Wind", "Cold", "Hot", "Rain") else 0.65)
        wagon_mod = 0.6 + (self.wagon_condition / 100.0) * 0.6
        party_mod = 0.75 + (self.party_count_alive() / max(1, len(self.party))) * 0.35
        miles = max(1, int(base * mod * wagon_mod * party_mod))
        prev = self.miles_traveled
        self.miles_traveled += miles
        self.add_log(f"Travel: +{miles} miles (Weather: {self.weather}, Pace: {self.pace}).")
        self.advance_day(context="travel")
        self.check_landmark_reached(prev, self.miles_traveled)

    def check_landmark_reached(self, prev_miles: int, new_miles: int):
        while self.next_landmark_index < len(self.landmarks):
            lm = self.landmarks[self.next_landmark_index]
            if prev_miles < lm.miles <= new_miles:
                self.next_landmark_index += 1
                self.trigger_landmark(lm)
                break
            break

    def trigger_landmark(self, lm: Landmark):
        if lm.kind == "town":
            self.mode = "LANDMARK"
            self.modal_title = f"Town: {lm.name}"
            self.modal_body = [f"You arrive at {lm.name} (mile {lm.miles}).", "You can shop here, rest, or move on."]
            self.modal_actions = [("Shop", "OPEN_SHOP"), ("Rest (1 day)", "REST"), ("Continue", "CLOSE_MODAL")]
            self.add_log(f"Arrived at {lm.name}.")
        elif lm.kind == "river":
            self.mode = "RIVER"
            self.pending_river = lm
            self.modal_title = f"River: {lm.name}"
            self.modal_body = [f"You reached {lm.name} (mile {lm.miles}).", f"Crossing difficulty: {lm.difficulty}/3",
                               "Choose how to cross:", "- Ford: risky, no cash", "- Caulk: uses wagon condition", "- Ferry: costs cash, safer"]
            self.modal_actions = [("Ford", "RIVER_FORD"), ("Caulk", "RIVER_CAULK"), ("Ferry", "RIVER_FERRY"), ("Wait (1 day)", "RIVER_WAIT")]
            self.add_log(f"Reached river: {lm.name}.")
        else:
            self.mode = "LANDMARK"
            self.modal_title = f"Landmark: {lm.name}"
            outcome = random.random()
            if outcome < 0.40:
                bonus = random.randint(10, 35)
                self.food += bonus
                self.modal_body = [f"You pass {lm.name} (mile {lm.miles}).", f"You find supplies (+{bonus} food)."]
            elif outcome < 0.70:
                self.morale = clamp(self.morale + 6, 0, 100)
                self.modal_body = [f"You pass {lm.name} (mile {lm.miles}).", "The view lifts spirits (+6 morale)."]
            else:
                dmg = random.randint(5, 15)
                self.wagon_condition = clamp(self.wagon_condition - dmg, 0, 100)
                self.modal_body = [f"You pass {lm.name} (mile {lm.miles}).", f"Rough terrain strains wagon (-{dmg}% condition)."]
            self.modal_actions = [("Continue", "CLOSE_MODAL")]
            self.add_log(f"Passed {lm.name}.")

    def resolve_river_crossing(self, method: str):
        lm = self.pending_river
        if not lm:
            self.mode = "MAIN"
            return
        difficulty = lm.difficulty
        avg_h = self.average_health()
        wagon = self.wagon_condition
        winter_penalty = 0.08 if self.season == "Winter" else 0.0
        low_health_penalty = 0.06 if avg_h < 60 else 0.0
        bad_weather_penalty = 0.08 if self.weather in ("Storm", "Snow") else 0.0

        if method == "FORD":
            cost_cash, cost_wagon = 0, 0
            base_fail, base_injury, day_cost = 0.20 + 0.10*(difficulty-1), 0.18 + 0.08*(difficulty-1), 1
        elif method == "CAULK":
            cost_cash, cost_wagon = 0, 10 + 7*difficulty
            base_fail, base_injury, day_cost = 0.12 + 0.06*(difficulty-1), 0.12 + 0.06*(difficulty-1), 1
        else:
            cost_cash, cost_wagon = 25 + 20*difficulty, 0
            base_fail, base_injury, day_cost = 0.06 + 0.03*(difficulty-1), 0.06 + 0.03*(difficulty-1), 1
            if self.cash < cost_cash:
                self.modal_body = [f"You don't have enough cash for the ferry (${cost_cash} needed).", "Choose another method or wait."]
                return

        if cost_cash > 0:
            self.cash -= cost_cash
        if cost_wagon > 0:
            self.wagon_condition = clamp(self.wagon_condition - cost_wagon, 0, 100)

        fail_p = clamp(base_fail + winter_penalty + low_health_penalty + bad_weather_penalty + (0.06 if wagon < 30 else 0.0), 0.02, 0.75)
        injury_p = clamp(base_injury + winter_penalty + low_health_penalty + bad_weather_penalty, 0.02, 0.75)

        lines = [f"You attempt to cross by {method.title()}..."]
        for _ in range(day_cost):
            self.advance_day(context="rest")

        if random.random() < fail_p:
            food_lost = min(random.randint(20, 90), self.food)
            ammo_lost = min(random.randint(0, 12), self.ammo)
            cash_lost = min(random.randint(0, 40), self.cash)
            self.food -= food_lost
            self.ammo -= ammo_lost
            self.cash -= cash_lost
            self.morale = clamp(self.morale - 8, 0, 100)
            lines.append(f"Disaster! (-{food_lost} food, -{ammo_lost} ammo, -${cash_lost}).")
            if self.alive_members() and random.random() < 0.65:
                victim = random.choice(self.alive_members())
                victim.status = "Injured"
                victim.apply_health(-random.randint(10, 22))
                lines.append(f"{victim.name} is injured during the crossing.")
        else:
            lines.append("Success! You cross safely.")
            if method in ("FERRY", "CAULK"):
                self.morale = clamp(self.morale + 3, 0, 100)
            if self.alive_members() and random.random() < injury_p * 0.35:
                victim = random.choice(self.alive_members())
                victim.status = "Injured"
                victim.apply_health(-random.randint(6, 14))
                lines.append(f"{victim.name} gets hurt crossing (injured).")

        self.pending_river = None
        self.mode = "LANDMARK"
        self.modal_title = "River Crossing Result"
        self.modal_body = lines
        self.modal_actions = [("Continue", "CLOSE_MODAL")]

    def to_dict(self) -> Dict:
        return {"day": self.day, "season": self.season, "miles_traveled": self.miles_traveled, "weather": self.weather,
                "player_class": self.player_class, "party": [asdict(m) for m in self.party], "morale": self.morale,
                "wagon_condition": self.wagon_condition, "food": self.food, "ammo": self.ammo, "medicine": self.medicine,
                "cash": self.cash, "pace": self.pace, "rations": self.rations, "next_landmark_index": self.next_landmark_index,
                "game_over": self.game_over, "win": self.win, "log": self.log}

    def from_dict(self, d: Dict):
        self.day = int(d.get("day", 1))
        self.set_season()
        self.season = d.get("season", self.season)
        self.miles_traveled = int(d.get("miles_traveled", 0))
        self.weather = d.get("weather", "Clear")
        self.player_class = d.get("player_class", "Middle Class")
        self.party = [PartyMember(**m) for m in d.get("party", [])] or self.party
        self.morale = int(d.get("morale", 80))
        self.wagon_condition = int(d.get("wagon_condition", 100))
        self.food = int(d.get("food", 500))
        self.ammo = int(d.get("ammo", 40))
        self.medicine = int(d.get("medicine", 6))
        self.cash = int(d.get("cash", STARTING_CLASSES.get(self.player_class, 10000)))
        self.pace = d.get("pace", "Steady")
        self.rations = d.get("rations", "Normal")
        self.landmarks = self.build_landmarks()
        self.next_landmark_index = int(d.get("next_landmark_index", 0))
        self.game_over = bool(d.get("game_over", False))
        self.win = bool(d.get("win", False))
        self.log = d.get("log", self.log)[-12:]
        self.mode = "MAIN"
        self.modal_title = ""
        self.modal_body = []
        self.modal_actions = []
        self.pending_river = None
        self.hunt_game = HuntingMiniGame()

    def save(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True, f"Saved to {SAVE_PATH}"
        except Exception as e:
            return False, f"Save failed: {e}"

    def load(self):
        if not os.path.exists(SAVE_PATH):
            return False, f"No save found at {SAVE_PATH}"
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.from_dict(d)
            return True, f"Loaded from {SAVE_PATH}"
        except Exception as e:
            return False, f"Load failed: {e}"

    def check_end_conditions(self):
        if self.miles_traveled >= MILES_TO_GOAL:
            self.win = True
            self.game_over = True
            self.add_log("You reached your destination. You win!")
        if self.party_count_alive() <= 0:
            self.game_over = True
            self.win = False
            self.add_log("Everyone is gone. Game over.")
        if self.wagon_condition <= 0:
            self.game_over = True
            self.win = False
            self.add_log("Your wagon broke beyond repair. Game over.")
        if self.day > 160:
            self.game_over = True
            self.win = False
            self.add_log("Too many days passed. Winter wins. Game over.")

def draw_bar(x, y, w, h, pct, label, color_fill):
    pygame.draw.rect(screen, GRAY, (x, y, w, h), border_radius=8)
    fill_w = int(w * (pct / 100.0))
    pygame.draw.rect(screen, color_fill, (x, y, fill_w, h), border_radius=8)
    pygame.draw.rect(screen, DARK, (x, y, w, h), 2, border_radius=8)
    draw_text(screen, f"{label}: {pct}%", x + 8, y + 6, BLACK, FONT)

def draw_panel(rect, title):
    pygame.draw.rect(screen, (250, 250, 250), rect, border_radius=14)
    pygame.draw.rect(screen, DARK, rect, 2, border_radius=14)
    draw_text(screen, title, rect.x + 20, rect.y + 12, BLACK, FONT_B)

def main():
    game = Game()

    btn_rich = Button((390, 260, 320, 65), "Rich ($50,000)")
    btn_mid = Button((390, 345, 320, 65), "Middle Class ($10,000)")
    btn_poor = Button((390, 430, 320, 65), "Poor ($500)")

    name_boxes = [
        InputBox((420, 240, 320, 42), "", "Leader", digits_only=False, max_len=12),
        InputBox((420, 300, 320, 42), "", "Member 2", digits_only=False, max_len=12),
        InputBox((420, 360, 320, 42), "", "Member 3", digits_only=False, max_len=12),
        InputBox((420, 420, 320, 42), "", "Member 4", digits_only=False, max_len=12),
        InputBox((420, 480, 320, 42), "", "Member 5", digits_only=False, max_len=12),
    ]
    btn_start_journey = Button((450, 550, 260, 65), "Start Journey", bg=GREEN, fg=WHITE)

    btn_travel = Button((40, 585, 170, 55), "Travel", bg=BLUE, fg=WHITE)
    btn_rest = Button((220, 585, 170, 55), "Rest", bg=GREEN, fg=WHITE)
    btn_hunt = Button((400, 585, 170, 55), "Hunt", bg=YELLOW, fg=BLACK)
    btn_shop = Button((580, 585, 170, 55), "Shop")

    btn_pace = Button((40, 645, 170, 45), "Toggle Pace")
    btn_ration = Button((220, 645, 170, 45), "Toggle Rations")
    btn_save = Button((820, 585, 120, 55), "Save", bg=ORANGE, fg=BLACK)
    btn_load = Button((950, 585, 120, 55), "Load", bg=ORANGE, fg=BLACK)
    btn_reset = Button((820, 645, 250, 45), "Reset", bg=RED, fg=WHITE)

    shop_buy = Button((690, 520, 170, 50), "Buy", bg=GREEN, fg=WHITE)
    shop_leave = Button((880, 520, 170, 50), "Leave")
    shop_food = InputBox((720, 210, 160, 40), "0", "Food (x10)", digits_only=True, max_len=6)
    shop_ammo = InputBox((720, 290, 160, 40), "0", "Ammo (x1)", digits_only=True, max_len=6)
    shop_med = InputBox((720, 370, 160, 40), "0", "Medicine (x1)", digits_only=True, max_len=6)
    shop_rep = InputBox((720, 450, 160, 40), "0", "Repair kits (x1)", digits_only=True, max_len=6)

    modal_buttons = []

    def open_shop():
        game.mode = "SHOP"
        for b in (shop_food, shop_ammo, shop_med, shop_rep):
            b.text = "0"
            b.active = False
        game.add_log("Shop opened.")

    def close_modal():
        game.mode = "MAIN"
        game.modal_title = ""
        game.modal_body = []
        game.modal_actions = []
        game.pending_river = None

    def build_modal_buttons():
        nonlocal modal_buttons
        modal_buttons = []
        x0, y0, w, h, gap = 360, 520, 170, 50, 18
        for i, (txt, key) in enumerate(game.modal_actions):
            modal_buttons.append((Button((x0 + i*(w+gap), y0, w, h), txt), key))

    def handle_modal_action(key):
        if key == "CLOSE_MODAL":
            close_modal()
        elif key == "OPEN_SHOP":
            open_shop()
        elif key == "REST":
            close_modal()
            game.rest()
        elif key == "RIVER_FORD":
            game.resolve_river_crossing("FORD")
        elif key == "RIVER_CAULK":
            game.resolve_river_crossing("CAULK")
        elif key == "RIVER_FERRY":
            game.resolve_river_crossing("FERRY")
        elif key == "RIVER_WAIT":
            game.add_log("You wait by the river for conditions to improve.")
            game.advance_day(context="rest")
            if random.random() < 0.35:
                game.weather = "Clear"
            if game.pending_river:
                game.modal_body = [f"You wait at {game.pending_river.name}.", f"Weather now: {game.weather}",
                                   "Choose how to cross:", "- Ford: risky, no cash", "- Caulk: uses wagon condition", "- Ferry: costs cash, safer"]
        else:
            close_modal()

    while True:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()

            if btn_reset.clicked(event):
                game.reset()

            if event.type == pygame.KEYDOWN and game.mode not in ("START_CLASS", "START_NAMES"):
                if event.key == pygame.K_s:
                    ok, msg = game.save(); game.add_log(msg if ok else f"ERROR: {msg}")
                if event.key == pygame.K_l:
                    ok, msg = game.load(); game.add_log(msg if ok else f"ERROR: {msg}")

            if game.mode == "START_CLASS":
                if btn_rich.clicked(event):
                    game.player_class = "Rich"; game.cash = STARTING_CLASSES["Rich"]; game.mode = "START_NAMES"
                if btn_mid.clicked(event):
                    game.player_class = "Middle Class"; game.cash = STARTING_CLASSES["Middle Class"]; game.mode = "START_NAMES"
                if btn_poor.clicked(event):
                    game.player_class = "Poor"; game.cash = STARTING_CLASSES["Poor"]; game.mode = "START_NAMES"

            elif game.mode == "START_NAMES":
                for box in name_boxes:
                    box.handle_event(event)
                if btn_start_journey.clicked(event):
                    names = []
                    for i, box in enumerate(name_boxes, start=1):
                        n = box.text.strip() or f"Traveler{i}"
                        names.append(n[:12])
                    game.party = [PartyMember(n) for n in names]
                    game.mode = "MAIN"
                    game.add_log(f"Journey begins as {game.player_class} with ${game.cash}.")
                    game.add_log("Tip: Hunt is interactive (click to shoot).")

            elif game.mode == "MAIN":
                if btn_travel.clicked(event): game.travel()
                if btn_rest.clicked(event): game.rest()
                if btn_hunt.clicked(event): game.hunt()
                if btn_shop.clicked(event): open_shop()
                if btn_pace.clicked(event): game.toggle_pace()
                if btn_ration.clicked(event): game.toggle_rations()
                if btn_save.clicked(event):
                    ok, msg = game.save(); game.add_log(msg if ok else f"ERROR: {msg}")
                if btn_load.clicked(event):
                    ok, msg = game.load(); game.add_log(msg if ok else f"ERROR: {msg}")

            elif game.mode == "SHOP":
                for box in (shop_food, shop_ammo, shop_med, shop_rep):
                    box.handle_event(event)
                if shop_buy.clicked(event):
                    ok, msg = game.buy_shop(shop_food.value_int(), shop_ammo.value_int(), shop_med.value_int(), shop_rep.value_int())
                    game.add_log(f"Shop: {msg}")
                if shop_leave.clicked(event):
                    close_modal()

            elif game.mode in ("LANDMARK", "RIVER"):
                build_modal_buttons()
                for b, key in modal_buttons:
                    if b.clicked(event):
                        handle_modal_action(key)

            elif game.mode == "HUNT" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.ammo <= 0:
                    game.add_log("Out of ammo!")
                else:
                    game.ammo -= 1
                    game.hunt_game.shots += 1
                    hit, food = game.hunt_game.try_shot(*event.pos)
                    if hit and food > 0:
                        game.add_log(f"Hit! +{food} food")
                    elif hit:
                        game.add_log("Hit! (wounded)")
                    else:
                        game.add_log("Miss!")

        if game.mode == "HUNT":
            game.hunt_game.update(dt, weather=game.weather)
            if game.ammo <= 0:
                game.hunt_game.end()
            if not game.hunt_game.active:
                gained = game.hunt_game.food_gained
                game.food += gained
                game.morale = clamp(game.morale + min(6, gained // 25), 0, 100)
                game.add_log(f"Hunt finished. Total food gained: +{gained}")
                game.advance_day(context="travel")
                game.mode = "MAIN"

        screen.fill(WHITE)

        if game.mode == "START_CLASS":
            draw_text(screen, "Choose Your Starting Class", 320, 140, BLACK, FONT_H)
            draw_text(screen, "Rich is easiest, Poor is hardest (starting cash changes difficulty).", 260, 190, BLACK, FONT)
            btn_rich.draw(screen); btn_mid.draw(screen); btn_poor.draw(screen); btn_reset.draw(screen)
            pygame.display.flip(); continue

        if game.mode == "START_NAMES":
            draw_text(screen, "Name Your Party (5 members)", 340, 140, BLACK, FONT_H)
            draw_text(screen, f"Class: {game.player_class}  |  Starting Cash: ${game.cash}", 340, 180, BLACK, FONT)
            for box in name_boxes: box.draw(screen)
            btn_start_journey.draw(screen); btn_reset.draw(screen)
            pygame.display.flip(); continue

        draw_text(screen, "Trail Game (Oregon-ish) - Complete", 40, 18, BLACK, FONT_H)
        draw_text(screen, f"Day {game.day} | Season: {game.season} | Weather: {game.weather} | Class: {game.player_class} | Pace: {game.pace} | Rations: {game.rations}", 40, 56, BLACK, FONT)

        pygame.draw.rect(screen, GRAY, (40, 90, 1020, 28), border_radius=10)
        pct = clamp(int((game.miles_traveled / MILES_TO_GOAL) * 100), 0, 100)
        pygame.draw.rect(screen, BLUE, (40, 90, int(1020 * (pct / 100.0)), 28), border_radius=10)
        pygame.draw.rect(screen, DARK, (40, 90, 1020, 28), 2, border_radius=10)
        draw_text(screen, f"Miles: {game.miles_traveled}/{MILES_TO_GOAL} ({pct}%)", 50, 95)

        party_rect = pygame.Rect(40, 140, 660, 430)
        draw_panel(party_rect, "Party Status")

        avg = game.average_health()
        draw_bar(60, 185, 620, 30, avg, "Avg Health", GREEN if avg >= 50 else RED)
        draw_bar(60, 225, 620, 30, game.morale, "Morale", GREEN if game.morale >= 50 else RED)
        draw_bar(60, 265, 620, 30, game.wagon_condition, "Wagon", GREEN if game.wagon_condition >= 50 else RED)

        draw_text(screen, "Members:", 60, 312, BLACK, FONT_B)
        y = 345
        for m in game.party:
            c = RED if m.status == "Dead" else (ORANGE if m.status in ("Sick", "Injured") else BLACK)
            draw_text(screen, f"- {m.name:12}  Health: {m.health:3}  Status: {m.status}", 60, y, c, FONT)
            y += 26

        draw_text(screen, "Inventory:", 60, 500, BLACK, FONT_B)
        draw_text(screen, f"Food: {game.food}", 60, 530)
        draw_text(screen, f"Ammo: {game.ammo}", 220, 530)
        draw_text(screen, f"Medicine: {game.medicine}", 360, 530)
        draw_text(screen, f"Cash: ${game.cash}", 560, 530)

        log_rect = pygame.Rect(720, 140, 340, 430)
        draw_panel(log_rect, "Trail Log")

        if game.next_landmark_index < len(game.landmarks):
            next_lm = game.landmarks[game.next_landmark_index]
            dist = max(0, next_lm.miles - game.miles_traveled)
            # Next landmark (wrapped/clipped so it always fits)
            info_clip = pygame.Rect(log_rect.x + 20, log_rect.y + 58, log_rect.width - 40, 96)
            draw_wrapped_text(screen, f"Next: {next_lm.name} ({next_lm.kind})", log_rect.x + 20, log_rect.y + 58, info_clip, color=BLACK, font=FONT, line_height=22)
            draw_text_clipped(screen, f"In: {dist} miles", log_rect.x + 20, log_rect.y + 58 + 68, info_clip, color=BLACK, font=FONT)
        y = log_rect.y + 175
        clip = pygame.Rect(log_rect.x + 20, log_rect.y + 165, log_rect.width - 40, log_rect.height - 185)
        for line in game.log:
            y = draw_wrapped_text(screen, line, log_rect.x + 20, y, clip, color=BLACK, font=FONT, line_height=22, bullet_prefix="- ")
            y += 2
            if y > clip.bottom - 22:
                break
        btn_travel.draw(screen); btn_rest.draw(screen); btn_hunt.draw(screen); btn_shop.draw(screen)
        btn_pace.draw(screen); btn_ration.draw(screen); btn_save.draw(screen); btn_load.draw(screen); btn_reset.draw(screen)

        if game.mode in ("LANDMARK", "RIVER"):
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))
            modal = pygame.Rect(160, 160, 780, 420)
            pygame.draw.rect(screen, WHITE, modal, border_radius=18)
            pygame.draw.rect(screen, DARK, modal, 2, border_radius=18)
            draw_text(screen, game.modal_title, modal.x + 25, modal.y + 20, BLACK, FONT_H)
            yy = modal.y + 75
            body_clip = pygame.Rect(modal.x + 25, modal.y + 70, modal.width - 50, modal.height - 150)
            for line in game.modal_body:
                yy = draw_wrapped_text(screen, line, modal.x + 25, yy, body_clip, color=BLACK, font=FONT, line_height=24)
                yy += 2
                if yy > body_clip.bottom - 24:
                    break
            build_modal_buttons()
            for b, _ in modal_buttons: b.draw(screen)

        if game.mode == "SHOP":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))
            modal = pygame.Rect(140, 140, 820, 470)
            pygame.draw.rect(screen, WHITE, modal, border_radius=18)
            pygame.draw.rect(screen, DARK, modal, 2, border_radius=18)
            draw_text(screen, "Shop", modal.x + 25, modal.y + 20, BLACK, FONT_H)
            prices = game.shop_prices()
            draw_text(screen, "Prices:", modal.x + 25, modal.y + 70, BLACK, FONT_B)
            prices_clip = pygame.Rect(modal.x + 25, modal.y + 98, 360, 140)
            yy_p = modal.y + 100
            yy_p = draw_wrapped_text(screen, f"10 food = ${prices['food10']}", modal.x + 25, yy_p, prices_clip, color=BLACK, font=FONT, line_height=24)
            yy_p = draw_wrapped_text(screen, f"1 ammo = ${prices['ammo1']}", modal.x + 25, yy_p, prices_clip, color=BLACK, font=FONT, line_height=24)
            yy_p = draw_wrapped_text(screen, f"1 med = ${prices['med1']}", modal.x + 25, yy_p, prices_clip, color=BLACK, font=FONT, line_height=24)
            yy_p = draw_wrapped_text(screen, f"repair kit = ${prices['repair']} (adds +18% wagon)", modal.x + 25, yy_p, prices_clip, color=BLACK, font=FONT, line_height=24)
            draw_text(screen, "Enter quantities:", modal.x + 400, modal.y + 45, BLACK, FONT_B)
            shop_food.rect.topleft = (modal.x + 430, modal.y + 115)
            shop_ammo.rect.topleft = (modal.x + 430, modal.y + 195)
            shop_med.rect.topleft = (modal.x + 430, modal.y + 275)
            shop_rep.rect.topleft = (modal.x + 430, modal.y + 355)
            shop_food.draw(screen); shop_ammo.draw(screen); shop_med.draw(screen); shop_rep.draw(screen)

            projected = shop_food.value_int()*prices["food10"] + shop_ammo.value_int()*prices["ammo1"] + shop_med.value_int()*prices["med1"] + shop_rep.value_int()*prices["repair"]
            draw_text(screen, f"Projected cost: ${projected}", modal.x + 25, modal.y + 235, BLACK, FONT_B)
            draw_text(screen, f"Your cash: ${game.cash}", modal.x + 25, modal.y + 265, BLACK, FONT)

            shop_buy.rect.topleft = (modal.x + 430, modal.y + 415)
            shop_leave.rect.topleft = (modal.x + 610, modal.y + 415)
            shop_buy.draw(screen); shop_leave.draw(screen)

        if game.mode == "HUNT":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0, 0, 0, 90))
            screen.blit(overlay, (0, 0))
            game.hunt_game.draw(screen)
            draw_text(screen, f"Ammo remaining: {game.ammo}", 80, 235, BLACK, FONT_B)
            draw_text(screen, "Tip: aim center-mass. Bears take 2 hits.", 80, 265, BLACK, FONT)

        if game.game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))
            msg = "YOU WIN!" if game.win else "GAME OVER"
            box = pygame.Rect(330, 260, 440, 150)
            pygame.draw.rect(screen, WHITE, box, border_radius=18)
            pygame.draw.rect(screen, DARK, box, 2, border_radius=18)
            draw_text(screen, msg, box.x + 150, box.y + 25, BLACK, FONT_H)
            draw_text(screen, "Tip: Load (L) or Reset to play again.", box.x + 55, box.y + 85, BLACK, FONT)

        pygame.display.flip()

if __name__ == "__main__":
    main()
