# ============================================================
# NR-17 | ERGONOMIA POR VISÃO - ANDROID LOCAL MVP
# Kivy + câmera local + ML Kit Pose Android + IRE/RULA/REBA
# ============================================================

import os
import json
import math
import time
import threading
from pathlib import Path
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, Ellipse, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.camera import Camera
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scatter import Scatter
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

# Pillow já faz parte da estrutura de build usada no APK existente.
from PIL import Image, ImageDraw, ImageFont

APP_TITLE = "NR-17 | Ergonomia por Visão"

# ------------------------------------------------------------------
# VISUAL
# ------------------------------------------------------------------
BG = (0.025, 0.060, 0.100, 1)
PANEL = (0.045, 0.110, 0.180, 1)
PANEL_2 = (0.060, 0.145, 0.235, 1)
LINE_C = (0.18, 0.50, 0.72, 0.35)
TEXT = (0.94, 0.98, 1, 1)
MUTED = (0.58, 0.70, 0.80, 1)
CYAN = (0.26, 0.86, 1.0, 1)
GREEN = (0.22, 0.86, 0.52, 1)
YELLOW = (0.96, 0.76, 0.20, 1)
ORANGE = (1.00, 0.48, 0.16, 1)
RED = (1.00, 0.28, 0.32, 1)

Window.clearcolor = BG


# ------------------------------------------------------------------
# CONFIG LOCAL
# ------------------------------------------------------------------
def load_env(path):
    path = Path(path)
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
    except Exception:
        pass


BASE_DIR = Path(__file__).resolve().parent
load_env(BASE_DIR / "teste.env")


def env_int(name, default):
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return int(default)


def env_float(name, default):
    try:
        return float(os.getenv(name, str(default)).strip())
    except Exception:
        return float(default)


CAMERA_INDEX = env_int("CAMERA_TRASEIRA_INDEX", 0)
CAMERA_PREVIEW_ROTATION = env_int("CAMERA_PREVIEW_ROTATION", 270) % 360
POSE_ROTATION = env_int("POSE_ROTATION", CAMERA_PREVIEW_ROTATION) % 360
CAM_W = env_int("CAMERA_WIDTH", 1280)
CAM_H = env_int("CAMERA_HEIGHT", 720)
POSE_LONG_SIDE = env_int("POSE_INPUT_LONG_SIDE", 640)
POSE_INTERVAL = max(0.08, env_float("POSE_INTERVAL", 0.12))
MIN_CONFIDENCE = max(0.25, min(0.95, env_float("POSE_MIN_CONFIDENCE", 0.45)))

TRUNK_LIMIT = env_float("IRE_TRONCO", 25.0)
NECK_LIMIT = env_float("IRE_PESCOCO", 25.0)
ARM_LIMIT = env_float("IRE_BRACO", 60.0)
KNEE_LIMIT = env_float("IRE_JOELHO", 130.0)


# ------------------------------------------------------------------
# HELPERS DE GEOMETRIA
# ------------------------------------------------------------------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def angle3(a, b, c):
    if not a or not b or not c:
        return None
    bax = a[0] - b[0]
    bay = a[1] - b[1]
    bcx = c[0] - b[0]
    bcy = c[1] - b[1]
    n1 = math.hypot(bax, bay)
    n2 = math.hypot(bcx, bcy)
    if n1 < 1e-9 or n2 < 1e-9:
        return None
    val = clamp((bax * bcx + bay * bcy) / (n1 * n2), -1.0, 1.0)
    return math.degrees(math.acos(val))


def vector_angle(v1, v2):
    if not v1 or not v2:
        return None
    n1 = math.hypot(v1[0], v1[1])
    n2 = math.hypot(v2[0], v2[1])
    if n1 < 1e-9 or n2 < 1e-9:
        return None
    val = clamp((v1[0]*v2[0] + v1[1]*v2[1]) / (n1*n2), -1.0, 1.0)
    return math.degrees(math.acos(val))


def midpoint(a, b):
    if not a or not b:
        return None
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def fmt_angle(v):
    return "--" if v is None else f"{v:.1f}°"


def fmt_seconds(seconds):
    seconds = max(0, int(seconds or 0))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ------------------------------------------------------------------
