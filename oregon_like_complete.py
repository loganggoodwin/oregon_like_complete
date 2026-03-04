import json
import os
import random
import sys
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

import pygame

# -----------------------------
# Oregon Trail-ish (More Complete) - Single File
# Features added per request:
# - Named party members + individual health
# - River crossings with choices
# - Towns/landmarks every X miles
# - Quantity-based shop (simple numeric inputs)
# - Save/Load (JSON)
# -----------------------------

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
pygame.display.set_caption("Trail Game (Oregon-ish) - Complete Starter")
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()

FONT = pygame.font.SysFont("consolas", 18)
FONT_B = pygame.font.SysFont("consolas", 22, bold=True)
FONT_H = pygame.font.SysFont("consolas", 28, bold=True)

SAVE_PATH = "trail_save.json"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def draw_text(surface, text, x, y, color=BLACK, font=FONT):
    surface.blit(font.render(text, True, color), (x, y))


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
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


class InputBox:
    """
    Minimal numeric input box:
    - Click to focus
    - Type digits
    - Backspace removes
    """

    def __init__(self, rect, text="0", label=""):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.label = label
        self.active = False

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
            else:
                # Only digits
                if event.unicode.isdigit():
                    # Avoid ridiculous lengths
                    if len(self.text) < 6:
                        # Replace leading zero nicely
                        if self.text == "0":
                            self.text = event.unicode
                        else:
                            self.text += event.unicode
            if self.text == "":
                self.text = "0"

    def draw(self, surface):
        # Label
        if self.label:
            draw_text(surface, self.label, self.rect.x, self.rect.y - 22, BLACK, FONT)
        # Box
        bg = (255, 255, 255) if self.active else (245, 245, 245)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, BLUE if self.active else DARK, self.rect, 2, border_radius=8)
        draw_text(surface, self.text, self.rect.x + 10, self.rect.y + 8, BLACK, FONT_B)


@dataclass
class PartyMember:
    name: str
    health: int = 100  # 0-100
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
    kind: str  # "town" | "landmark" | "river"
    # optional hint/metadata
    difficulty: int = 1  # for rivers (1-3)


