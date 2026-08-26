# ============================================================
# NR-17 | ERGONOMIA POR VISÃO - ANDROID LOCAL MVP 0.1.5
# Kivy + ML Kit local + calibração em tempo real + evidências + PDF
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
from kivy.uix.popup import Popup
from kivy.uix.scatter import Scatter
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

from PIL import Image, ImageDraw, ImageFont

APP_TITLE = "NR-17 | Ergonomia por Visão"
APP_VERSION = "0.1.5"

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
# CONFIG PADRÃO DO APK
# O JSON salvo no tablet tem prioridade sobre estes valores.
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


def env_bool(name, default=False):
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in ("1", "true", "yes", "sim", "on")


CAMERA_INDEX = env_int("CAMERA_TRASEIRA_INDEX", 0)
DEFAULT_CAMERA_PREVIEW_ROTATION = env_int("CAMERA_PREVIEW_ROTATION", 0) % 360
DEFAULT_POSE_ROTATION = env_int("POSE_ROTATION", 270) % 360
# Primeiro APK já inicia com correção do problema relatado: esqueleto invertido em X.
DEFAULT_MIRROR_X = env_bool("CAMERA_PREVIEW_MIRROR_X", True)
DEFAULT_MIRROR_Y = env_bool("CAMERA_PREVIEW_MIRROR_Y", False)

CAM_W = env_int("CAMERA_WIDTH", 1280)
CAM_H = env_int("CAMERA_HEIGHT", 720)
POSE_LONG_SIDE = env_int("POSE_INPUT_LONG_SIDE", 640)
POSE_INTERVAL = max(0.08, env_float("POSE_INTERVAL", 0.12))
MIN_CONFIDENCE = max(0.25, min(0.95, env_float("POSE_MIN_CONFIDENCE", 0.45)))
ANGLE_MIN_CONFIDENCE = max(
    MIN_CONFIDENCE,
    min(0.95, env_float("ANGLE_MIN_CONFIDENCE", 0.60))
)
LANDMARK_CONFIRM_FRAMES = max(1, env_int("LANDMARK_CONFIRM_FRAMES", 2))
LANDMARK_JUMP_LIMIT = max(0.03, min(0.50, env_float("LANDMARK_JUMP_LIMIT", 0.18)))
LANDMARK_SMOOTH_ALPHA = max(0.10, min(1.0, env_float("LANDMARK_SMOOTH_ALPHA", 0.65)))

TRUNK_LIMIT = env_float("IRE_TRONCO", 25.0)
NECK_LIMIT = env_float("IRE_PESCOCO", 25.0)
ARM_LIMIT = env_float("IRE_BRACO", 60.0)
KNEE_LIMIT = env_float("IRE_JOELHO", 130.0)

# ------------------------------------------------------------------
# HELPERS
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
    val = clamp((v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2), -1.0, 1.0)
    return math.degrees(math.acos(val))


def vertical_deviation(a, b):
    """Desvio do segmento em relacao ao eixo vertical, sempre entre 0 e 90 graus."""
    if not a or not b:
        return None
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    if math.hypot(dx, dy) < 1e-9:
        return None
    # Independente de o eixo Y da textura crescer para cima ou para baixo.
    return math.degrees(math.atan2(abs(dx), max(abs(dy), 1e-9)))


def acute_angle(value):
    """Retorna o menor angulo equivalente entre dois eixos (0 a 90 graus)."""
    if value is None:
        return None
    a = abs(float(value)) % 180.0
    return min(a, 180.0 - a)


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


def source_xy(obj):
    """Coordenada normalizada na geometria ORIGINAL da textura da câmera."""
    if not obj:
        return None
    try:
        x = float(obj.get("sx", obj.get("x")))
        y = float(obj.get("sy", obj.get("y")))
        return clamp(x, 0.0, 1.0), clamp(y, 0.0, 1.0)
    except Exception:
        return None


def rotate_norm_ccw(x, y, degrees):
    r = int(degrees or 0) % 360
    if r == 90:
        return y, 1.0 - x
    if r == 180:
        return 1.0 - x, 1.0 - y
    if r == 270:
        return 1.0 - y, x
    return x, y


def transform_preview_xy(x, y, rotation, mirror_x=False, mirror_y=False):
    """Transformação única usada na tela e nas evidências."""
    x, y = rotate_norm_ccw(x, y, rotation)
    if mirror_x:
        x = 1.0 - x
    if mirror_y:
        y = 1.0 - y
    return clamp(x, 0.0, 1.0), clamp(y, 0.0, 1.0)


def safe_pct(part, total):
    return 100.0 * float(part) / float(total) if total else 0.0