# RULA / REBA - mesma lógica de triagem do MVP
# Fatores que a visão 2D não determina ficam neutros neste primeiro APK.
# ------------------------------------------------------------------
RULA_TABLE_A = [
    [1,2,2,2,2,3,3,3],[2,2,2,2,3,3,3,3],[2,3,3,3,3,3,4,4],
    [2,3,3,3,3,4,4,4],[2,3,3,3,3,3,4,4],[3,4,4,4,4,4,5,5],
    [3,3,4,4,4,4,5,5],[3,4,4,4,4,4,5,5],[4,4,4,4,4,5,5,5],
    [4,4,4,4,4,5,5,5],[4,4,4,4,4,5,5,5],[4,4,4,5,5,5,6,6],
    [5,5,5,5,5,6,6,7],[5,6,6,6,6,6,7,7],[6,6,6,7,7,7,7,8],
    [7,7,7,7,7,8,8,9],[8,8,8,8,8,9,9,9],[9,9,9,9,9,9,9,9],
]
RULA_TABLE_B = [
    [1,3,2,3,3,4,5,5,6,6,7,7],
    [2,3,2,3,4,5,5,5,6,7,7,7],
    [3,3,3,4,4,5,5,6,6,7,7,7],
    [5,5,5,6,6,7,7,7,7,7,8,8],
    [7,7,7,7,7,8,8,8,8,8,8,8],
    [8,8,8,8,8,8,8,9,9,9,9,9],
]
RULA_TABLE_C = [
    [1,2,3,3,4,5,5],[2,2,3,4,4,5,5],[3,3,3,4,4,5,6],[3,3,3,4,5,6,6],
    [4,4,4,5,6,7,7],[4,4,5,6,6,7,7],[5,5,6,6,7,7,7],[5,5,6,7,7,7,7],
]

REBA_TABLE_A = [
    [1,2,3,4,1,2,3,4,3,3,5,6],
    [2,3,4,5,3,4,5,6,4,5,6,7],
    [2,4,5,6,4,5,6,7,5,6,7,8],
    [3,5,6,7,5,6,7,8,6,7,8,9],
    [4,6,7,8,6,7,8,9,7,8,9,9],
]
REBA_TABLE_B = [
    [1,2,2,1,2,3],[1,2,3,2,3,4],[3,4,5,4,5,5],
    [4,5,5,5,6,7],[6,7,8,7,8,8],[7,8,8,8,9,9],
]
REBA_TABLE_C = [
    [1,1,1,2,3,3,4,5,6,7,7,7],[1,2,2,3,4,4,5,6,6,7,7,8],
    [2,3,3,3,4,5,6,7,7,8,8,8],[3,4,4,4,5,6,7,8,8,9,9,9],
    [4,4,4,5,6,7,8,8,9,9,9,9],[6,6,6,7,8,8,9,9,10,10,10,10],
    [7,7,7,8,9,9,9,10,10,11,11,11],[8,8,8,9,10,10,10,10,10,11,11,11],
    [9,9,9,10,10,10,11,11,11,12,12,12],[10,10,10,11,11,11,11,12,12,12,12,12],
    [11,11,11,11,12,12,12,12,12,12,12,12],[12,12,12,12,12,12,12,12,12,12,12,12],
]


def rula_upper_arm_score(angle):
    a = abs(float(angle or 0))
    if a <= 20: return 1
    if a <= 45: return 2
    if a <= 90: return 3
    return 4


def rula_lower_arm_score(elbow):
    if elbow is None:
        return 1
    return 1 if 60 <= elbow <= 100 else 2


def rula_wrist_score(wrist):
    a = abs(float(wrist or 0))
    if a < 1: return 1
    if a <= 15: return 2
    return 3


def rula_neck_score(angle):
    a = abs(float(angle or 0))
    if a <= 10: return 1
    if a <= 20: return 2
    return 3


def rula_trunk_score(angle):
    a = abs(float(angle or 0))
    if a < 1: return 1
    if a <= 20: return 2
    if a <= 60: return 3
    return 4


def calculate_rula(pose, side="right"):
    if side == "left":
        ua_angle, la_angle, wrist = pose.get("shoulder_l"), pose.get("elbow_l"), pose.get("wrist_l")
    else:
        ua_angle, la_angle, wrist = pose.get("shoulder_r"), pose.get("elbow_r"), pose.get("wrist_r")

    ua = clamp(rula_upper_arm_score(ua_angle), 1, 6)
    la = clamp(rula_lower_arm_score(la_angle), 1, 3)
    wr = clamp(rula_wrist_score(wrist), 1, 4)
    wt = 1

    row_a = (ua - 1) * 3 + (la - 1)
    col_a = (wr - 1) * 2 + (wt - 1)
    table_a = RULA_TABLE_A[row_a][col_a]

    ne = clamp(rula_neck_score(pose.get("neck")), 1, 6)
    tr = clamp(rula_trunk_score(pose.get("trunk")), 1, 6)
    legs = 1  # apoiadas, até confirmação manual em versão posterior

    row_b = ne - 1
    col_b = (tr - 1) * 2 + (legs - 1)
    table_b = RULA_TABLE_B[row_b][col_b]

    final_a = clamp(table_a, 1, 8)
    final_b = clamp(table_b, 1, 7)
    return int(RULA_TABLE_C[final_a - 1][final_b - 1])


def reba_trunk_score(angle):
    a = abs(float(angle or 0))
    if a < 1: return 1
    if a <= 20: return 2
    if a <= 60: return 3
    return 4