class Game:
    def __init__(self):
        self.reset()

    def reset(self):
        # Core state
        self.day = 1
        self.season = "Spring"
        self.miles_traveled = 0
        self.weather = "Clear"

        # Party (named + individual health)
        default_names = ["Garth", "Christine", "Kate", "Xavier", "Samuel"]
        self.party: List[PartyMember] = [PartyMember(n) for n in default_names]

        # Global morale and wagon
        self.morale = 80
        self.wagon_condition = 100

        # Resources
        self.food = 500
        self.ammo = 40
        self.medicine = 6
        self.cash = 300

        # Gameplay knobs
        self.pace = "Steady"     # Leisurely / Steady / Grueling
        self.rations = "Normal"  # Meager / Normal / Filling

        # Journey structure: landmarks / towns / rivers
        self.landmarks: List[Landmark] = self.build_landmarks()
        self.next_landmark_index = 0

        # Log
        self.log = ["Welcome to the trail. Reach 2,000 miles to win.", "Tip: Press S to save, L to load."]
        self.game_over = False
        self.win = False

        # Modal state
        self.mode = "MAIN"  # MAIN / SHOP / LANDMARK / RIVER / MESSAGE
        self.modal_title = ""
        self.modal_body: List[str] = []
        self.modal_actions: List[Tuple[str, str]] = []  # (button text, action key)

        # For river crossing
        self.pending_river: Optional[Landmark] = None

    def build_landmarks(self) -> List[Landmark]:
        # A simple, spaced journey:
        # - Towns provide shop access
        # - Rivers force a crossing choice
        # - Landmarks are flavor / small bonuses/risks
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
        # Ensure sorted
        landmarks.sort(key=lambda l: l.miles)
        return landmarks

    # ---------------- UI helpers ----------------
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
        # Rough 30-day seasons
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

    # ---------------- economy ----------------
    def price_multiplier(self):
        base = 1.0 + (self.day / 120.0) * 0.6
        if self.season == "Winter":
            base *= 1.15
        return base

    def shop_prices(self) -> Dict[str, int]:
        mult = self.price_multiplier()
        # food priced per 10 units
        return {
            "food10": max(1, int(1 * mult)),
            "ammo1": max(1, int(2 * mult)),
            "med1": max(5, int(18 * mult)),
            "repair": max(10, int(20 * mult)),
        }

    def buy_shop(self, food10: int, ammo1: int, med1: int, repair: int) -> Tuple[bool, str]:
        if self.game_over:
            return False, "Game over."
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
            self.wagon_condition = clamp(self.wagon_condition + (repair * 18), 0, 100)
        return True, f"Spent ${cost}. +{food10*10} food, +{ammo1} ammo, +{med1} med, +{repair*18}% wagon."

    # ---------------- daily mechanics ----------------
    def ration_factor(self):
        return {"Meager": 0.7, "Normal": 1.0, "Filling": 1.25}[self.rations]

    def pace_factor(self):
        return {"Leisurely": 0.8, "Steady": 1.0, "Grueling": 1.25}[self.pace]

    def daily_food_consumption(self):
        # based on alive members
        base = 8 * max(1, self.party_count_alive())
        return int(base * self.ration_factor())

    def consume_food(self):
        need = self.daily_food_consumption()
        if self.food >= need:
            self.food -= need
        else:
            self.food = 0
            # Starvation hits everyone alive
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
        self.wagon_condition -= int(wear)
        self.wagon_condition = clamp(self.wagon_condition, 0, 100)

    def apply_daily_health(self):
        # Global conditions affect each member
        for m in self.alive_members():
            delta = 0

            # rations influence
            if self.rations == "Meager":
                delta -= 2
            elif self.rations == "Filling":
                delta += 1

            # morale influence
            if self.morale < 30:
                delta -= 1
            elif self.morale > 70:
                delta += 1

            # weather influence
            if self.weather == "Snow":
                delta -= 3
            elif self.weather == "Cold":
                delta -= 2
            elif self.weather == "Storm":
                delta -= 2
            elif self.weather == "Hot":
                delta -= 1

            # wagon condition influence
            if self.wagon_condition < 25:
                delta -= 2

            # status effects
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

        # random events
        self.roll_event(context=context)

        self.check_end_conditions()

    # ---------------- random events ----------------
    def roll_event(self, context="travel"):
        if self.game_over:
            return

        chance = 0.22 if context == "travel" else 0.10
        if self.season == "Winter":
            chance += 0.07
        if self.pace == "Grueling":
            chance += 0.05

        if random.random() > chance:
            return

        events = [
            ("illness", 22),
            ("wagon_damage", 18),
            ("bandits", 12),
            ("find_food", 12),
            ("bad_weather", 10),
            ("lose_way", 10),
            ("help_traveler", 8),
        ]
        event = weighted_choice(events)

        if event == "illness":
            alive = self.alive_members()
            if not alive:
                return
            victim = random.choice(alive)
            severity = random.choice([1, 2, 3])
            victim.status = "Sick"
            victim.apply_health(-(6 * severity))
            self.add_log(f"Event: {victim.name} fell ill (-{6*severity} health).")

            # auto use medicine sometimes
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
                # injuries
                alive = self.alive_members()
                if alive:
                    victim = random.choice(alive)
                    victim.status = "Injured"
                    victim.apply_health(-12)
                    self.add_log(f"Event: Bandits! {victim.name} was injured (-12 health, -${loss_cash}).")
                else:
                    self.add_log(f"Event: Bandits! You lost ${loss_cash}.")
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

    # ---------------- actions ----------------
    def toggle_pace(self):
        if self.pace == "Leisurely":
            self.pace = "Steady"
        elif self.pace == "Steady":
            self.pace = "Grueling"
        else:
            self.pace = "Leisurely"
        self.add_log(f"Pace set to: {self.pace}")

    def toggle_rations(self):
        if self.rations == "Meager":
            self.rations = "Normal"
        elif self.rations == "Normal":
            self.rations = "Filling"
        else:
            self.rations = "Meager"
        self.add_log(f"Rations set to: {self.rations}")

    def rest(self):
        if self.game_over:
            return
        # Rest helps alive members a bit
        for m in self.alive_members():
            m.apply_health(+6)
            if m.status in ("Sick", "Injured") and m.health >= 70 and random.random() < 0.5:
                m.status = "OK"
        self.morale = clamp(self.morale + 4, 0, 100)
        self.add_log("Rest: party recovers.")
        self.advance_day(context="rest")

    def hunt(self):
        if self.game_over:
            return
        if self.ammo <= 0:
            self.add_log("Hunt: No ammo.")
            self.morale = clamp(self.morale - 2, 0, 100)
            self.advance_day(context="rest")
            return

        spent = min(random.randint(6, 14), self.ammo)
        self.ammo -= spent

        gain = int(spent * random.uniform(4.0, 7.5))
        if self.weather in ("Storm", "Snow"):
            gain = int(gain * 0.75)

        self.food += gain
        self.morale = clamp(self.morale + 3, 0, 100)
        self.add_log(f"Hunt: -{spent} ammo, +{gain} food.")
        self.advance_day(context="travel")

    def travel(self):
        if self.game_over:
            return

        base = 18 * self.pace_factor()
        if self.weather == "Clear":
            mod = 1.0
        elif self.weather in ("Wind", "Cold", "Hot", "Rain"):
            mod = 0.85
        else:
            mod = 0.65

        wagon_mod = 0.6 + (self.wagon_condition / 100.0) * 0.6  # 0.6 to 1.2
        party_mod = 0.75 + (self.party_count_alive() / max(1, len(self.party))) * 0.35  # fewer alive => slower

        miles = int(base * mod * wagon_mod * party_mod)
        miles = max(1, miles)

        prev = self.miles_traveled
        self.miles_traveled += miles

        self.add_log(f"Travel: +{miles} miles (Weather: {self.weather}, Pace: {self.pace}).")
        self.advance_day(context="travel")

        # Check if we crossed a landmark
        self.check_landmark_reached(prev, self.miles_traveled)

    # ---------------- landmarks & rivers ----------------
    def check_landmark_reached(self, prev_miles: int, new_miles: int):
        # Trigger sequentially
        while self.next_landmark_index < len(self.landmarks):
            lm = self.landmarks[self.next_landmark_index]
            if prev_miles < lm.miles <= new_miles:
                self.next_landmark_index += 1
                self.trigger_landmark(lm)
                # Stop after one modal trigger to avoid stacking in a single frame
                break
            else:
                break

    def trigger_landmark(self, lm: Landmark):
        if lm.kind == "town":
            self.mode = "LANDMARK"
            self.modal_title = f"Town: {lm.name}"
            self.modal_body = [
                f"You arrive at {lm.name} (mile {lm.miles}).",
                "You can shop here, rest, or move on.",
            ]
            self.modal_actions = [
                ("Shop", "OPEN_SHOP"),
                ("Rest (1 day)", "REST"),
                ("Continue", "CLOSE_MODAL"),
            ]
            self.add_log(f"Arrived at {lm.name}.")

        elif lm.kind == "river":
            self.mode = "RIVER"
            self.pending_river = lm
            self.modal_title = f"River: {lm.name}"
            self.modal_body = [
                f"You reached {lm.name} (mile {lm.miles}).",
                f"Crossing difficulty: {lm.difficulty}/3",
                "Choose how to cross:",
                "- Ford: risky, no cash",
                "- Caulk: uses wagon condition, medium risk",
                "- Ferry: costs cash, safer",
            ]
            self.modal_actions = [
                ("Ford", "RIVER_FORD"),
                ("Caulk", "RIVER_CAULK"),
                ("Ferry", "RIVER_FERRY"),
                ("Wait (1 day)", "RIVER_WAIT"),
            ]
            self.add_log(f"Reached river: {lm.name}.")

        else:
            # landmark flavor: small random outcome
            self.mode = "LANDMARK"
            self.modal_title = f"Landmark: {lm.name}"
            outcome = random.random()
            if outcome < 0.40:
                bonus = random.randint(10, 35)
                self.food += bonus
                self.modal_body = [
                    f"You pass {lm.name} (mile {lm.miles}).",
                    f"You find a stash of supplies (+{bonus} food).",
                ]
            elif outcome < 0.70:
                self.morale = clamp(self.morale + 6, 0, 100)
                self.modal_body = [
                    f"You pass {lm.name} (mile {lm.miles}).",
                    "The view lifts everyone's spirits (+6 morale).",
                ]
            else:
                dmg = random.randint(5, 15)
                self.wagon_condition = clamp(self.wagon_condition - dmg, 0, 100)
                self.modal_body = [
                    f"You pass {lm.name} (mile {lm.miles}).",
                    f"Rough terrain strains the wagon (-{dmg}% condition).",
                ]
            self.modal_actions = [("Continue", "CLOSE_MODAL")]
            self.add_log(f"Passed {lm.name}.")

    def resolve_river_crossing(self, method: str):
        lm = self.pending_river
        if not lm:
            self.mode = "MAIN"
            return

        # Baseline chances by method; increase with difficulty and conditions
        difficulty = lm.difficulty
        avg_h = self.average_health()
        wagon = self.wagon_condition

        # Risk factors
        winter_penalty = 0.08 if self.season == "Winter" else 0.0
        low_health_penalty = 0.06 if avg_h < 60 else 0.0
        bad_weather_penalty = 0.08 if self.weather in ("Storm", "Snow") else 0.0

        # Define method parameters
        if method == "FORD":
            cost_cash = 0
            cost_wagon = 0
            base_fail = 0.20 + 0.10 * (difficulty - 1)
            base_injury = 0.18 + 0.08 * (difficulty - 1)
            day_cost = 1
        elif method == "CAULK":
            cost_cash = 0
            cost_wagon = 10 + 7 * difficulty
            base_fail = 0.12 + 0.06 * (difficulty - 1)
            base_injury = 0.12 + 0.06 * (difficulty - 1)
            day_cost = 1
        else:  # FERRY
            cost_cash = 25 + 20 * difficulty
            cost_wagon = 0
            base_fail = 0.06 + 0.03 * (difficulty - 1)
            base_injury = 0.06 + 0.03 * (difficulty - 1)
            day_cost = 1

        # Check affordability for ferry
        if method == "FERRY" and self.cash < cost_cash:
            self.modal_body = [
                f"You don't have enough cash for the ferry (${cost_cash} needed).",
                "Choose another method or wait.",
            ]
            return

        # Apply method costs
        if cost_cash > 0:
            self.cash -= cost_cash
        if cost_wagon > 0:
            self.wagon_condition = clamp(self.wagon_condition - cost_wagon, 0, 100)

        # Compute final probabilities
        fail_p = base_fail + winter_penalty + low_health_penalty + bad_weather_penalty
        injury_p = base_injury + winter_penalty + low_health_penalty + bad_weather_penalty

        # Wagon in bad shape increases failure
        if wagon < 30:
            fail_p += 0.06

        fail_p = clamp(fail_p, 0.02, 0.75)
        injury_p = clamp(injury_p, 0.02, 0.75)

        # Resolve outcome
        lines = [f"You attempt to cross by {method.title()}..."]
        roll = random.random()

        # Spend a day
        for _ in range(day_cost):
            self.advance_day(context="rest")

        if roll < fail_p:
            # Failure: lose supplies and possibly someone gets hurt
            food_lost = min(random.randint(20, 90), self.food)
            ammo_lost = min(random.randint(0, 12), self.ammo)
            cash_lost = min(random.randint(0, 40), self.cash)
            self.food -= food_lost
            self.ammo -= ammo_lost
            self.cash -= cash_lost
            self.morale = clamp(self.morale - 8, 0, 100)
            lines.append(f"Disaster! You lose supplies (-{food_lost} food, -{ammo_lost} ammo, -${cash_lost}).")

            # Injury chance on failure
            if self.alive_members() and random.random() < 0.65:
                victim = random.choice(self.alive_members())
                victim.status = "Injured"
                victim.apply_health(-random.randint(10, 22))
                lines.append(f"{victim.name} is injured during the crossing.")
        else:
            lines.append("Success! You cross safely.")
            # Minor morale bump if ferry or caulk
            if method in ("FERRY", "CAULK"):
                self.morale = clamp(self.morale + 3, 0, 100)

            # Injury can still occur even on success
            if self.alive_members() and random.random() < injury_p * 0.35:
                victim = random.choice(self.alive_members())
                victim.status = "Injured"
                victim.apply_health(-random.randint(6, 14))
                lines.append(f"{victim.name} takes a hard hit crossing (injured).")

        self.pending_river = None
        self.mode = "LANDMARK"
        self.modal_title = "River Crossing Result"
        self.modal_body = lines
        self.modal_actions = [("Continue", "CLOSE_MODAL")]

    # ---------------- save/load ----------------
    def to_dict(self) -> Dict:
        return {
            "day": self.day,
            "season": self.season,
            "miles_traveled": self.miles_traveled,
            "weather": self.weather,
            "party": [asdict(m) for m in self.party],
            "morale": self.morale,
            "wagon_condition": self.wagon_condition,
            "food": self.food,
            "ammo": self.ammo,
            "medicine": self.medicine,
            "cash": self.cash,
            "pace": self.pace,
            "rations": self.rations,
            "next_landmark_index": self.next_landmark_index,
            "game_over": self.game_over,
            "win": self.win,
            "log": self.log,
        }

    def from_dict(self, d: Dict):
        self.day = int(d.get("day", 1))
        self.set_season()
        self.season = d.get("season", self.season)
        self.miles_traveled = int(d.get("miles_traveled", 0))
        self.weather = d.get("weather", "Clear")
        self.party = [PartyMember(**m) for m in d.get("party", [])] or self.party
        self.morale = int(d.get("morale", 80))
        self.wagon_condition = int(d.get("wagon_condition", 100))
        self.food = int(d.get("food", 500))
        self.ammo = int(d.get("ammo", 40))
        self.medicine = int(d.get("medicine", 6))
        self.cash = int(d.get("cash", 300))
        self.pace = d.get("pace", "Steady")
        self.rations = d.get("rations", "Normal")
        self.landmarks = self.build_landmarks()
        self.next_landmark_index = int(d.get("next_landmark_index", 0))
        self.game_over = bool(d.get("game_over", False))
        self.win = bool(d.get("win", False))
        self.log = d.get("log", self.log)[-12:]

        # Reset modal state
        self.mode = "MAIN"
        self.modal_title = ""
        self.modal_body = []
        self.modal_actions = []
        self.pending_river = None

    def save(self) -> Tuple[bool, str]:
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            return True, f"Saved to {SAVE_PATH}"
        except Exception as e:
            return False, f"Save failed: {e}"

    def load(self) -> Tuple[bool, str]:
        if not os.path.exists(SAVE_PATH):
            return False, f"No save found at {SAVE_PATH}"
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.from_dict(d)
            return True, f"Loaded from {SAVE_PATH}"
        except Exception as e:
            return False, f"Load failed: {e}"

    # ---------------- end conditions ----------------
    def check_end_conditions(self):
        if self.miles_traveled >= MILES_TO_GOAL:
            self.win = True
            self.game_over = True
            self.add_log("You reached your destination. You win!")
            return

        if self.party_count_alive() <= 0:
            self.game_over = True
            self.win = False
            self.add_log("Everyone is gone. Game over.")
            return

        if self.wagon_condition <= 0:
            self.game_over = True
            self.win = False
            self.add_log("Your wagon broke beyond repair. Game over.")
            return

        if self.day > 160:
            self.game_over = True
            self.win = False
            self.add_log("Too many days passed. Winter wins. Game over.")
            return


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

    # MAIN buttons
    btn_travel = Button((40, 585, 170, 55), "Travel", bg=BLUE, fg=WHITE)
    btn_rest = Button((220, 585, 170, 55), "Rest", bg=GREEN, fg=WHITE)
    btn_hunt = Button((400, 585, 170, 55), "Hunt", bg=YELLOW, fg=BLACK)
    btn_shop = Button((580, 585, 170, 55), "Shop", bg=GRAY, fg=BLACK)

    btn_pace = Button((40, 645, 170, 45), "Toggle Pace", bg=GRAY, fg=BLACK)
    btn_ration = Button((220, 645, 170, 45), "Toggle Rations", bg=GRAY, fg=BLACK)
    btn_save = Button((820, 585, 120, 55), "Save", bg=ORANGE, fg=BLACK)
    btn_load = Button((950, 585, 120, 55), "Load", bg=ORANGE, fg=BLACK)
    btn_reset = Button((820, 645, 250, 45), "Reset", bg=RED, fg=WHITE)

    # SHOP modal elements
    shop_buy = Button((690, 520, 170, 50), "Buy", bg=GREEN, fg=WHITE)
    shop_leave = Button((880, 520, 170, 50), "Leave", bg=GRAY, fg=BLACK)
    shop_food_box = InputBox((720, 210, 160, 40), "0", "Food (x10 units)")
    shop_ammo_box = InputBox((720, 290, 160, 40), "0", "Ammo (x1)")
    shop_med_box = InputBox((720, 370, 160, 40), "0", "Medicine (x1)")
    shop_rep_box = InputBox((720, 450, 160, 40), "0", "Repair kits (x1)")

    # Modal action buttons (dynamic)
    modal_buttons: List[Tuple[Button, str]] = []

    def open_shop():
        game.mode = "SHOP"
        # Clear inputs
        shop_food_box.text = "0"
        shop_ammo_box.text = "0"
        shop_med_box.text = "0"
        shop_rep_box.text = "0"
        for b in (shop_food_box, shop_ammo_box, shop_med_box, shop_rep_box):
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
        x0, y0 = 360, 520
        w, h = 170, 50
        gap = 18
        for i, (txt, key) in enumerate(game.modal_actions):
            btn = Button((x0 + i * (w + gap), y0, w, h), txt, bg=GRAY, fg=BLACK)
            modal_buttons.append((btn, key))

    def handle_modal_action(key: str):
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
            # waiting costs a day; might improve weather a bit
            game.add_log("You wait by the river for conditions to improve.")
            game.advance_day(context="rest")
            if random.random() < 0.35:
                game.weather = "Clear"
            # Keep river modal open
            if game.pending_river:
                game.modal_body = [
                    f"You wait at {game.pending_river.name}.",
                    f"Weather now: {game.weather}",
                    "Choose how to cross:",
                    "- Ford: risky, no cash",
                    "- Caulk: uses wagon condition, medium risk",
                    "- Ferry: costs cash, safer",
                ]
        else:
            close_modal()

    while True:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # Keyboard shortcuts for save/load
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_s:
                    ok, msg = game.save()
                    game.add_log(msg if ok else f"ERROR: {msg}")
                if event.key == pygame.K_l:
                    ok, msg = game.load()
                    game.add_log(msg if ok else f"ERROR: {msg}")

            # SHOP input boxes handle events
            if game.mode == "SHOP":
                for box in (shop_food_box, shop_ammo_box, shop_med_box, shop_rep_box):
                    box.handle_event(event)

            # MAIN mode buttons
            if game.mode == "MAIN":
                if btn_travel.clicked(event):
                    game.travel()
                if btn_rest.clicked(event):
                    game.rest()
                if btn_hunt.clicked(event):
                    game.hunt()
                if btn_shop.clicked(event):
                    open_shop()

                if btn_pace.clicked(event):
                    game.toggle_pace()
                if btn_ration.clicked(event):
                    game.toggle_rations()

                if btn_save.clicked(event):
                    ok, msg = game.save()
                    game.add_log(msg if ok else f"ERROR: {msg}")
                if btn_load.clicked(event):
                    ok, msg = game.load()
                    game.add_log(msg if ok else f"ERROR: {msg}")

                if btn_reset.clicked(event):
                    game.reset()

            # SHOP buttons
            if game.mode == "SHOP":
                if shop_buy.clicked(event):
                    ok, msg = game.buy_shop(
                        food10=shop_food_box.value_int(),
                        ammo1=shop_ammo_box.value_int(),
                        med1=shop_med_box.value_int(),
                        repair=shop_rep_box.value_int(),
                    )
                    game.add_log(f"Shop: {msg}")
                if shop_leave.clicked(event):
                    close_modal()

            # Landmark / River modal buttons
            if game.mode in ("LANDMARK", "RIVER"):
                # ensure buttons exist
                build_modal_buttons()
                for btn, key in modal_buttons:
                    if btn.clicked(event):
                        handle_modal_action(key)

            # Reset button also works in modals
            if btn_reset.clicked(event):
                game.reset()

        # ------------- Draw -------------
        screen.fill(WHITE)

        # Header
        draw_text(screen, "Trail Game (Oregon-ish) - Complete Starter", 40, 18, BLACK, FONT_H)
        draw_text(
            screen,
            f"Day {game.day} | Season: {game.season} | Weather: {game.weather} | Pace: {game.pace} | Rations: {game.rations}",
            40,
            56,
            BLACK,
            FONT,
        )

        # Progress bar (miles)
        pygame.draw.rect(screen, GRAY, (40, 90, 1020, 28), border_radius=10)
        pct = clamp(int((game.miles_traveled / MILES_TO_GOAL) * 100), 0, 100)
        pygame.draw.rect(screen, BLUE, (40, 90, int(1020 * (pct / 100.0)), 28), border_radius=10)
        pygame.draw.rect(screen, DARK, (40, 90, 1020, 28), 2, border_radius=10)
        draw_text(screen, f"Miles: {game.miles_traveled}/{MILES_TO_GOAL} ({pct}%)", 50, 95)

        # Left panel: Party & wagon
        party_rect = pygame.Rect(40, 140, 660, 430)
        draw_panel(party_rect, "Party Status")

        avg_health = game.average_health()
        draw_bar(60, 185, 620, 30, avg_health, "Avg Health", GREEN if avg_health >= 50 else RED)
        draw_bar(60, 225, 620, 30, game.morale, "Morale", GREEN if game.morale >= 50 else RED)
        draw_bar(60, 265, 620, 30, game.wagon_condition, "Wagon", GREEN if game.wagon_condition >= 50 else RED)

        # Party members list
        draw_text(screen, "Members:", 60, 312, BLACK, FONT_B)
        y = 345
        for m in game.party:
            status_color = BLACK
            if m.status == "Dead":
                status_color = RED
            elif m.status in ("Sick", "Injured"):
                status_color = ORANGE
            draw_text(screen, f"- {m.name:10}  Health: {m.health:3}  Status: {m.status}", 60, y, status_color, FONT)
            y += 26

        # Inventory line
        draw_text(screen, "Inventory:", 60, 500, BLACK, FONT_B)
        draw_text(screen, f"Food: {game.food}", 60, 530)
        draw_text(screen, f"Ammo: {game.ammo}", 220, 530)
        draw_text(screen, f"Medicine: {game.medicine}", 360, 530)
        draw_text(screen, f"Cash: ${game.cash}", 560, 530)

        # Right panel: log + upcoming landmark
        log_rect = pygame.Rect(720, 140, 340, 430)
        draw_panel(log_rect, "Trail Log")

        # Upcoming landmark
        if game.next_landmark_index < len(game.landmarks):
            next_lm = game.landmarks[game.next_landmark_index]
            dist = max(0, next_lm.miles - game.miles_traveled)
            draw_text(screen, f"Next: {next_lm.name} ({next_lm.kind})", 740, 180, BLACK, FONT)
            draw_text(screen, f"In: {dist} miles", 740, 205, BLACK, FONT)
        else:
            draw_text(screen, "Next: Final stretch", 740, 180, BLACK, FONT)

        # Log lines
        y = 240
        for line in game.log:
            draw_text(screen, f"- {line}", 740, y, BLACK, FONT)
            y += 24

        # Bottom buttons
        btn_travel.draw(screen)
        btn_rest.draw(screen)
        btn_hunt.draw(screen)
        btn_shop.draw(screen)

        btn_pace.draw(screen)
        btn_ration.draw(screen)
        btn_save.draw(screen)
        btn_load.draw(screen)
        btn_reset.draw(screen)

        # --------- Modal overlays ----------
        if game.mode in ("LANDMARK", "RIVER"):
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))

            modal = pygame.Rect(160, 160, 780, 420)
            pygame.draw.rect(screen, WHITE, modal, border_radius=18)
            pygame.draw.rect(screen, DARK, modal, 2, border_radius=18)

            draw_text(screen, game.modal_title, modal.x + 25, modal.y + 20, BLACK, FONT_H)
            yy = modal.y + 75
            for line in game.modal_body:
                draw_text(screen, line, modal.x + 25, yy, BLACK, FONT)
                yy += 28

            build_modal_buttons()
            for btn, _ in modal_buttons:
                btn.draw(screen)

        if game.mode == "SHOP":
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))

            modal = pygame.Rect(140, 140, 820, 470)
            pygame.draw.rect(screen, WHITE, modal, border_radius=18)
            pygame.draw.rect(screen, DARK, modal, 2, border_radius=18)

            draw_text(screen, "Shop", modal.x + 25, modal.y + 20, BLACK, FONT_H)

            prices = game.shop_prices()
            draw_text(screen, "Prices:", modal.x + 25, modal.y + 70, BLACK, FONT_B)
            draw_text(screen, f"10 food = ${prices['food10']}", modal.x + 25, modal.y + 100)
            draw_text(screen, f"1 ammo  = ${prices['ammo1']}", modal.x + 25, modal.y + 125)
            draw_text(screen, f"1 med   = ${prices['med1']}", modal.x + 25, modal.y + 150)
            draw_text(screen, f"repair kit = ${prices['repair']} (adds +18% wagon)", modal.x + 25, modal.y + 175)

            draw_text(screen, "Enter quantities:", modal.x + 400, modal.y + 70, BLACK, FONT_B)

            # Input boxes (positioned relative)
            shop_food_box.rect.topleft = (modal.x + 430, modal.y + 95)
            shop_ammo_box.rect.topleft = (modal.x + 430, modal.y + 175)
            shop_med_box.rect.topleft = (modal.x + 430, modal.y + 255)
            shop_rep_box.rect.topleft = (modal.x + 430, modal.y + 335)

            shop_food_box.draw(screen)
            shop_ammo_box.draw(screen)
            shop_med_box.draw(screen)
            shop_rep_box.draw(screen)

            # Show projected cost
            projected_cost = (
                shop_food_box.value_int() * prices["food10"]
                + shop_ammo_box.value_int() * prices["ammo1"]
                + shop_med_box.value_int() * prices["med1"]
                + shop_rep_box.value_int() * prices["repair"]
            )
            draw_text(screen, f"Projected cost: ${projected_cost}", modal.x + 25, modal.y + 235, BLACK, FONT_B)
            draw_text(screen, f"Your cash: ${game.cash}", modal.x + 25, modal.y + 265, BLACK, FONT)

            # Shop buttons
            shop_buy.rect.topleft = (modal.x + 430, modal.y + 395)
            shop_leave.rect.topleft = (modal.x + 610, modal.y + 395)
            shop_buy.draw(screen)
            shop_leave.draw(screen)

        # Game over overlay (still allows reset/load)
        if game.game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
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