def load_report_font(size, bold=False):
    candidates = []
    if bold:
        candidates.extend([
            "/system/fonts/Roboto-Bold.ttf",
            "/system/fonts/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/system/fonts/Roboto-Regular.ttf",
            "/system/fonts/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ])
    for path in candidates:
        try:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def draw_wrapped(draw, text, xy, font, fill, max_width, line_gap=6):
    x, y = xy
    words = str(text or "").split()
    line = ""
    lines = []
    for word in words:
        test = word if not line else f"{line} {word}"
        try:
            box = draw.textbbox((0, 0), test, font=font)
            width = box[2] - box[0]
        except Exception:
            width = len(test) * 8
        if line and width > max_width:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    try:
        bbox = draw.textbbox((0, 0), "Ag", font=font)
        line_h = max(18, bbox[3] - bbox[1] + line_gap)
    except Exception:
        line_h = 24
    for item in lines:
        draw.text((x, y), item, font=font, fill=fill)
        y += line_h
    return y

# ------------------------------------------------------------------
# RULA / REBA
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
    if elbow is None: return 1
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
    legs = 1
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
    if elbow is None: return 1
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
    s_knee = 0 if knee >= KNEE_LIMIT else clamp((KNEE_LIMIT - knee) / max(KNEE_LIMIT - 70, 1) * 100, 0, 100)
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
    "left_ear", "right_ear",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
]

POSE_CONNECTIONS = [
    ("left_ear", "left_shoulder"), ("right_ear", "right_shoulder"),
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
]


def landmark_point(landmarks, name, min_conf=ANGLE_MIN_CONFIDENCE):
    obj = (landmarks or {}).get(name)
    if not obj:
        return None
    try:
        if float(obj.get("c", 0)) < min_conf:
            return None
        return source_xy(obj)
    except Exception:
        return None


def derive_pose_values(landmarks, preview_rotation=0):
    def p(name):
        pt = landmark_point(landmarks, name)
        if pt is None:
            return None
        # Calcula a postura na mesma orientação em que a pessoa aparece no preview.
        # Espelhamento não muda magnitudes angulares; rotação muda a referência vertical.
        return rotate_norm_ccw(pt[0], pt[1], preview_rotation)
    ls, rs = p("left_shoulder"), p("right_shoulder")
    lh, rh = p("left_hip"), p("right_hip")
    le, re = p("left_ear"), p("right_ear")
    sm = midpoint(ls, rs)
    hm = midpoint(lh, rh)
    em = midpoint(le, re)
    # Tronco: desvio real da vertical. Uma pessoa ereta deve ficar proxima de 0°,
    # nunca proxima de 180°. A conta independe do sentido do eixo Y da camera.
    trunk = vertical_deviation(sm, hm) if sm and hm else None

    # Pescoço: menor angulo entre o eixo cabeca/ombros e o eixo do tronco.
    neck_raw = vector_angle(
        (em[0]-sm[0], em[1]-sm[1]),
        (sm[0]-hm[0], sm[1]-hm[1])
    ) if em and sm and hm else None
    neck = acute_angle(neck_raw)
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
    right_ready = all(v is not None for v in [sh_r, el_r])
    left_ready = all(v is not None for v in [sh_l, el_l])
    analysis_side = "right" if right_ready else ("left" if left_ready else None)
    vals["analysis_side"] = analysis_side or "--"
    base_ready = trunk is not None and neck is not None and analysis_side is not None
    if base_ready:
        vals["rula"] = calculate_rula(vals, side=analysis_side)
        knee_side = kn_r if analysis_side == "right" else kn_l
        vals["reba"] = calculate_reba(vals, side=analysis_side) if knee_side is not None else 0
    else:
        vals["rula"] = 0
        vals["reba"] = 0
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
        self.image_rect = None
        self.preview_rotation = DEFAULT_CAMERA_PREVIEW_ROTATION
        self.mirror_x = DEFAULT_MIRROR_X
        self.mirror_y = DEFAULT_MIRROR_Y
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw())

    def set_transform(self, rotation, mirror_x=False, mirror_y=False):
        self.preview_rotation = int(rotation or 0) % 360
        self.mirror_x = bool(mirror_x)
        self.mirror_y = bool(mirror_y)
        self.redraw()

    def set_image_rect(self, x, y, w, h):
        self.image_rect = (float(x), float(y), float(w), float(h))
        self.redraw()

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
        rx, ry, rw, rh = self.image_rect or (self.x, self.y, self.width, self.height)
        if rw <= 1 or rh <= 1:
            return

        def xy(name):
            obj = self.landmarks.get(name)
            if not obj:
                return None
            try:
                if float(obj.get("c", 0)) < ANGLE_MIN_CONFIDENCE:
                    return None
                pt = source_xy(obj)
                if pt is None:
                    return None
                xn, yn = transform_preview_xy(
                    pt[0], pt[1], self.preview_rotation, self.mirror_x, self.mirror_y
                )
                return (rx + xn * rw, ry + (1.0 - yn) * rh)
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

        # Calibração dinâmica: não exige novo APK para rotação/espelhamento.
        self.camera_preview_rotation = DEFAULT_CAMERA_PREVIEW_ROTATION
        self.pose_rotation = DEFAULT_POSE_ROTATION
        self.mirror_x = DEFAULT_MIRROR_X
        self.mirror_y = DEFAULT_MIRROR_Y
        self._calibration_popup = None
        self._calibration_status = None
        self._load_calibration()

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
        self.peak_values = {}
        self.peak_at = None
        self.last_quality = 0.0
        self.last_coverage = 0.0
        self.cycle_active = False
        self.cycle_start_total = 0.0
        self.cycle_count = 0
        self.cycle_records = []

        self.assessment_started_at = datetime.now()
        self.assessment_id = self.assessment_started_at.strftime("%Y%m%d_%H%M%S")
        self.assessment_dir = None
        self.evidence_records = []
        self.last_exported_report = None

        self._landmark_state = {}
        self._landmark_streak = {}
        self._frame_worker_busy = False
        self._running = False

        self._build_ui()
        Clock.schedule_once(lambda dt: self._request_camera_permission(), 0.2)

    # --------------------------- Configuração persistente ---------------------------
    def _calibration_path(self):
        app = App.get_running_app()
        base = Path(getattr(app, "user_data_dir", str(BASE_DIR)))
        base.mkdir(parents=True, exist_ok=True)
        return base / "camera_calibration.json"

    def _load_calibration(self):
        try:
            path = self._calibration_path()
            if not path.exists():
                return
            cfg = json.loads(path.read_text(encoding="utf-8"))
            self.camera_preview_rotation = int(cfg.get("camera_preview_rotation", self.camera_preview_rotation)) % 360
            self.pose_rotation = int(cfg.get("pose_rotation", self.pose_rotation)) % 360
            self.mirror_x = bool(cfg.get("mirror_x", self.mirror_x))
            self.mirror_y = bool(cfg.get("mirror_y", self.mirror_y))
        except Exception:
            pass

    def _save_calibration(self):
        cfg = {
            "camera_preview_rotation": int(self.camera_preview_rotation) % 360,
            "pose_rotation": int(self.pose_rotation) % 360,
            "mirror_x": bool(self.mirror_x),
            "mirror_y": bool(self.mirror_y),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        }
        path = self._calibration_path()
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status_text = "Calibração da câmera salva neste tablet."
        self._refresh_calibration_status()
        return path

    def _apply_calibration(self):
        self.camera_preview_rotation %= 360
        self.pose_rotation %= 360
        if self.scatter:
            self.scatter.rotation = self.camera_preview_rotation
        if self.overlay:
            self.overlay.set_transform(self.camera_preview_rotation, self.mirror_x, self.mirror_y)
        self._landmark_state = {}
        self._landmark_streak = {}
        self.last_pose_seq = -1
        self._fit_preview()
        self._refresh_calibration_status()

    def _refresh_calibration_status(self):
        if self._calibration_status:
            self._calibration_status.text = (
                f"CÂMERA: {self.camera_preview_rotation}°   |   "
                f"POSE: {self.pose_rotation}°   |   "
                f"ESPELHO X: {'SIM' if self.mirror_x else 'NÃO'}   |   "
                f"ESPELHO Y: {'SIM' if self.mirror_y else 'NÃO'}"
            )

    def _calib_camera_rotate(self, *_):
        self.camera_preview_rotation = (self.camera_preview_rotation + 90) % 360
        self._apply_calibration()

    def _calib_pose_rotate(self, *_):
        self.pose_rotation = (self.pose_rotation + 90) % 360
        self._apply_calibration()

    def _calib_mirror_x(self, *_):
        self.mirror_x = not self.mirror_x
        self._apply_calibration()

    def _calib_mirror_y(self, *_):
        self.mirror_y = not self.mirror_y
        self._apply_calibration()

    def _calib_defaults(self, *_):
        self.camera_preview_rotation = DEFAULT_CAMERA_PREVIEW_ROTATION
        self.pose_rotation = DEFAULT_POSE_ROTATION
        self.mirror_x = DEFAULT_MIRROR_X
        self.mirror_y = DEFAULT_MIRROR_Y
        self._apply_calibration()
        self.status_text = "Padrão restaurado. Use SALVAR para manter após fechar o aplicativo."

    def open_calibration(self, *_):
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))
        title = self._label("CALIBRAÇÃO AO VIVO", CYAN, "20sp", True)
        instruction = self._label(
            "Fique em frente à câmera e levante o braço DIREITO. Ajuste até o esqueleto ficar exatamente sobre a pessoa. As mudanças são aplicadas na hora.",
            TEXT, "13sp"
        )
        instruction.size_hint_y = None
        instruction.height = dp(58)
        self._calibration_status = self._label("", YELLOW, "14sp", True)
        self._calibration_status.size_hint_y = None
        self._calibration_status.height = dp(42)
        content.add_widget(title)
        content.add_widget(instruction)
        content.add_widget(self._calibration_status)

        grid = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(128))
        grid.add_widget(self._button("GIRAR CÂMERA +90°", self._calib_camera_rotate))
        grid.add_widget(self._button("GIRAR ESQUELETO +90°", self._calib_pose_rotate))
        grid.add_widget(self._button("ESPELHAR HORIZONTAL", self._calib_mirror_x, primary=True))
        grid.add_widget(self._button("ESPELHAR VERTICAL", self._calib_mirror_y))
        content.add_widget(grid)

        footer = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(52))
        footer.add_widget(self._button("RESTAURAR PADRÃO", self._calib_defaults))
        footer.add_widget(self._button("SALVAR", lambda *_: self._save_calibration(), primary=True))
        close_btn = self._button("FECHAR", lambda *_: self._calibration_popup.dismiss())
        footer.add_widget(close_btn)
        content.add_widget(footer)

        self._calibration_popup = Popup(
            title="Configuração da câmera / esqueleto",
            content=content,
            size_hint=(0.62, 0.78),
            auto_dismiss=False,
            background_color=(0.02, 0.06, 0.10, 0.72),
        )
        self._refresh_calibration_status()
        self._calibration_popup.open()

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
        header = Card(size_hint_y=None, height=dp(62), padding=dp(10), spacing=dp(10))
        title_box = BoxLayout(orientation="vertical")
        title_box.add_widget(self._label("NR-17 | ERGONOMIA POR VISÃO", CYAN, "20sp", True))
        title_box.add_widget(self._label(f"ML Kit local · calibração ao vivo · evidências · PDF · v{APP_VERSION}", MUTED, "11sp"))
        self.status_lbl = self._label(self.status_text, YELLOW, "11sp", True)
        self.bind(status_text=lambda *_: setattr(self.status_lbl, "text", self.status_text))
        header.add_widget(title_box)
        header.add_widget(self.status_lbl)
        self.add_widget(header)

        meta = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.in_setor = TextInput(hint_text="Setor", multiline=False, background_color=PANEL_2, foreground_color=TEXT)
        self.in_posto = TextInput(hint_text="Operação / Posto", multiline=False, background_color=PANEL_2, foreground_color=TEXT)
        self.in_colab = TextInput(hint_text="Colaborador", multiline=False, background_color=PANEL_2, foreground_color=TEXT)
        meta.add_widget(self.in_setor)
        meta.add_widget(self.in_posto)
        meta.add_widget(self.in_colab)
        self.add_widget(meta)

        main = BoxLayout(orientation="horizontal", spacing=dp(8))
        left = Card(orientation="vertical", padding=dp(6), spacing=dp(6), size_hint_x=0.72)
        self.preview_area = FloatLayout()
        left.add_widget(self.preview_area)

        controls = GridLayout(cols=7, size_hint_y=None, height=dp(52), spacing=dp(5))
        controls.add_widget(self._button("INICIAR", self.start_camera, primary=True))
        controls.add_widget(self._button("PARAR", self.stop_camera))
        controls.add_widget(self._button("CICLO", self.toggle_cycle))
        controls.add_widget(self._button("FOTO +", self.capture_evidence, primary=True))
        controls.add_widget(self._button("RELATÓRIO", self.generate_report))
        controls.add_widget(self._button("⚙ CÂMERA", self.open_calibration))
        controls.add_widget(self._button("ZERAR", self.reset_measurement))
        left.add_widget(controls)

        evidence_bar = Card(
            orientation="horizontal", size_hint_y=None, height=dp(34),
            padding=(dp(10), dp(4)), spacing=dp(8)
        )
        self.evidence_count_lbl = self._label(
            "EVIDÊNCIAS: 0  ·  Toque em FOTO + para adicionar quantas imagens precisar.",
            MUTED, "10sp", True
        )
        evidence_bar.add_widget(self.evidence_count_lbl)
        remove_btn = self._button("REMOVER ÚLTIMA", self.remove_last_evidence)
        remove_btn.size_hint_x = None
        remove_btn.width = dp(150)
        evidence_bar.add_widget(remove_btn)
        left.add_widget(evidence_bar)
        main.add_widget(left)

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
            ("ire", "IRE"), ("rula", "RULA"), ("reba", "REBA"),
            ("tempo", "TEMPO VÁLIDO"), ("exp", "EXPOSIÇÃO"), ("posefps", "POSE FPS"),
            ("trunk", "TRONCO"), ("neck", "PESCOÇO"),
            ("arm", "BRAÇO D/E"), ("knee", "JOELHO D/E"),
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
            self.status_text = "Modo desktop: câmera pode funcionar; pose ML Kit exige APK Android."
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
        self.scatter.rotation = self.camera_preview_rotation
        self.scatter.add_widget(self.camera)

        self.overlay = PoseOverlay()
        self.overlay.set_transform(self.camera_preview_rotation, self.mirror_x, self.mirror_y)
        self.preview_area.add_widget(self.scatter)
        self.preview_area.add_widget(self.overlay)
        self.preview_area.bind(size=self._fit_preview, pos=self._fit_preview)
        Clock.schedule_once(lambda dt: self._fit_preview(), 0.1)

    def _preview_image_rect(self):
        if not self.preview_area:
            return (0, 0, 0, 0)
        ax, ay = self.preview_area.pos
        aw, ah = self.preview_area.size
        if aw <= 1 or ah <= 1:
            return (ax, ay, aw, ah)
        tw, th = CAM_W, CAM_H
        try:
            if self.camera and self.camera.texture:
                tw, th = [float(v) for v in self.camera.texture.size]
        except Exception:
            pass
        if int(self.camera_preview_rotation) % 180 == 90:
            tw, th = th, tw
        if tw <= 0 or th <= 0:
            return (ax, ay, aw, ah)
        scale = min(aw / tw, ah / th)
        dw, dh = tw * scale, th * scale
        dx = ax + (aw - dw) / 2.0
        dy = ay + (ah - dh) / 2.0
        return (dx, dy, dw, dh)

    def _fit_preview(self, *_):
        if not self.camera or not self.scatter or not self.preview_area:
            return
        w, h = self.preview_area.size
        if w <= 0 or h <= 0:
            return
        rot = abs(self.camera_preview_rotation) % 180
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
        self.scatter.rotation = self.camera_preview_rotation
        self.overlay.pos = self.preview_area.pos
        self.overlay.size = self.preview_area.size
        self.overlay.set_transform(self.camera_preview_rotation, self.mirror_x, self.mirror_y)
        self.overlay.set_image_rect(*self._preview_image_rect())

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
        threading.Thread(target=self._prepare_frame_worker, args=(pixels, size), daemon=True).start()

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
                self.pose_analyzer.analyze(rgba, int(w), int(h), int(self.pose_rotation))
            except Exception as exc:
                Clock.schedule_once(lambda dt, msg=str(exc): self._set_status(f"Falha no analisador: {msg}"), 0)
        except Exception as exc:
            Clock.schedule_once(lambda dt, msg=str(exc): self._set_status(f"Falha preparando frame: {msg}"), 0)
        finally:
            self._frame_worker_busy = False

    def _set_status(self, text):
        self.status_text = str(text)

    def _filter_landmarks(self, landmarks):
        filtered = {}
        seen = set()
        for name, obj in (landmarks or {}).items():
            try:
                conf = float(obj.get("c", 0))
            except Exception:
                conf = 0.0
            if conf < ANGLE_MIN_CONFIDENCE:
                self._landmark_streak[name] = 0
                continue
            pt = source_xy(obj)
            if pt is None:
                self._landmark_streak[name] = 0
                continue
            x, y = pt
            prev = self._landmark_state.get(name)
            if prev is not None:
                px, py = prev["sx"], prev["sy"]
                jump = math.hypot(x - px, y - py)
                if jump > LANDMARK_JUMP_LIMIT:
                    self._landmark_streak[name] = 0
                    continue
                a = LANDMARK_SMOOTH_ALPHA
                x = a*x + (1.0-a)*px
                y = a*y + (1.0-a)*py
            self._landmark_streak[name] = self._landmark_streak.get(name, 0) + 1
            new_obj = dict(obj)
            new_obj["sx"] = clamp(x, 0.0, 1.0)
            new_obj["sy"] = clamp(y, 0.0, 1.0)
            self._landmark_state[name] = new_obj
            seen.add(name)
            if self._landmark_streak[name] >= LANDMARK_CONFIRM_FRAMES:
                filtered[name] = new_obj
        for name in list(self._landmark_streak.keys()):
            if name not in seen:
                self._landmark_streak[name] = 0
        return filtered

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
            self.last_quality = 0.0
            self.last_coverage = 0.0
            self.quality_lbl.text = "SEM CORPO"
            self.quality_lbl.color = YELLOW
            self.detail_lbl.text = f"ML Kit {data.get('inferenceMs', 0)} ms"
            return

        raw_landmarks = data.get("landmarks") or {}
        landmarks = self._filter_landmarks(raw_landmarks)
        quality, coverage = pose_quality(landmarks)
        self.last_quality = float(quality)
        self.last_coverage = float(coverage)
        values = derive_pose_values(landmarks, self.camera_preview_rotation)
        data["landmarks_filtered"] = landmarks

        now = time.monotonic()
        dt = clamp(now - self.last_metrics_tick, 0.0, 0.4)
        self.last_metrics_tick = now
        self.last_valid_pose_time = now
        if values.get("trunk") is not None and values.get("neck") is not None:
            self._accumulate(values, dt)
        else:
            self.invalid_time += dt
        self.last_values = values

        valid = quality >= 55.0 and len(landmarks) >= 6
        if self.overlay:
            self.overlay.set_image_rect(*self._preview_image_rect())
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

        ire_now = int(v.get("ire", 0) or 0)
        if not self.peak_values or ire_now >= self.max_ire:
            self.peak_values = dict(v)
            self.peak_at = datetime.now().isoformat(timespec="seconds")

        self.max_ire = max(self.max_ire, ire_now)
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
        self.metrics["rula"].set(f"{v.get('rula', 0)}/7")
        self.metrics["reba"].set(f"{v.get('reba', 0)}/15")
        self.metrics["tempo"].set(fmt_seconds(self.total_time))
        self.metrics["exp"].set(f"{(100*self.risk_time/self.total_time if self.total_time else 0):.1f}%")
        self.metrics["posefps"].set(f"{pose_fps:.1f}")
        self.metrics["trunk"].set(fmt_angle(v.get("trunk")))
        self.metrics["neck"].set(fmt_angle(v.get("neck")))
        self.metrics["arm"].set(f"{fmt_angle(v.get('shoulder_r'))} / {fmt_angle(v.get('shoulder_l'))}")
        self.metrics["knee"].set(f"{fmt_angle(v.get('knee_r'))} / {fmt_angle(v.get('knee_l'))}")

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
            self.cycle_records.append({
                "ciclo": self.cycle_count,
                "duracao_s": round(duration, 2),
                "fechado_em": datetime.now().isoformat(timespec="seconds"),
            })
            self._save_assessment_json()
            self.status_text = f"Ciclo {self.cycle_count} fechado · {fmt_seconds(duration)}."

    def _assessment_dir(self):
        app = App.get_running_app()
        if self.assessment_dir is None:
            base = Path(getattr(app, "user_data_dir", str(BASE_DIR))) / "avaliacoes_nr17"
            self.assessment_dir = base / self.assessment_id
            self.assessment_dir.mkdir(parents=True, exist_ok=True)
        return self.assessment_dir

    def _evidence_dir(self):
        base = self._assessment_dir() / "evidencias"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _assessment_snapshot(self):
        v = dict(self.last_values or {})
        total = float(self.total_time or 0)
        return {
            "assessment_id": self.assessment_id,
            "inicio": self.assessment_started_at.isoformat(timespec="seconds"),
            "atualizado_em": datetime.now().isoformat(timespec="seconds"),
            "setor": self.in_setor.text.strip(),
            "posto": self.in_posto.text.strip(),
            "colaborador": self.in_colab.text.strip(),
            "tempo_valido_s": round(total, 2),
            "tempo_invalido_s": round(float(self.invalid_time), 2),
            "exposicao_total_pct": round(safe_pct(self.risk_time, total), 2),
            "exposicao_tronco_pct": round(safe_pct(self.trunk_time, total), 2),
            "exposicao_pescoco_pct": round(safe_pct(self.neck_time, total), 2),
            "exposicao_braco_pct": round(safe_pct(self.arm_time, total), 2),
            "exposicao_joelho_pct": round(safe_pct(self.knee_time, total), 2),
            "eventos": int(self.events),
            "ciclos": list(self.cycle_records),
            "max_ire": int(self.max_ire),
            "max_rula": int(self.max_rula),
            "max_reba": int(self.max_reba),
            "ultimo": v,
            "pico": dict(self.peak_values or v),
            "pico_em": self.peak_at,
            "evidencias": list(self.evidence_records),
            "config": {
                "camera_preview_rotation": self.camera_preview_rotation,
                "pose_rotation": self.pose_rotation,
                "mirror_x": self.mirror_x,
                "mirror_y": self.mirror_y,
                "pose_min_confidence": MIN_CONFIDENCE,
                "angle_min_confidence": ANGLE_MIN_CONFIDENCE,
                "confirm_frames": LANDMARK_CONFIRM_FRAMES,
                "jump_limit": LANDMARK_JUMP_LIMIT,
            },
        }

    def _save_assessment_json(self):
        try:
            path = self._assessment_dir() / "dados_avaliacao.json"
            path.write_text(json.dumps(self._assessment_snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
            return path
        except Exception:
            return None

    def _refresh_evidence_count(self):
        if getattr(self, "evidence_count_lbl", None):
            n = len(self.evidence_records)
            self.evidence_count_lbl.text = (
                f"EVIDÊNCIAS: {n}  ·  Cada toque em FOTO + adiciona uma nova imagem ao PDF."
            )

    def remove_last_evidence(self, *_):
        if not self.evidence_records:
            self.status_text = "Não há evidências para remover."
            return
        record = self.evidence_records.pop()
        try:
            path = Path(record.get("arquivo", ""))
            if path.exists():
                path.unlink()
        except Exception:
            pass
        self._refresh_evidence_count()
        self._save_assessment_json()
        self.status_text = f"Última evidência removida. Restam {len(self.evidence_records)}."

    def _capture_evidence_file(self):
        """Captura o preview composto exatamente como ele aparece na tela."""
        if not self.camera or self.camera.texture is None or not self.preview_area:
            raise RuntimeError("Sem imagem disponível para evidência.")

        idx = len(self.evidence_records) + 1
        captured_at = datetime.now()
        temp_path = self._evidence_dir() / f"_preview_{idx:03d}.png"

        self._fit_preview()
        if self.overlay:
            self.overlay.redraw()

        try:
            # A câmera e o esqueleto são rasterizados juntos pelo Kivy.
            # Dessa forma não existe uma segunda rotação/espelhamento no PDF.
            self.preview_area.export_to_png(str(temp_path))
            if not temp_path.exists():
                raise RuntimeError("Kivy não gerou a captura do preview.")
            with Image.open(temp_path) as raw:
                img = raw.convert("RGB")
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass

        values = dict(self.last_values or {})
        footer_h = max(118, int(img.height * 0.15))
        canvas = Image.new("RGB", (img.width, img.height + footer_h), (8, 20, 34))
        canvas.paste(img, (0, 0))
        draw = ImageDraw.Draw(canvas)
        f_big = load_report_font(max(18, img.width // 48), bold=True)
        f_small = load_report_font(max(14, img.width // 68), bold=False)
        f_tiny = load_report_font(max(12, img.width // 82), bold=False)
        y0 = img.height + 14
        draw.text((20, y0),
            f"NR-17  |  IRE {values.get('ire',0)}/100  |  RULA {values.get('rula',0)}/7  |  REBA {values.get('reba',0)}/15",
            font=f_big, fill="white")
        draw.text((20, y0 + 36),
            f"Tronco {fmt_angle(values.get('trunk'))}  |  Pescoco {fmt_angle(values.get('neck'))}  |  "
            f"Braco D/E {fmt_angle(values.get('shoulder_r'))}/{fmt_angle(values.get('shoulder_l'))}",
            font=f_small, fill=(205, 225, 238))
        draw.text((20, y0 + 68),
            f"{captured_at.strftime('%d/%m/%Y %H:%M:%S')}  |  Setor: {self.in_setor.text or '-'}  |  "
            f"Posto: {self.in_posto.text or '-'}  |  Qualidade: {self.last_quality:.0f}%",
            font=f_tiny, fill=(154, 184, 204))

        path = self._evidence_dir() / f"evidencia_{idx:03d}.jpg"
        canvas.save(str(path), "JPEG", quality=95, subsampling=0)
        record = {
            "numero": idx, "arquivo": str(path),
            "capturada_em": captured_at.isoformat(timespec="seconds"),
            "ire": int(values.get("ire", 0) or 0),
            "rula": int(values.get("rula", 0) or 0),
            "reba": int(values.get("reba", 0) or 0),
            "trunk": values.get("trunk"), "neck": values.get("neck"),
            "shoulder_r": values.get("shoulder_r"), "shoulder_l": values.get("shoulder_l"),
            "elbow_r": values.get("elbow_r"), "elbow_l": values.get("elbow_l"),
            "knee_r": values.get("knee_r"), "knee_l": values.get("knee_l"),
            "quality": round(float(self.last_quality or 0), 1),
            "coverage": round(float(self.last_coverage or 0), 1),
            "camera_preview_rotation": int(self.camera_preview_rotation),
            "pose_rotation": int(self.pose_rotation),
            "mirror_x": bool(self.mirror_x), "mirror_y": bool(self.mirror_y),
        }
        self.evidence_records.append(record)
        self._refresh_evidence_count()
        self._save_assessment_json()
        return path, record

    def capture_evidence(self, *_):
        try:
            path, _record = self._capture_evidence_file()
            self.status_text = (
                f"Foto {len(self.evidence_records)} adicionada. "
                f"O PDF incluirá todas as {len(self.evidence_records)} evidências."
            )
        except Exception as exc:
            self.status_text = f"Erro ao salvar evidência: {exc}"

    # --------------------------- PDF ---------------------------
    def _risk_level_report(self, ire):
        ire = int(ire or 0)
        if ire >= 70:
            return "CRITICO", (214, 52, 71), "Intervencao prioritaria e validacao ergonomica recomendadas."
        if ire >= 50:
            return "ALTO", (238, 117, 37), "Ha sinais relevantes de sobrecarga postural."
        if ire >= 30:
            return "ATENCAO", (226, 169, 45), "Acompanhar a exposicao e revisar oportunidades de melhoria."
        return "BAIXO", (46, 160, 104), "Baixa exposicao visual no periodo analisado."

    def _pdf_metric_card(self, d, box, label, value, accent, fonts):
        x1, y1, x2, y2 = box
        d.rounded_rectangle(box, radius=18, fill=(247, 250, 252), outline=(216, 226, 234), width=2)
        d.rectangle((x1, y1, x1+8, y2), fill=accent)
        d.text((x1+24, y1+20), label, font=fonts["small_b"], fill=(92, 109, 124))
        d.text((x1+24, y1+58), str(value), font=fonts["metric"], fill=(18, 50, 78))

    def _pdf_exposure_bar(self, d, y, label, pct, fonts):
        pct = float(pct or 0)
        x_label, x_bar, bar_w, bar_h = 75, 330, 805, 28
        d.text((x_label, y-4), label, font=fonts["body_b"], fill=(36, 51, 64))
        d.rounded_rectangle((x_bar, y, x_bar+bar_w, y+bar_h), radius=14, fill=(230, 236, 241))
        fill_w = bar_w * clamp(pct/100.0, 0, 1)
        col = (214, 52, 71) if pct >= 70 else (238, 117, 37) if pct >= 40 else (226, 169, 45) if pct >= 20 else (35, 158, 183)
        if fill_w > 1:
            d.rounded_rectangle((x_bar, y, x_bar+fill_w, y+bar_h), radius=14, fill=col)
        pct_txt = f"{pct:.1f}%"
        try:
            bb = d.textbbox((0, 0), pct_txt, font=fonts["body_b"]); tw = bb[2]-bb[0]
        except Exception:
            tw = 70
        d.text((1140-tw, y-4), pct_txt, font=fonts["body_b"], fill=(36, 51, 64))

    def _pdf_summary_page(self, snapshot):
        W, H = 1240, 1754
        page = Image.new("RGB", (W, H), (246, 249, 251))
        d = ImageDraw.Draw(page)
        navy=(10,38,64); navy2=(18,62,96); cyan=(35,158,183); dark=(31,45,58)
        gray=(96,113,128); line=(215,225,233); white=(255,255,255)
        fonts={
            "title":load_report_font(38,True), "subtitle":load_report_font(22),
            "section":load_report_font(25,True), "body":load_report_font(21),
            "body_b":load_report_font(21,True), "small":load_report_font(17),
            "small_b":load_report_font(17,True), "metric":load_report_font(38,True),
            "risk":load_report_font(30,True),
        }
        d.rectangle((0,0,W,205),fill=navy); d.rectangle((0,198,W,205),fill=cyan)
        d.text((62,45),"NR-17 | RELATORIO ERGONOMICO POR VISAO",font=fonts["title"],fill=white)
        d.text((65,108),"Triagem postural assistida por visao computacional",font=fonts["subtitle"],fill=(189,215,230))
        d.text((855,113),f"Avaliacao: {snapshot.get('assessment_id','-')}",font=fonts["small_b"],fill=(189,215,230))

        y=238
        d.rounded_rectangle((58,y,1182,y+178),radius=20,fill=white,outline=line,width=2)
        d.text((82,y+18),"IDENTIFICACAO",font=fonts["section"],fill=navy)
        fields=[
            ("Setor",snapshot.get("setor") or "-"),("Operacao / Posto",snapshot.get("posto") or "-"),("Colaborador",snapshot.get("colaborador") or "-"),
            ("Inicio",str(snapshot.get("inicio") or "-").replace("T"," ")),("Tempo valido",fmt_seconds(snapshot.get("tempo_valido_s",0))),("Evidencias",str(len(snapshot.get("evidencias",[])))),
        ]
        xs=[82,455,825]
        for i,(lab,val) in enumerate(fields):
            row=0 if i<3 else 1; col=i if i<3 else i-3
            x=xs[col]; yy=y+58+row*55
            d.text((x,yy),str(lab).upper(),font=fonts["small_b"],fill=gray)
            d.text((x,yy+24),str(val),font=fonts["body"],fill=dark)

        y=448; d.text((62,y),"RESUMO EXECUTIVO DE RISCO",font=fonts["section"],fill=navy); y+=45
        card_w,gap=258,20
        metrics=[("IRE MAX",f"{snapshot.get('max_ire',0)}/100",cyan),("RULA MAX",f"{snapshot.get('max_rula',0)}/7",(87,111,169)),("REBA MAX",f"{snapshot.get('max_reba',0)}/15",(117,88,165)),("EXPOSICAO",f"{snapshot.get('exposicao_total_pct',0):.1f}%",navy2)]
        for i,item in enumerate(metrics):
            x=62+i*(card_w+gap); self._pdf_metric_card(d,(x,y,x+card_w,y+130),*item,fonts)
        level,level_color,level_desc=self._risk_level_report(snapshot.get("max_ire",0)); y+=155
        d.rounded_rectangle((62,y,1178,y+92),radius=20,fill=white,outline=level_color,width=3)
        d.rounded_rectangle((82,y+18,340,y+72),radius=14,fill=level_color)
        d.text((103,y+31),f"RISCO {level}",font=fonts["risk"],fill=white)
        d.text((370,y+23),level_desc,font=fonts["body_b"],fill=dark)
        d.text((370,y+54),"Resultado de triagem visual - validar no contexto da AEP/AET.",font=fonts["small"],fill=gray)

        y+=130; d.text((62,y),"EXPOSICAO CORPORAL NO PERIODO",font=fonts["section"],fill=navy); y+=50
        for lab,pct in [("Tronco",snapshot.get("exposicao_tronco_pct",0)),("Pescoco",snapshot.get("exposicao_pescoco_pct",0)),("Braco elevado",snapshot.get("exposicao_braco_pct",0)),("Joelho / flexao",snapshot.get("exposicao_joelho_pct",0))]:
            self._pdf_exposure_bar(d,y,lab,pct,fonts); y+=58

        y+=12; peak=snapshot.get("pico") or snapshot.get("ultimo") or {}
        d.text((62,y),"POSTURA DE MAIOR IRE",font=fonts["section"],fill=navy)
        if snapshot.get("pico_em"):
            d.text((400,y+4),str(snapshot.get("pico_em")).replace("T"," "),font=fonts["small"],fill=gray)
        y+=48; d.rounded_rectangle((62,y,1178,y+238),radius=20,fill=white,outline=line,width=2)
        peak_items=[
            ("TRONCO",fmt_angle(peak.get("trunk")),f"Limite IRE: {TRUNK_LIMIT:.0f}°"),
            ("PESCOCO",fmt_angle(peak.get("neck")),f"Limite IRE: {NECK_LIMIT:.0f}°"),
            ("BRACO D / E",f"{fmt_angle(peak.get('shoulder_r'))} / {fmt_angle(peak.get('shoulder_l'))}",f"Limite IRE: {ARM_LIMIT:.0f}°"),
            ("JOELHO D / E",f"{fmt_angle(peak.get('knee_r'))} / {fmt_angle(peak.get('knee_l'))}",f"Critico abaixo de {KNEE_LIMIT:.0f}°"),
        ]
        cell_w=538; cell_h=92
        for i,(lab,val,note) in enumerate(peak_items):
            col=i%2; row=i//2; x=84+col*548; yy=y+24+row*96
            if col: d.line((620,y+20,620,y+205),fill=line,width=2)
            if row and col==0: d.line((82,y+116,1158,y+116),fill=line,width=2)
            d.text((x,yy),lab,font=fonts["small_b"],fill=gray)
            d.text((x+185,yy-4),val,font=fonts["metric"],fill=navy2)
            d.text((x,yy+48),note,font=fonts["small"],fill=gray)
        d.text((84,y+208),f"Eventos de risco: {snapshot.get('eventos',0)}   |   Ciclos fechados: {len(snapshot.get('ciclos',[]))}",font=fonts["small_b"],fill=gray)

        y+=270; d.text((62,y),f"EVIDENCIAS REGISTRADAS  |  {len(snapshot.get('evidencias',[]))}",font=fonts["section"],fill=navy); y+=42
        records=list(snapshot.get("evidencias",[]))[:3]
        if records:
            thumb_w,thumb_h,gap=350,155,18
            for i,rec in enumerate(records):
                x=62+i*(thumb_w+gap); d.rounded_rectangle((x,y,x+thumb_w,y+thumb_h),radius=15,fill=white,outline=line,width=2)
                p=Path(rec.get("arquivo",""))
                if p.exists():
                    try:
                        with Image.open(p) as ev:
                            ev=ev.convert("RGB"); res=Image.Resampling.LANCZOS if hasattr(Image,"Resampling") else Image.LANCZOS; ev.thumbnail((thumb_w-16,thumb_h-38),res)
                            page.paste(ev,(x+(thumb_w-ev.width)//2,y+8))
                    except Exception: pass
                d.text((x+10,y+thumb_h-27),f"Foto {rec.get('numero',i+1)}  |  IRE {rec.get('ire',0)}",font=fonts["small_b"],fill=dark)
            if len(snapshot.get("evidencias",[]))>3:
                d.text((62,y+thumb_h+10),f"+ {len(snapshot.get('evidencias',[]))-3} evidencias nas paginas seguintes",font=fonts["small"],fill=gray)
        else:
            d.text((75,y+25),"Nenhuma evidencia fotografica registrada.",font=fonts["body"],fill=gray)

        d.line((62,1680,1178,1680),fill=line,width=2)
        d.text((62,1695),"NR-17 Visao 0.1.5  |  Apoio a AEP/AET - nao substitui avaliacao ergonomica profissional.",font=fonts["small"],fill=gray)
        d.text((925,1695),datetime.now().strftime("%d/%m/%Y %H:%M"),font=fonts["small"],fill=gray)
        return page

    def _pdf_evidence_page(self, record, page_num, total_pages):
        W,H=1240,1754; page=Image.new("RGB",(W,H),(246,249,251)); d=ImageDraw.Draw(page)
        navy=(10,38,64); cyan=(35,158,183); dark=(31,45,58); gray=(96,113,128); line=(215,225,233); white=(255,255,255)
        fonts={"title":load_report_font(38,True),"section":load_report_font(24,True),"body":load_report_font(21),"body_b":load_report_font(21,True),"small":load_report_font(17),"small_b":load_report_font(17,True),"metric":load_report_font(34,True)}
        d.rectangle((0,0,W,155),fill=navy); d.rectangle((0,148,W,155),fill=cyan)
        d.text((62,42),f"EVIDENCIA {int(record.get('numero',page_num)):02d}",font=fonts["title"],fill=white)
        d.text((62,102),str(record.get("capturada_em","")).replace("T"," "),font=fonts["small"],fill=(189,215,230))
        d.text((980,70),f"Pagina {page_num+1}/{total_pages}",font=fonts["small_b"],fill=white)
        top=190; d.rounded_rectangle((58,top,1182,1125),radius=20,fill=white,outline=line,width=2)
        p=Path(record.get("arquivo",""))
        if p.exists():
            try:
                with Image.open(p) as ev:
                    ev=ev.convert("RGB"); res=Image.Resampling.LANCZOS if hasattr(Image,"Resampling") else Image.LANCZOS; ev.thumbnail((1084,895),res)
                    page.paste(ev,((W-ev.width)//2,top+(915-ev.height)//2))
            except Exception:
                d.text((95,top+60),"Nao foi possivel carregar a imagem da evidencia.",font=fonts["body"],fill=gray)
        else:
            d.text((95,top+60),"Imagem da evidencia nao encontrada.",font=fonts["body"],fill=gray)
        y=1160; d.text((62,y),"INDICADORES DA CAPTURA",font=fonts["section"],fill=navy); y+=42
        cards=[("IRE",f"{record.get('ire',0)}/100",cyan),("RULA",f"{record.get('rula',0)}/7",(87,111,169)),("REBA",f"{record.get('reba',0)}/15",(117,88,165)),("QUALIDADE",f"{float(record.get('quality',0) or 0):.0f}%",navy)]
        cw,gap=258,20
        for i,item in enumerate(cards):
            x=62+i*(cw+gap); self._pdf_metric_card(d,(x,y,x+cw,y+118),*item,fonts)
        y+=150; d.rounded_rectangle((62,y,1178,y+220),radius=20,fill=white,outline=line,width=2); d.text((84,y+18),"ANGULOS E CONTEXTO",font=fonts["section"],fill=navy)
        rows=[("Tronco",fmt_angle(record.get("trunk")),"Pescoco",fmt_angle(record.get("neck"))),("Braco D / E",f"{fmt_angle(record.get('shoulder_r'))} / {fmt_angle(record.get('shoulder_l'))}","Joelho D / E",f"{fmt_angle(record.get('knee_r'))} / {fmt_angle(record.get('knee_l'))}"),("Cobertura",f"{float(record.get('coverage',0) or 0):.0f}%","Calibracao",f"Cam {record.get('camera_preview_rotation','-')}° | Pose {record.get('pose_rotation','-')}°")]
        yy=y+68
        for l1,v1,l2,v2 in rows:
            d.text((85,yy),f"{l1}:",font=fonts["body_b"],fill=gray); d.text((245,yy),str(v1),font=fonts["body"],fill=dark); d.text((640,yy),f"{l2}:",font=fonts["body_b"],fill=gray); d.text((800,yy),str(v2),font=fonts["body"],fill=dark); yy+=46
        d.line((62,1680,1178,1680),fill=line,width=2); d.text((62,1695),"Evidencia capturada do preview composto - imagem e esqueleto preservam a mesma orientacao.",font=fonts["small"],fill=gray)
        return page

    def _export_report_android(self, pdf_path):
        if platform != "android" or not self.pose_analyzer:
            return None
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            result = str(self.pose_analyzer.exportFileToDownloads(activity, str(pdf_path), pdf_path.name) or "")
            if result.startswith("ERROR:"):
                return None
            return result or None
        except Exception:
            return None

    def generate_report(self, *_):
        try:
            if not self.evidence_records and self.camera and self.camera.texture is not None:
                try:
                    self._capture_evidence_file()
                except Exception:
                    pass
            snapshot = self._assessment_snapshot()
            self._save_assessment_json()
            pages = [self._pdf_summary_page(snapshot)]
            total_pages = 1 + len(self.evidence_records)
            for idx, record in enumerate(self.evidence_records, start=1):
                pages.append(self._pdf_evidence_page(record, idx, total_pages))
            pdf_name = f"relatorio_NR17_{self.assessment_id}.pdf"
            pdf_path = self._assessment_dir() / pdf_name
            pages[0].save(str(pdf_path), "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
            exported = self._export_report_android(pdf_path)
            self.last_exported_report = exported or str(pdf_path)
            if exported and exported.startswith("content://"):
                self.status_text = f"PDF gerado e salvo em Downloads/NR17: {pdf_name}"
            else:
                self.status_text = f"PDF gerado: {pdf_path.name}"
        except Exception as exc:
            self.status_text = f"Erro ao gerar PDF: {exc}"

    def reset_measurement(self, *_):
        self._save_assessment_json()
        self.total_time = self.invalid_time = self.risk_time = 0.0
        self.trunk_time = self.neck_time = self.arm_time = self.knee_time = 0.0
        self.events = 0; self.was_risk = False
        self.max_ire = self.max_rula = self.max_reba = 0
        self.peak_values = {}; self.peak_at = None
        self.last_quality = 0.0; self.last_coverage = 0.0
        self.cycle_active = False; self.cycle_count = 0; self.cycle_records = []
        self.last_values = None; self.last_pose_data = None; self.last_metrics_tick = time.monotonic()
        self.assessment_started_at = datetime.now()
        self.assessment_id = self.assessment_started_at.strftime("%Y%m%d_%H%M%S")
        self.assessment_dir = None; self.evidence_records = []; self.last_exported_report = None
        self._landmark_state = {}; self._landmark_streak = {}
        self._refresh_evidence_count()
        self.status_text = "Nova avaliação iniciada."
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