def reba_neck_score(angle):
    return 2 if abs(float(angle or 0)) > 20 else 1


def reba_leg_score(knee):
    score = 1
    if knee is not None:
        flexion = max(0.0, 180.0 - knee)
        if 30 <= flexion <= 60: score += 1
        elif flexion > 60: score += 2
    return clamp(score, 1, 4)


def reba_upper_arm_score(angle):
    a = abs(float(angle or 0))
    if a <= 20: return 1
    if a <= 45: return 2
    if a <= 90: return 3
    return 4


def reba_lower_arm_score(elbow):
    if elbow is None:
        return 1
    return 1 if 60 <= elbow <= 100 else 2


def reba_wrist_score(wrist):
    return 1 if abs(float(wrist or 0)) <= 15 else 2


def calculate_reba(pose, side="right"):
    knee = pose.get("knee_r") if side == "right" else pose.get("knee_l")
    ua_angle = pose.get("shoulder_r") if side == "right" else pose.get("shoulder_l")
    la_angle = pose.get("elbow_r") if side == "right" else pose.get("elbow_l")
    wrist = pose.get("wrist_r") if side == "right" else pose.get("wrist_l")

    tr = clamp(reba_trunk_score(pose.get("trunk")), 1, 5)
    ne = clamp(reba_neck_score(pose.get("neck")), 1, 3)
    legs = reba_leg_score(knee)

    col_a = (ne - 1) * 4 + (legs - 1)
    score_a = clamp(REBA_TABLE_A[tr - 1][col_a], 1, 12)

    ua = clamp(reba_upper_arm_score(ua_angle), 1, 6)
    la = clamp(reba_lower_arm_score(la_angle), 1, 2)
    wr = clamp(reba_wrist_score(wrist), 1, 3)

    col_b = (la - 1) * 3 + (wr - 1)
    score_b = clamp(REBA_TABLE_B[ua - 1][col_b], 1, 12)

    return int(clamp(REBA_TABLE_C[score_a - 1][score_b - 1], 1, 15))


def calc_ire(v):
    trunk = v.get("trunk") or 0
    neck = v.get("neck") or 0
    arm = max([x for x in [v.get("shoulder_l"), v.get("shoulder_r")] if x is not None] or [0])
    knee = min([x for x in [v.get("knee_l"), v.get("knee_r")] if x is not None] or [180])

    s_trunk = clamp(trunk / max(TRUNK_LIMIT * 2, 1) * 100, 0, 100)
    s_neck = clamp(neck / max(NECK_LIMIT * 2, 1) * 100, 0, 100)
    s_arm = clamp(arm / max(ARM_LIMIT * 1.8, 1) * 100, 0, 100)
    s_knee = 0 if knee >= KNEE_LIMIT else clamp(
        (KNEE_LIMIT - knee) / max(KNEE_LIMIT - 70, 1) * 100, 0, 100
    )
    return int(round(0.35*s_trunk + 0.20*s_neck + 0.25*s_arm + 0.20*s_knee))


def risk_color(ire):
    if ire >= 70: return RED
    if ire >= 50: return ORANGE
    if ire >= 30: return YELLOW
    return GREEN


# ------------------------------------------------------------------
# LANDMARKS / POSE
# ------------------------------------------------------------------
KEY_LANDMARKS = [
    "left_ear","right_ear",
    "left_shoulder","right_shoulder",
    "left_elbow","right_elbow",
    "left_wrist","right_wrist",
    "left_hip","right_hip",
    "left_knee","right_knee",
    "left_ankle","right_ankle",
]

POSE_CONNECTIONS = [
    ("left_ear","left_shoulder"), ("right_ear","right_shoulder"),
    ("left_shoulder","right_shoulder"),
    ("left_shoulder","left_elbow"), ("left_elbow","left_wrist"),
    ("right_shoulder","right_elbow"), ("right_elbow","right_wrist"),
    ("left_shoulder","left_hip"), ("right_shoulder","right_hip"),
    ("left_hip","right_hip"),
    ("left_hip","left_knee"), ("left_knee","left_ankle"),
    ("right_hip","right_knee"), ("right_knee","right_ankle"),
]


def landmark_point(landmarks, name, min_conf=MIN_CONFIDENCE):
    obj = (landmarks or {}).get(name)
    if not obj:
        return None
    try:
        if float(obj.get("c", 0)) < min_conf:
            return None
        return (float(obj["x"]), float(obj["y"]))
    except Exception:
        return None


def derive_pose_values(landmarks):
    p = lambda name: landmark_point(landmarks, name)

    ls, rs = p("left_shoulder"), p("right_shoulder")
    lh, rh = p("left_hip"), p("right_hip")
    le, re = p("left_ear"), p("right_ear")

    sm = midpoint(ls, rs)
    hm = midpoint(lh, rh)
    em = midpoint(le, re)

    trunk = None
    if sm and hm:
        trunk = vector_angle((sm[0]-hm[0], sm[1]-hm[1]), (0.0, -1.0))

    neck = None
    if em and sm and hm:
        neck = vector_angle((em[0]-sm[0], em[1]-sm[1]), (sm[0]-hm[0], sm[1]-hm[1]))

    sh_l = angle3(lh, ls, p("left_elbow"))
    sh_r = angle3(rh, rs, p("right_elbow"))
    el_l = angle3(ls, p("left_elbow"), p("left_wrist"))
    el_r = angle3(rs, p("right_elbow"), p("right_wrist"))

    def wrist_dev(elbow, wrist, index_name, pinky_name):
        idx, pinky = p(index_name), p(pinky_name)
        if not elbow or not wrist or not idx or not pinky:
            return None
        hand = midpoint(idx, pinky)
        internal = angle3(elbow, wrist, hand)
        return None if internal is None else abs(180.0 - internal)

    wr_l = wrist_dev(p("left_elbow"), p("left_wrist"), "left_index", "left_pinky")
    wr_r = wrist_dev(p("right_elbow"), p("right_wrist"), "right_index", "right_pinky")

    kn_l = angle3(lh, p("left_knee"), p("left_ankle"))
    kn_r = angle3(rh, p("right_knee"), p("right_ankle"))

    vals = {
        "trunk": trunk, "neck": neck,
        "shoulder_l": sh_l, "shoulder_r": sh_r,
        "elbow_l": el_l, "elbow_r": el_r,
        "wrist_l": wr_l, "wrist_r": wr_r,
        "knee_l": kn_l, "knee_r": kn_r,
    }
    vals["ire"] = calc_ire(vals)
    vals["rula"] = calculate_rula(vals, side="right")
    vals["reba"] = calculate_reba(vals, side="right")
    return vals


def pose_quality(landmarks):
    vals = []
    for name in KEY_LANDMARKS:
        obj = (landmarks or {}).get(name)
        if obj:
            try:
                vals.append(float(obj.get("c", 0)))
            except Exception:
                pass
    if not vals:
        return 0.0, 0.0
    coverage = 100.0 * sum(1 for v in vals if v >= MIN_CONFIDENCE) / len(KEY_LANDMARKS)
    confidence = 100.0 * sum(vals) / len(vals)
    quality = 0.65 * coverage + 0.35 * confidence
    return clamp(quality, 0, 100), clamp(coverage, 0, 100)


# ------------------------------------------------------------------
# WIDGETS
# ------------------------------------------------------------------
class Card(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*PANEL)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])
            Color(*LINE_C)
            self._border = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(14)), width=1)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(14))


class MetricCard(Card):
    def __init__(self, title, value="--", **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(2), **kwargs)
        self.title_lbl = Label(text=title, color=MUTED, font_size="11sp", halign="left", valign="middle")
        self.value_lbl = Label(text=value, color=TEXT, font_size="24sp", bold=True, halign="left", valign="middle")
        self.title_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        self.value_lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        self.add_widget(self.title_lbl)
        self.add_widget(self.value_lbl)

    def set(self, text, color=None):
        self.value_lbl.text = str(text)
        if color is not None:
            self.value_lbl.color = color


class PoseOverlay(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.landmarks = {}
        self.valid = False
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw())

    def set_pose(self, landmarks, valid=True):
        self.landmarks = landmarks or {}
        self.valid = bool(valid)
        self.redraw()

    def clear_pose(self):
        self.landmarks = {}
        self.valid = False
        self.redraw()

    def redraw(self):
        self.canvas.clear()
        if not self.landmarks:
            return

        def xy(name):
            obj = self.landmarks.get(name)
            if not obj:
                return None
            try:
                if float(obj.get("c", 0)) < MIN_CONFIDENCE:
                    return None
                xn = clamp(float(obj["x"]), 0, 1)
                yn = clamp(float(obj["y"]), 0, 1)
                return (
                    self.x + xn * self.width,
                    self.y + (1.0 - yn) * self.height,
                )
            except Exception:
                return None

        with self.canvas:
            Color(*(GREEN if self.valid else YELLOW))
            for a, b in POSE_CONNECTIONS:
                p1, p2 = xy(a), xy(b)
                if p1 and p2:
                    Line(points=[p1[0], p1[1], p2[0], p2[1]], width=dp(2.2))

            Color(1, 1, 1, 0.98)
            r = dp(4.5)
            for name in KEY_LANDMARKS:
                p = xy(name)
                if p:
                    Ellipse(pos=(p[0]-r, p[1]-r), size=(2*r, 2*r))


# ------------------------------------------------------------------
# TELA PRINCIPAL
# ------------------------------------------------------------------
class NR17Screen(BoxLayout):
    status_text = StringProperty("Preparando câmera local...")

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(7), padding=dp(8), **kwargs)

        self.camera = None
        self.scatter = None
        self.overlay = None
        self.preview_area = None
        self.pose_analyzer = None
        self.pose_supported = False

        self.last_pose_seq = -1
        self.last_pose_data = None
        self.last_values = None
        self.last_valid_pose_time = 0.0
        self.last_metrics_tick = time.monotonic()

        self.total_time = 0.0
        self.invalid_time = 0.0
        self.risk_time = 0.0
        self.trunk_time = 0.0
        self.neck_time = 0.0
        self.arm_time = 0.0
        self.knee_time = 0.0
        self.events = 0
        self.was_risk = False
        self.max_ire = 0
        self.max_rula = 0
        self.max_reba = 0
        self.cycle_active = False
        self.cycle_start_total = 0.0
        self.cycle_count = 0

        self._frame_worker_busy = False
        self._running = False

        self._build_ui()
        Clock.schedule_once(lambda dt: self._request_camera_permission(), 0.2)

    # --------------------------- UI ---------------------------
    def _label(self, text, color=TEXT, size="14sp", bold=False):
        lbl = Label(text=text, color=color, font_size=size, bold=bold, halign="left", valign="middle")
        lbl.bind(size=lambda i, s: setattr(i, "text_size", s))
        return lbl

    def _button(self, text, callback, primary=False):
        btn = Button(
            text=text,
            background_normal="",
            background_color=(0.05, 0.36, 0.60, 1) if primary else (0.08, 0.18, 0.29, 1),
            color=TEXT,
            bold=True,
            font_size="13sp",
        )
        btn.bind(on_release=callback)
        return btn

    def _build_ui(self):
        # Cabeçalho
        header = Card(size_hint_y=None, height=dp(62), padding=dp(10), spacing=dp(10))
        title_box = BoxLayout(orientation="vertical")
        title_box.add_widget(self._label("NR-17 | ERGONOMIA POR VISÃO", CYAN, "20sp", True))
        title_box.add_widget(self._label("Câmera local + pose local no Android · sem Streamlit", MUTED, "11sp"))
        self.status_lbl = self._label(self.status_text, YELLOW, "11sp", True)
        self.bind(status_text=lambda *_: setattr(self.status_lbl, "text", self.status_text))
        header.add_widget(title_box)
        header.add_widget(self.status_lbl)
        self.add_widget(header)

        # Identificação compacta
        meta = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.in_setor = TextInput(hint_text="Setor", multiline=False, background_color=PANEL_2, foreground_color=TEXT)
        self.in_posto = TextInput(hint_text="Operação / Posto", multiline=False, background_color=PANEL_2, foreground_color=TEXT)
        self.in_colab = TextInput(hint_text="Colaborador", multiline=False, background_color=PANEL_2, foreground_color=TEXT)
        meta.add_widget(self.in_setor)
        meta.add_widget(self.in_posto)
        meta.add_widget(self.in_colab)
        self.add_widget(meta)

        # Área principal
        main = BoxLayout(orientation="horizontal", spacing=dp(8))

        # Preview
        left = Card(orientation="vertical", padding=dp(6), spacing=dp(6), size_hint_x=0.72)
        self.preview_area = FloatLayout()
        left.add_widget(self.preview_area)

        controls = GridLayout(cols=5, size_hint_y=None, height=dp(52), spacing=dp(5))
        controls.add_widget(self._button("INICIAR", self.start_camera, primary=True))
        controls.add_widget(self._button("PARAR", self.stop_camera))
        controls.add_widget(self._button("CICLO", self.toggle_cycle))
        controls.add_widget(self._button("EVIDÊNCIA", self.capture_evidence))
        controls.add_widget(self._button("ZERAR", self.reset_measurement))
        left.add_widget(controls)
        main.add_widget(left)

        # Painel direito
        right = BoxLayout(orientation="vertical", spacing=dp(7), size_hint_x=0.28)

        quality_card = Card(orientation="vertical", size_hint_y=None, height=dp(76), padding=dp(8))
        quality_card.add_widget(self._label("QUALIDADE DA CAPTURA", MUTED, "10sp", True))
        self.quality_lbl = self._label("--", TEXT, "20sp", True)
        self.detail_lbl = self._label("aguardando pose", MUTED, "10sp")
        quality_card.add_widget(self.quality_lbl)
        quality_card.add_widget(self.detail_lbl)
        right.add_widget(quality_card)

        grid = GridLayout(cols=2, spacing=dp(6))
        self.metrics = {}
        for key, title in [
            ("ire","IRE"),
            ("rula","RULA"),
            ("reba","REBA"),
            ("tempo","TEMPO VÁLIDO"),
            ("exp","EXPOSIÇÃO"),
            ("posefps","POSE FPS"),
            ("trunk","TRONCO"),
            ("neck","PESCOÇO"),
            ("arm","BRAÇO D/E"),
            ("knee","JOELHO D/E"),
        ]:
            card = MetricCard(title)
            self.metrics[key] = card
            grid.add_widget(card)
        right.add_widget(grid)
        main.add_widget(right)
        self.add_widget(main)

    # --------------------------- Android / ML Kit ---------------------------
    def _request_camera_permission(self):
        if platform != "android":
            self.status_text = "Modo desktop: câmera pode funcionar, pose ML Kit exige APK Android."
            self._init_camera_widget()
            return

        try:
            from android.permissions import request_permissions, Permission

            def callback(perms, grants):
                ok = all(bool(x) for x in grants) if grants else False
                Clock.schedule_once(lambda dt: self._after_permission(ok), 0)

            request_permissions([Permission.CAMERA], callback)
        except Exception as exc:
            self.status_text = f"Falha ao solicitar câmera: {exc}"

    def _after_permission(self, granted):
        if not granted:
            self.status_text = "Permissão de câmera negada."
            return
        self._init_pose_analyzer()
        self._init_camera_widget()
        Clock.schedule_once(lambda dt: self.start_camera(), 0.5)

    def _init_pose_analyzer(self):
        if platform != "android":
            return
        try:
            from jnius import autoclass
            Analyzer = autoclass("br.com.ibero.nr17.PoseAnalyzer")
            self.pose_analyzer = Analyzer()
            self.pose_supported = True
            self.status_text = "ML Kit local carregado. Preparando câmera..."
        except Exception as exc:
            self.pose_analyzer = None
            self.pose_supported = False
            self.status_text = f"ML Kit não carregou: {exc}"

    # --------------------------- Câmera ---------------------------
    def _init_camera_widget(self):
        if self.camera is not None:
            return

        try:
            self.camera = Camera(index=CAMERA_INDEX, play=False, resolution=(CAM_W, CAM_H))
            self.camera.allow_stretch = True
            self.camera.keep_ratio = True
        except Exception as exc:
            self.status_text = f"Falha ao criar câmera: {exc}"
            return

        self.scatter = Scatter(
            do_rotation=False,
            do_translation=False,
            do_scale=False,
            auto_bring_to_front=False,
        )
        self.scatter.rotation = CAMERA_PREVIEW_ROTATION
        self.scatter.add_widget(self.camera)

        self.overlay = PoseOverlay()
        self.preview_area.add_widget(self.scatter)
        self.preview_area.add_widget(self.overlay)

        self.preview_area.bind(size=self._fit_preview, pos=self._fit_preview)
        Clock.schedule_once(lambda dt: self._fit_preview(), 0.1)

    def _fit_preview(self, *_):
        if not self.camera or not self.scatter or not self.preview_area:
            return

        w, h = self.preview_area.size
        if w <= 0 or h <= 0:
            return

        rot = abs(CAMERA_PREVIEW_ROTATION) % 180
        if rot == 90:
            cam_w, cam_h = h, w
        else:
            cam_w, cam_h = w, h

        self.camera.size_hint = (None, None)
        self.camera.pos = (0, 0)
        self.camera.size = (cam_w, cam_h)

        self.scatter.size_hint = (None, None)
        self.scatter.size = (cam_w, cam_h)
        self.scatter.center = self.preview_area.center

        self.overlay.pos = self.preview_area.pos
        self.overlay.size = self.preview_area.size

    def start_camera(self, *_):
        if self.camera is None:
            self._init_camera_widget()
        if self.camera is None:
            return

        try:
            self.camera.play = True
            self._running = True
            self.status_text = "Câmera local ativa · análise local em segundo plano."
            Clock.unschedule(self._analysis_tick)
            Clock.unschedule(self._poll_pose_result)
            Clock.schedule_interval(self._analysis_tick, POSE_INTERVAL)
            Clock.schedule_interval(self._poll_pose_result, 0.08)
        except Exception as exc:
            self.status_text = f"Falha ao iniciar câmera: {exc}"

    def stop_camera(self, *_):
        self._running = False
        Clock.unschedule(self._analysis_tick)
        Clock.unschedule(self._poll_pose_result)
        try:
            if self.camera:
                self.camera.play = False
        except Exception:
            pass
        self.status_text = "Câmera parada."

    # --------------------------- Frame -> ML Kit ---------------------------
    def _analysis_tick(self, _dt):
        if not self._running or not self.camera or not self.pose_analyzer:
            return
        if self._frame_worker_busy:
            return

        try:
            if bool(self.pose_analyzer.isBusy()):
                return
        except Exception:
            return

        texture = self.camera.texture
        if texture is None:
            return

        try:
            size = tuple(int(x) for x in texture.size)
            pixels = bytes(texture.pixels)
            if not pixels or size[0] <= 0 or size[1] <= 0:
                return
        except Exception:
            return

        self._frame_worker_busy = True
        threading.Thread(
            target=self._prepare_frame_worker,
            args=(pixels, size),
            daemon=True,
        ).start()

    def _prepare_frame_worker(self, pixels, size):
        try:
            img = Image.frombytes("RGBA", size, pixels)
            w, h = img.size

            long_side = max(w, h)
            if long_side > POSE_LONG_SIDE:
                scale = POSE_LONG_SIDE / float(long_side)
                nw = max(2, int(round(w * scale)))
                nh = max(2, int(round(h * scale)))
                try:
                    resample = Image.Resampling.BILINEAR
                except Exception:
                    resample = Image.BILINEAR
                img = img.resize((nw, nh), resample=resample)

            rgba = img.tobytes()
            w, h = img.size

            try:
                accepted = bool(self.pose_analyzer.analyze(rgba, int(w), int(h), int(POSE_ROTATION)))
                if not accepted:
                    pass
            except Exception as exc:
                Clock.schedule_once(
                    lambda dt, msg=str(exc): self._set_status(f"Falha no analisador: {msg}"),
                    0
                )
        except Exception as exc:
            Clock.schedule_once(
                lambda dt, msg=str(exc): self._set_status(f"Falha preparando frame: {msg}"),
                0
            )
        finally:
            self._frame_worker_busy = False

    def _set_status(self, text):
        self.status_text = str(text)

    def _poll_pose_result(self, _dt):
        if not self.pose_analyzer:
            return
        try:
            raw = str(self.pose_analyzer.getLatestJson() or "")
        except Exception:
            return
        if not raw:
            return

        try:
            data = json.loads(raw)
        except Exception:
            return

        seq = int(data.get("seq", -1))
        if seq == self.last_pose_seq:
            return
        self.last_pose_seq = seq
        self.last_pose_data = data

        if not data.get("detected"):
            self.invalid_time += min(0.4, max(0.0, time.monotonic() - self.last_metrics_tick))
            self.last_metrics_tick = time.monotonic()
            if self.overlay:
                self.overlay.clear_pose()
            self.quality_lbl.text = "SEM CORPO"
            self.quality_lbl.color = YELLOW
            self.detail_lbl.text = f"ML Kit {data.get('inferenceMs',0)} ms"
            return

        landmarks = data.get("landmarks") or {}
        quality, coverage = pose_quality(landmarks)
        values = derive_pose_values(landmarks)

        now = time.monotonic()
        dt = clamp(now - self.last_metrics_tick, 0.0, 0.4)
        self.last_metrics_tick = now
        self.last_valid_pose_time = now

        self._accumulate(values, dt)
        self.last_values = values

        valid = quality >= 55.0
        if self.overlay:
            self.overlay.set_pose(landmarks, valid=valid)

        self._update_ui(data, landmarks, values, quality, coverage)

    def _accumulate(self, v, dt):
        if dt <= 0:
            return

        trunk_flag = v.get("trunk") is not None and v["trunk"] >= TRUNK_LIMIT
        neck_flag = v.get("neck") is not None and v["neck"] >= NECK_LIMIT
        arms = [x for x in (v.get("shoulder_l"), v.get("shoulder_r")) if x is not None]
        knees = [x for x in (v.get("knee_l"), v.get("knee_r")) if x is not None]
        arm_flag = bool(arms) and max(arms) >= ARM_LIMIT
        knee_flag = bool(knees) and min(knees) <= KNEE_LIMIT

        self.total_time += dt
        if trunk_flag: self.trunk_time += dt
        if neck_flag: self.neck_time += dt
        if arm_flag: self.arm_time += dt
        if knee_flag: self.knee_time += dt

        risk_now = trunk_flag or neck_flag or arm_flag or knee_flag
        if risk_now:
            self.risk_time += dt
            if not self.was_risk:
                self.events += 1
        self.was_risk = risk_now

        self.max_ire = max(self.max_ire, int(v.get("ire", 0)))
        self.max_rula = max(self.max_rula, int(v.get("rula", 0)))
        self.max_reba = max(self.max_reba, int(v.get("reba", 0)))

    def _update_ui(self, data, landmarks, v, quality, coverage):
        ire = int(v.get("ire", 0))
        self.quality_lbl.text = f"{quality:.0f}%"
        self.quality_lbl.color = GREEN if quality >= 70 else YELLOW if quality >= 55 else RED

        inf_ms = max(1, int(data.get("inferenceMs", 0) or 0))
        pose_fps = 1000.0 / inf_ms if inf_ms else 0
        self.detail_lbl.text = f"cobertura {coverage:.0f}% · ML Kit {inf_ms} ms"

        self.metrics["ire"].set(f"{ire}/100", risk_color(ire))
        self.metrics["rula"].set(f"{v.get('rula',0)}/7")
        self.metrics["reba"].set(f"{v.get('reba',0)}/15")
        self.metrics["tempo"].set(fmt_seconds(self.total_time))
        self.metrics["exp"].set(f"{(100*self.risk_time/self.total_time if self.total_time else 0):.1f}%")
        self.metrics["posefps"].set(f"{pose_fps:.1f}")

        self.metrics["trunk"].set(fmt_angle(v.get("trunk")))
        self.metrics["neck"].set(fmt_angle(v.get("neck")))
        self.metrics["arm"].set(
            f"{fmt_angle(v.get('shoulder_r'))} / {fmt_angle(v.get('shoulder_l'))}"
        )
        self.metrics["knee"].set(
            f"{fmt_angle(v.get('knee_r'))} / {fmt_angle(v.get('knee_l'))}"
        )

    # --------------------------- Ciclo / Evidência ---------------------------
    def toggle_cycle(self, *_):
        if not self.cycle_active:
            self.cycle_active = True
            self.cycle_start_total = self.total_time
            self.status_text = f"Ciclo {self.cycle_count + 1} iniciado."
        else:
            duration = max(0.0, self.total_time - self.cycle_start_total)
            self.cycle_count += 1
            self.cycle_active = False
            self.status_text = f"Ciclo {self.cycle_count} fechado · {fmt_seconds(duration)}."

    def _evidence_dir(self):
        app = App.get_running_app()
        base = Path(getattr(app, "user_data_dir", str(BASE_DIR))) / "evidencias_nr17"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def capture_evidence(self, *_):
        if not self.camera or self.camera.texture is None:
            self.status_text = "Sem imagem disponível para evidência."
            return

        try:
            size = tuple(int(x) for x in self.camera.texture.size)
            pixels = bytes(self.camera.texture.pixels)
            img = Image.frombytes("RGBA", size, pixels)
            if POSE_ROTATION:
                img = img.rotate(POSE_ROTATION, expand=True)
            img = img.convert("RGB")

            draw = ImageDraw.Draw(img)
            landmarks = (self.last_pose_data or {}).get("landmarks") or {}

            def pxy(name):
                obj = landmarks.get(name)
                if not obj or float(obj.get("c", 0)) < MIN_CONFIDENCE:
                    return None
                return (
                    int(clamp(float(obj["x"]), 0, 1) * img.width),
                    int(clamp(float(obj["y"]), 0, 1) * img.height),
                )

            for a, b in POSE_CONNECTIONS:
                pa, pb = pxy(a), pxy(b)
                if pa and pb:
                    draw.line([pa, pb], fill=(50, 230, 255), width=max(3, img.width // 320))

            rr = max(4, img.width // 220)
            for name in KEY_LANDMARKS:
                pt = pxy(name)
                if pt:
                    draw.ellipse(
                        (pt[0]-rr, pt[1]-rr, pt[0]+rr, pt[1]+rr),
                        fill=(255,255,255),
                        outline=(50,230,255),
                        width=max(2, img.width // 500),
                    )

            values = self.last_values or {}
            panel_h = max(84, int(img.height * 0.13))
            draw.rectangle((0, img.height-panel_h, img.width, img.height), fill=(8, 20, 34))
            text = (
                f"NR-17 | IRE {values.get('ire',0)} | "
                f"RULA {values.get('rula',0)}/7 | REBA {values.get('reba',0)}/15 | "
                f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            )
            draw.text((20, img.height-panel_h+18), text, fill="white")
            draw.text(
                (20, img.height-panel_h+48),
                f"Setor: {self.in_setor.text or '-'} | Posto: {self.in_posto.text or '-'} | Colaborador: {self.in_colab.text or '-'}",
                fill=(200,220,235)
            )

            path = self._evidence_dir() / f"nr17_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            img.save(str(path), "JPEG", quality=94)
            self.status_text = f"Evidência salva: {path.name}"
        except Exception as exc:
            self.status_text = f"Erro ao salvar evidência: {exc}"

    def reset_measurement(self, *_):
        self.total_time = self.invalid_time = self.risk_time = 0.0
        self.trunk_time = self.neck_time = self.arm_time = self.knee_time = 0.0
        self.events = 0
        self.was_risk = False
        self.max_ire = self.max_rula = self.max_reba = 0
        self.cycle_active = False
        self.cycle_count = 0
        self.last_values = None
        self.last_metrics_tick = time.monotonic()
        self.status_text = "Medição zerada."
        for key, card in self.metrics.items():
            card.set("--")
        if self.overlay:
            self.overlay.clear_pose()

    def shutdown(self):
        self.stop_camera()
        try:
            if self.pose_analyzer:
                self.pose_analyzer.close()
        except Exception:
            pass


# ------------------------------------------------------------------
# APP
# ------------------------------------------------------------------
class NR17App(App):
    def build(self):
        self.title = APP_TITLE
        self.screen = NR17Screen()
        return self.screen

    def on_pause(self):
        try:
            self.screen.stop_camera()
        except Exception:
            pass
        return True

    def on_resume(self):
        try:
            Clock.schedule_once(lambda dt: self.screen.start_camera(), 0.5)
        except Exception:
            pass

    def on_stop(self):
        try:
            self.screen.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    NR17App().run()
