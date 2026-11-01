#!/usr/bin/env python3
"""
Blueprint Agent — Glamour Upholstery
Generates dimensioned floor plan + elevation SVG drawings from room measurements.

CLI:  python blueprint.py boudreau.json [--pdf]
      python blueprint.py --demo [--pdf]
Flask: from blueprint import render_blueprint_html
"""

import json
import math
import os
import platform
import subprocess
import sys
from pathlib import Path
from datetime import date


# ── Canvas / style constants ──────────────────────────────────────────────────

FP_W, FP_H   = 820, 600   # floor plan canvas
EL_W, EL_H   = 820, 520   # elevation canvas
MARGIN        = 85         # space around room for dimension labels
DIM_OFF       = 30         # distance dim line sits from object edge
DIM_TICK      = 7
FONT          = "Courier New, Courier, monospace"

C_WALL        = "#1a1a1a"
C_SOFFIT_FILL = "#d8d8d8"
C_SOFFIT_STK  = "#555"
C_TRACK       = "#1a3f6f"
C_BRACKET     = "#1a3f6f"
C_CURTAIN     = "#c5cfd8"
C_DIM         = "#555"
C_WINDOW_FILL = "#d0eaf7"
C_WINDOW_STK  = "#6aaed6"
C_BG          = "#fafafa"


# ── Unit helpers ──────────────────────────────────────────────────────────────

def to_in(val):
    """Accept inches (int/float) or 'F-I' string like '12-6' → 150."""
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip().replace("'", "-").replace('"', "")
    if "-" in val:
        parts = val.split("-")
        return float(parts[0]) * 12 + float(parts[1]) if len(parts) == 2 else float(parts[0])
    return float(val)


def fmt(inches):
    """Format inches → 12'-6" style."""
    inches = round(inches, 2)
    ft = int(inches) // 12
    rem = round(inches % 12, 2)
    if ft and rem:
        return f"{ft}'-{rem:.4g}\""
    if ft:
        return f"{ft}'-0\""
    return f'{rem:.4g}"'


# ── SVG primitives ────────────────────────────────────────────────────────────

DEFS = """
  <defs>
    <marker id="as" markerWidth="7" markerHeight="7" refX="3.5" refY="2"
            orient="auto" markerUnits="strokeWidth">
      <path d="M7,0 L0,2 L7,4 Z" fill="#555"/>
    </marker>
    <marker id="ae" markerWidth="7" markerHeight="7" refX="3.5" refY="2"
            orient="auto-start-reverse" markerUnits="strokeWidth">
      <path d="M7,0 L0,2 L7,4 Z" fill="#555"/>
    </marker>
    <pattern id="hatch" patternUnits="userSpaceOnUse" width="8" height="8"
             patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="8" stroke="#bbb" stroke-width="1.2"/>
    </pattern>
  </defs>"""


def svg_open(w, h, title=""):
    label = f'<title>{title}</title>' if title else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">{label}{DEFS}'
            f'<rect width="{w}" height="{h}" fill="{C_BG}"/>')


def svg_close():
    return "</svg>"


def dim_h(x1, x2, y, label, above=True):
    """Horizontal dimension line."""
    t = DIM_TICK
    ty = y - 8 if above else y + 14
    return (
        f'<line x1="{x1}" y1="{y-t}" x2="{x1}" y2="{y+t}" stroke="{C_DIM}" stroke-width="0.8"/>'
        f'<line x1="{x2}" y1="{y-t}" x2="{x2}" y2="{y+t}" stroke="{C_DIM}" stroke-width="0.8"/>'
        f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{C_DIM}" stroke-width="0.8" '
        f'marker-start="url(#as)" marker-end="url(#ae)"/>'
        f'<text x="{(x1+x2)/2:.1f}" y="{ty}" text-anchor="middle" '
        f'font-family="{FONT}" font-size="10" fill="{C_DIM}">{label}</text>'
    )


def dim_v(y1, y2, x, label, right=True):
    """Vertical dimension line."""
    t = DIM_TICK
    mid = (y1 + y2) / 2
    lx = x + 12 if right else x - 6
    anc = "start" if right else "end"
    return (
        f'<line x1="{x-t}" y1="{y1}" x2="{x+t}" y2="{y1}" stroke="{C_DIM}" stroke-width="0.8"/>'
        f'<line x1="{x-t}" y1="{y2}" x2="{x+t}" y2="{y2}" stroke="{C_DIM}" stroke-width="0.8"/>'
        f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="{C_DIM}" stroke-width="0.8" '
        f'marker-start="url(#as)" marker-end="url(#ae)"/>'
        f'<text x="{lx}" y="{mid+4:.1f}" text-anchor="{anc}" '
        f'font-family="{FONT}" font-size="10" fill="{C_DIM}">{label}</text>'
    )


def label_box(x, y, text, small=False):
    size = 9 if small else 11
    return (f'<text x="{x}" y="{y}" text-anchor="middle" font-family="{FONT}" '
            f'font-size="{size}" fill="{C_WALL}">{text}</text>')


# ── Floor Plan ────────────────────────────────────────────────────────────────

def floor_plan_svg(m):
    """
    Top-down view: room outline, soffit footprint, track line, brackets, windows.
    m = normalised measurement dict (all values in inches).
    """
    rw = m["room_width"]
    rl = m["room_length"]

    avail_w = FP_W - 2 * MARGIN
    avail_h = FP_H - 2 * MARGIN
    scale   = min(avail_w / rw, avail_h / rl)

    # Pixel room box
    rx = MARGIN
    ry = MARGIN
    rW = rw * scale
    rH = rl * scale

    svg  = svg_open(FP_W, FP_H, "Floor Plan")
    svg += f'\n  <!-- floor plan label -->'
    svg += (f'\n  <text x="{FP_W/2:.0f}" y="22" text-anchor="middle" font-family="{FONT}" '
            f'font-size="13" font-weight="bold" fill="{C_WALL}">FLOOR PLAN — TOP VIEW</text>')

    # Room outline
    svg += (f'\n  <rect x="{rx}" y="{ry}" width="{rW:.2f}" height="{rH:.2f}" '
            f'fill="white" stroke="{C_WALL}" stroke-width="2.5"/>')

    # Soffit footprint (the zone the soffit occupies on the floor, viewed from above)
    wall   = m.get("soffit_wall", "top")
    s_len  = m["soffit_length"] * scale
    s_dep  = m["soffit_depth"] * scale
    s_off  = m.get("soffit_offset", 0) * scale

    if wall == "top":
        sx, sy, sW, sH = rx + s_off, ry, s_len, s_dep
    elif wall == "bottom":
        sx, sy, sW, sH = rx + s_off, ry + rH - s_dep, s_len, s_dep
    elif wall == "left":
        sx, sy, sW, sH = rx, ry + s_off, s_dep, s_len
    else:  # right
        sx, sy, sW, sH = rx + rW - s_dep, ry + s_off, s_dep, s_len

    svg += (f'\n  <rect x="{sx:.2f}" y="{sy:.2f}" width="{sW:.2f}" height="{sH:.2f}" '
            f'fill="url(#hatch)" stroke="{C_SOFFIT_STK}" stroke-width="1.2"/>')
    svg += label_box(sx + sW/2, sy + sH/2 + 4, "SOFFIT", small=True)

    # Track line (on the soffit, parallel to wall)
    t_len = m["track_length"] * scale
    t_off = m.get("track_offset", 0) * scale   # offset along soffit length
    t_ins = m.get("track_inset", 0) * scale     # inset from face of soffit

    if wall == "top":
        tx1 = sx + t_off
        tx2 = tx1 + t_len
        ty1 = ty2 = sy + s_dep - t_ins
    elif wall == "bottom":
        tx1 = sx + t_off
        tx2 = tx1 + t_len
        ty1 = ty2 = sy + t_ins
    elif wall == "left":
        tx1 = ty1 = sx + s_dep - t_ins
        ty1 = sy + t_off
        ty2 = ty1 + t_len
        tx2 = tx1
    else:
        tx1 = tx2 = sx + t_ins
        ty1 = sy + t_off
        ty2 = ty1 + t_len

    svg += (f'\n  <line x1="{tx1:.2f}" y1="{ty1:.2f}" x2="{tx2:.2f}" y2="{ty2:.2f}" '
            f'stroke="{C_TRACK}" stroke-width="3" stroke-linecap="round"/>')

    # Brackets (dots on track)
    br_sp  = m.get("bracket_spacing", 24) * scale
    n_br   = max(2, int(m["track_length"] / m.get("bracket_spacing", 24)) + 1)
    for i in range(n_br):
        frac = i / max(n_br - 1, 1)
        if wall in ("top", "bottom"):
            bx = tx1 + frac * (tx2 - tx1)
            by = ty1
        else:
            bx = tx1
            by = ty1 + frac * (ty2 - ty1)
        svg += (f'\n  <circle cx="{bx:.2f}" cy="{by:.2f}" r="3.5" '
                f'fill="{C_BRACKET}" stroke="white" stroke-width="1"/>')

    # Windows
    for win in m.get("windows", []):
        wwall  = win.get("wall", "top")
        woff   = win.get("offset", 0) * scale
        wwidth = win.get("width", 36) * scale
        wthick = 6
        if wwall == "top":
            wx, wy, wW, wH = rx + woff, ry, wwidth, wthick
        elif wwall == "bottom":
            wx, wy, wW, wH = rx + woff, ry + rH - wthick, wwidth, wthick
        elif wwall == "left":
            wx, wy, wW, wH = rx, ry + woff, wthick, wwidth
        else:
            wx, wy, wW, wH = rx + rW - wthick, ry + woff, wthick, wwidth
        svg += (f'\n  <rect x="{wx:.2f}" y="{wy:.2f}" width="{wW:.2f}" height="{wH:.2f}" '
                f'fill="{C_WINDOW_FILL}" stroke="{C_WINDOW_STK}" stroke-width="1.5"/>')

    # Dimension lines
    # Bottom: room width
    svg += "\n  " + dim_h(rx, rx + rW, ry + rH + DIM_OFF, fmt(rw), above=False)
    # Right: room length
    svg += "\n  " + dim_v(ry, ry + rH, rx + rW + DIM_OFF, fmt(rl), right=True)
    # Soffit width (along its length axis)
    if wall in ("top", "bottom"):
        svg += "\n  " + dim_h(sx, sx + sW, sy - DIM_OFF if wall == "top" else sy + sH + DIM_OFF,
                               fmt(m["soffit_length"]), above=(wall == "top"))
    # Track length
    if wall in ("top", "bottom"):
        svg += "\n  " + dim_h(tx1, tx2, ty1 + DIM_OFF * 1.3, fmt(m["track_length"]), above=False)

    # Compass rose (top-right corner)
    cx, cy, cr = FP_W - 32, 32, 14
    svg += (f'\n  <circle cx="{cx}" cy="{cy}" r="{cr}" fill="none" stroke="#999" stroke-width="1"/>'
            f'\n  <line x1="{cx}" y1="{cy-cr}" x2="{cx}" y2="{cy+cr}" stroke="#999" stroke-width="1"/>'
            f'\n  <line x1="{cx-cr}" y1="{cy}" x2="{cx+cr}" y2="{cy}" stroke="#999" stroke-width="1"/>'
            f'\n  <text x="{cx}" y="{cy-cr-3}" text-anchor="middle" font-size="9" '
            f'font-family="{FONT}" fill="#777">N</text>')

    svg += f'\n  <text x="4" y="{FP_H-4}" font-size="8" font-family="{FONT}" fill="#aaa">scale approx</text>'
    svg += "\n" + svg_close()
    return svg


# ── Elevation ─────────────────────────────────────────────────────────────────

def elevation_svg(m):
    """
    Front-facing elevation of the soffit wall showing:
    ceiling, soffit box, brackets, track, curtain panels, floor.
    """
    rw = m["room_width"] if m.get("soffit_wall") in ("top", "bottom", None) else m["room_length"]
    rh = m["ceiling_height"]

    avail_w = EL_W - 2 * MARGIN
    avail_h = EL_H - 2 * MARGIN - 20
    scale   = min(avail_w / rw, avail_h / rh)

    # Pixel origin (bottom-left of wall = floor level)
    ox = MARGIN
    oy = EL_H - MARGIN

    def px(x_in):   return ox + x_in * scale
    def py(y_in):   return oy - y_in * scale   # y increases upward for inches

    wall_w = rw * scale
    wall_h = rh * scale

    # Soffit dimensions
    s_len  = m["soffit_length"]
    s_dep  = m["soffit_depth"]
    s_off  = m.get("soffit_offset", 0)
    s_bot  = m["soffit_bottom_from_floor"]   # bottom of soffit from floor

    # Track
    t_len  = m["track_length"]
    t_off  = m.get("track_offset", 0)
    t_ins  = m.get("track_inset", 0)  # inset from face of soffit (downward from soffit face)
    t_from_floor = s_bot - t_ins      # track Y position from floor

    # Curtain
    drop   = m.get("curtain_drop", 0)
    panels = m.get("panel_count", 2)
    br_sp  = m.get("bracket_spacing", 24)

    svg = svg_open(EL_W, EL_H, "Elevation")
    svg += (f'\n  <text x="{EL_W/2:.0f}" y="22" text-anchor="middle" font-family="{FONT}" '
            f'font-size="13" font-weight="bold" fill="{C_WALL}">ELEVATION — SOFFIT WALL</text>')

    # Floor line
    svg += (f'\n  <line x1="{ox}" y1="{py(0)}" x2="{px(rw)}" y2="{py(0)}" '
            f'stroke="{C_WALL}" stroke-width="2.5"/>')
    # Ceiling line
    svg += (f'\n  <line x1="{ox}" y1="{py(rh)}" x2="{px(rw)}" y2="{py(rh)}" '
            f'stroke="{C_WALL}" stroke-width="2.5"/>')
    # Left wall
    svg += (f'\n  <line x1="{ox}" y1="{py(0)}" x2="{ox}" y2="{py(rh)}" '
            f'stroke="{C_WALL}" stroke-width="2.5"/>')
    # Right wall
    svg += (f'\n  <line x1="{px(rw)}" y1="{py(0)}" x2="{px(rw)}" y2="{py(rh)}" '
            f'stroke="{C_WALL}" stroke-width="2.5"/>')

    # Soffit box
    sfx1 = px(s_off)
    sfx2 = px(s_off + s_len)
    sfy_top = py(rh)               # soffit top = ceiling
    sfy_bot = py(s_bot)            # soffit bottom
    svg += (f'\n  <rect x="{sfx1:.2f}" y="{sfy_top:.2f}" '
            f'width="{sfx2-sfx1:.2f}" height="{sfy_bot-sfy_top:.2f}" '
            f'fill="{C_SOFFIT_FILL}" stroke="{C_SOFFIT_STK}" stroke-width="1.5"/>')
    svg += (f'\n  <rect x="{sfx1:.2f}" y="{sfy_top:.2f}" '
            f'width="{sfx2-sfx1:.2f}" height="{sfy_bot-sfy_top:.2f}" '
            f'fill="url(#hatch)" stroke="{C_SOFFIT_STK}" stroke-width="1.5" fill-opacity="0.5"/>')
    svg += label_box((sfx1+sfx2)/2, (sfy_top+sfy_bot)/2 + 4, "SOFFIT", small=True)

    # Track line
    ty = py(t_from_floor)
    tx1 = px(s_off + t_off)
    tx2 = px(s_off + t_off + t_len)
    svg += (f'\n  <line x1="{tx1:.2f}" y1="{ty:.2f}" x2="{tx2:.2f}" y2="{ty:.2f}" '
            f'stroke="{C_TRACK}" stroke-width="4" stroke-linecap="round"/>')

    # Brackets (vertical lines from soffit face to track)
    n_br = max(2, int(t_len / br_sp) + 1)
    for i in range(n_br):
        frac = i / max(n_br - 1, 1)
        bx = tx1 + frac * (tx2 - tx1)
        svg += (f'\n  <line x1="{bx:.2f}" y1="{sfy_bot:.2f}" x2="{bx:.2f}" y2="{ty:.2f}" '
                f'stroke="{C_BRACKET}" stroke-width="2"/>')
        svg += (f'\n  <rect x="{bx-4:.2f}" y="{sfy_bot:.2f}" width="8" height="6" '
                f'fill="{C_BRACKET}"/>')

    # Curtain panels
    if drop and panels:
        panel_w = (t_len / panels) * scale
        curtain_top = ty
        curtain_bot = py(t_from_floor - drop)
        for i in range(panels):
            cpx = tx1 + i * panel_w
            svg += (f'\n  <rect x="{cpx:.2f}" y="{curtain_top:.2f}" '
                    f'width="{panel_w:.2f}" height="{curtain_bot-curtain_top:.2f}" '
                    f'fill="{C_CURTAIN}" stroke="#a0acb5" stroke-width="0.8" fill-opacity="0.7"/>')
            # Fold lines (decorative)
            for fold in [0.33, 0.66]:
                fx = cpx + fold * panel_w
                svg += (f'\n  <line x1="{fx:.2f}" y1="{curtain_top:.2f}" '
                        f'x2="{fx:.2f}" y2="{curtain_bot:.2f}" '
                        f'stroke="#a0acb5" stroke-width="0.6" stroke-dasharray="3,4"/>')

    # ── Dimension lines ───────────────────────────────────────────────────────

    # Ceiling height (right side)
    svg += "\n  " + dim_v(py(0), py(rh), px(rw) + DIM_OFF, fmt(rh), right=True)

    # Soffit depth (right side, interior segment)
    svg += "\n  " + dim_v(py(s_bot), py(rh), px(rw) + DIM_OFF * 2, fmt(rh - s_bot), right=True)

    # Curtain drop (left side)
    if drop:
        svg += "\n  " + dim_v(py(t_from_floor - drop), py(t_from_floor),
                               ox - DIM_OFF, fmt(drop), right=False)

    # Track length (below track)
    svg += "\n  " + dim_h(tx1, tx2, ty + DIM_OFF, fmt(t_len), above=False)

    # Room width (bottom)
    svg += "\n  " + dim_h(ox, px(rw), py(0) + DIM_OFF * 1.5, fmt(rw), above=False)

    svg += f'\n  <text x="4" y="{EL_H-4}" font-size="8" font-family="{FONT}" fill="#aaa">scale approx</text>'
    svg += "\n" + svg_close()
    return svg


# ── 3-D scene ────────────────────────────────────────────────────────────────

def three_scene_html(m):
    """
    Returns the importmap + module script that builds the Three.js 3D room.
    All measurements are passed as a JSON object (in feet) so Python doesn't
    have to know anything about Three.js internals.
    """
    f   = 1 / 12   # inches → feet
    wall = m.get("soffit_wall", "top")

    hw  = HARDWARE.get(m.get("hardware_key", "custom"), HARDWARE["custom"])
    hw_js = {
        "profile":   hw["profile"],
        "profile_r": round(hw.get("profile_r", 0.625) * f, 4),
        "profile_w": round(hw.get("profile_w", 1.75)  * f, 4),
        "profile_h": round(hw.get("profile_h", 0.875) * f, 4),
    }

    data = json.dumps({
        "rw":    round(m["room_width"]               * f, 4),
        "rl":    round(m["room_length"]              * f, 4),
        "rh":    round(m["ceiling_height"]           * f, 4),
        "wall":  wall,
        "s_len": round(m["soffit_length"]            * f, 4),
        "s_dep": round(m["soffit_depth"]             * f, 4),
        "s_bot": round(m["soffit_bottom_from_floor"] * f, 4),
        "s_off": round(m.get("soffit_offset", 0)    * f, 4),
        "t_len": round(m["track_length"]             * f, 4),
        "t_off": round(m.get("track_offset", 0)     * f, 4),
        "t_ins": round(m.get("track_inset", 0)      * f, 4),
        "br_sp": round(m.get("bracket_spacing", 24) * f, 4),
        "drop":  round(m.get("curtain_drop", 0)     * f, 4),
        "panels": int(m.get("panel_count", 0)),
        "windows": [
            {"wall": w.get("wall","top"),
             "offset": round(w.get("offset",0)*f,4),
             "width":  round(w.get("width",36)*f,4)}
            for w in m.get("windows", [])
        ],
        "fabric_url":  m.get("fabric_url")  or None,
        "lining_url":  m.get("lining_url")  or None,
        "hw":          hw_js,
        "mount":       m.get("mount", "below"),         # "below" or "above"
        "overhang":    round(to_in(m.get("track_overhang", 0)) * f, 4),
        "sheer":       bool(m.get("sheer", False)),
    })

    return f"""
<script type="importmap">
{{
  "imports": {{
    "three": "https://cdn.jsdelivr.net/npm/three@0.165.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.165.0/examples/jsm/"
  }}
}}
</script>
<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

const D = {data};

/* ── helpers ── */
function box(w, h, d, color, opacity) {{
  const geo = new THREE.BoxGeometry(w, h, d);
  const mat = new THREE.MeshLambertMaterial({{
    color,
    transparent: opacity !== undefined && opacity < 1,
    opacity: opacity ?? 1,
    side: THREE.DoubleSide,
  }});
  return new THREE.Mesh(geo, mat);
}}

function edges(mesh, color=0x888888) {{
  const eg = new THREE.EdgesGeometry(mesh.geometry);
  const lm = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({{color}}));
  lm.position.copy(mesh.position);
  return lm;
}}

/* ── scene ── */
const canvas   = document.getElementById('bp-3d');
const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.shadowMap.enabled = true;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf2f0ec);

const W = canvas.parentElement.clientWidth;
const H = Math.round(W * 0.52);
canvas.style.width  = W + 'px';
canvas.style.height = H + 'px';
renderer.setSize(W, H);

const camera = new THREE.PerspectiveCamera(42, W / H, 0.01, 500);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;

/* ── lighting ── */
scene.add(new THREE.AmbientLight(0xffffff, 0.65));
const sun = new THREE.DirectionalLight(0xfff8ee, 0.9);
sun.position.set(D.rw * 1.5, D.rh * 2.5, D.rl * 2);
scene.add(sun);
const fill = new THREE.DirectionalLight(0xdce8ff, 0.3);
fill.position.set(-D.rw, D.rh, -D.rl);
scene.add(fill);

/* ── room shell ──
   Origin: floor left-front corner.
   X = width, Y = height, Z = depth (0=front, rl=back).
   Soffit wall:
     top    → back wall at Z = rl, soffit protrudes toward Z = rl - s_dep
     bottom → front wall at Z = 0, soffit protrudes toward Z = s_dep
     left   → left wall at X = 0,  soffit protrudes toward X = s_dep
     right  → right wall at X = rw, soffit protrudes toward X = rw - s_dep
*/
const {{ rw, rl, rh, wall, s_len, s_dep, s_bot, s_off,
         t_len, t_off, t_ins, br_sp, drop, panels }} = D;

const sH = rh - s_bot;   // soffit box height (ceiling to soffit bottom)

/* floor */
const floor = box(rw, 0.015, rl, 0xd2cec8);
floor.position.set(rw/2, 0, rl/2);
scene.add(floor);
scene.add(edges(floor, 0xaaa89f));

/* grid on floor */
const grid = new THREE.GridHelper(Math.max(rw, rl) * 1.6, 16, 0xbbb8b2, 0xd0cdc8);
grid.position.set(rw/2, 0.002, rl/2);
scene.add(grid);

/* walls — semi-transparent so interior is visible */
const wallMat = new THREE.MeshLambertMaterial({{
  color: 0xf0ede8, transparent: true, opacity: 0.22, side: THREE.DoubleSide
}});
function wallMesh(w, h, d, x, y, z) {{
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), wallMat);
  m.position.set(x, y, z);
  return m;
}}
const t = 0.025;  // wall thickness
scene.add(wallMesh(rw,   rh, t,   rw/2, rh/2, 0));      // front
scene.add(wallMesh(rw,   rh, t,   rw/2, rh/2, rl));     // back
scene.add(wallMesh(t,    rh, rl,  0,    rh/2, rl/2));   // left
scene.add(wallMesh(t,    rh, rl,  rw,   rh/2, rl/2));   // right

/* wall edge outlines */
[
  [rw, rh, t,  rw/2, rh/2, 0],
  [rw, rh, t,  rw/2, rh/2, rl],
  [t,  rh, rl, 0,    rh/2, rl/2],
  [t,  rh, rl, rw,   rh/2, rl/2],
].forEach(([w,h,d,x,y,z]) => {{
  const m = new THREE.Mesh(new THREE.BoxGeometry(w,h,d));
  m.position.set(x,y,z);
  scene.add(edges(m, 0xb0aca6));
}});

/* ceiling (very transparent) */
const ceil = box(rw, t, rl, 0xe8e4de, 0.08);
ceil.position.set(rw/2, rh, rl/2);
scene.add(ceil);

/* ── soffit ── */
let sfx, sfz, sfBotY = s_bot, sfTopY = rh;
let sfW, sfD;   // (x-extent, z-extent)
let trackAxis;  // 'x' or 'z'
let trackX1, trackX2, trackZ;

if (wall === 'top') {{
  sfW = s_len; sfD = s_dep;
  sfx = s_off + sfW/2;
  sfz = rl - sfD/2;
  trackAxis = 'x';
  trackX1 = s_off + t_off;
  trackX2 = trackX1 + t_len;
  trackZ   = rl - s_dep;        // face of soffit (front-facing)
}} else if (wall === 'bottom') {{
  sfW = s_len; sfD = s_dep;
  sfx = s_off + sfW/2;
  sfz = sfD/2;
  trackAxis = 'x';
  trackX1 = s_off + t_off;
  trackX2 = trackX1 + t_len;
  trackZ   = s_dep;
}} else if (wall === 'left') {{
  sfW = s_dep; sfD = s_len;
  sfx = sfW/2;
  sfz = s_off + sfD/2;
  trackAxis = 'z';
  trackX1 = s_dep;
  trackX2 = trackX1;
  trackZ   = s_off + t_off;
}} else {{  // right
  sfW = s_dep; sfD = s_len;
  sfx = rw - sfW/2;
  sfz = s_off + sfD/2;
  trackAxis = 'z';
  trackX1 = rw - s_dep;
  trackX2 = trackX1;
  trackZ   = s_off + t_off;
}}

const soffit = box(sfW, sH, sfD, 0xc8c2bb);
soffit.position.set(sfx, s_bot + sH/2, sfz);
scene.add(soffit);
scene.add(edges(soffit, 0x888078));

/* ── track — mount-aware, profile-aware ── */
const hw       = D.hw;
const mount    = D.mount || 'below';
const overhang = D.overhang || 0;

/* adjust trackZ to account for overhang past soffit face */
if (overhang > 0) {{
  if      (wall === 'top')    trackZ -= overhang;
  else if (wall === 'bottom') trackZ += overhang;
  else if (wall === 'left')   trackX1 -= overhang;
  else                        trackX1 += overhang;
}}

/*
  "above" mount: brackets are hidden inside the soffit, going UP to ceiling.
  Track sits at soffit-face level, with `overhang` inches past the soffit edge.
  "below" mount (default): brackets hang DOWN from soffit face to track.
*/
const trackY = (mount === 'above') ? s_bot : (s_bot - t_ins);

const trackMetal = new THREE.MeshStandardMaterial({{
  color: 0x2c3e6b, metalness: 0.75, roughness: 0.22,
}});

let trackMesh;
if (hw.profile === 'round') {{
  const r = hw.profile_r;
  const geo = new THREE.CylinderGeometry(r, r, t_len, 16);
  trackMesh = new THREE.Mesh(geo, trackMetal);
  if (trackAxis === 'x') {{
    trackMesh.rotation.z = Math.PI / 2;
    trackMesh.position.set(trackX1 + t_len/2, trackY, trackZ);
  }} else {{
    trackMesh.rotation.x = Math.PI / 2;
    trackMesh.position.set(trackX1, trackY, trackZ + t_len/2);
  }}
}} else {{
  const tw = hw.profile_w, th = hw.profile_h;
  if (trackAxis === 'x') {{
    trackMesh = new THREE.Mesh(new THREE.BoxGeometry(t_len, th, tw), trackMetal);
    trackMesh.position.set(trackX1 + t_len/2, trackY - th/2, trackZ);
  }} else {{
    trackMesh = new THREE.Mesh(new THREE.BoxGeometry(tw, th, t_len), trackMetal);
    trackMesh.position.set(trackX1, trackY - th/2, trackZ + t_len/2);
  }}
}}
scene.add(trackMesh);

/* ── brackets ── */
const nBr  = Math.max(2, Math.round(t_len / br_sp) + 1);
const brMat = new THREE.MeshStandardMaterial({{ color: 0x2c3e6b, metalness: 0.6, roughness: 0.35 }});

for (let i = 0; i < nBr; i++) {{
  const frac = i / Math.max(nBr - 1, 1);

  if (mount === 'above') {{
    /* bracket runs UP from track Y through the soffit to the ceiling above */
    const brH = rh - trackY;
    const br  = new THREE.Mesh(new THREE.BoxGeometry(0.038, brH, 0.038), brMat);
    if (trackAxis === 'x') {{
      br.position.set(trackX1 + frac * t_len, trackY + brH/2, trackZ);
    }} else {{
      br.position.set(trackX1, trackY + brH/2, trackZ + frac * t_len);
    }}
    scene.add(br);

    /* ceiling anchor plate (visible above soffit) */
    const anchor = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.02, 0.14), brMat);
    anchor.position.copy(br.position);
    anchor.position.y = rh - 0.01;
    scene.add(anchor);

    /* the 1" of track face visible past the soffit — highlight it */
    if (overhang > 0 && i === 0) {{
      const faceMat = new THREE.MeshStandardMaterial({{
        color: 0x3a5080, metalness: 0.5, roughness: 0.4
      }});
      const faceGeo = trackAxis === 'x'
        ? new THREE.BoxGeometry(t_len, hw.profile_h || 0.04, overhang)
        : new THREE.BoxGeometry(overhang, hw.profile_h || 0.04, t_len);
      const face = new THREE.Mesh(faceGeo, faceMat);
      if (trackAxis === 'x') {{
        const faceZ = (wall==='top') ? trackZ - overhang/2 : trackZ + overhang/2;
        face.position.set(trackX1 + t_len/2, trackY, faceZ);
      }} else {{
        const faceX = (wall==='left') ? trackX1 - overhang/2 : trackX1 + overhang/2;
        face.position.set(faceX, trackY, trackZ + t_len/2);
      }}
      scene.add(face);
    }}

  }} else {{
    /* standard: bracket hangs DOWN from soffit face to track */
    const brH = s_bot - trackY + 0.04;
    const br  = new THREE.Mesh(new THREE.BoxGeometry(0.042, brH, 0.042), brMat);
    if (trackAxis === 'x') {{
      br.position.set(trackX1 + frac * t_len, s_bot - brH/2, trackZ);
    }} else {{
      br.position.set(trackX1, s_bot - brH/2, trackZ + frac * t_len);
    }}
    scene.add(br);
    const plate = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.022, 0.13), brMat);
    plate.position.copy(br.position);
    plate.position.y = s_bot - 0.01;
    scene.add(plate);
  }}
}}

/* ── curtain panels + fabric texture ── */
const curtainMeshes = [];
if (drop > 0 && panels > 0) {{
  const panelLen = t_len / panels;
  const curtainY = trackY - drop / 2;

  const isSheer = D.sheer || false;
  const curtainMat = new THREE.MeshStandardMaterial({{
    color: isSheer ? 0xe8eef2 : 0xb8c8d8,
    roughness: isSheer ? 0.6 : 0.88,
    metalness: 0.0,
    transparent: true,
    opacity: isSheer ? 0.38 : 0.87,
    side: THREE.DoubleSide,
  }});

  for (let i = 0; i < panels; i++) {{
    const frac = i / panels;
    let cm;
    if (trackAxis === 'x') {{
      cm = new THREE.Mesh(
        new THREE.BoxGeometry(panelLen * 0.93, drop, 0.010),
        curtainMat.clone()
      );
      cm.position.set(trackX1 + (frac + 0.5/panels) * t_len, curtainY, trackZ + 0.018);
    }} else {{
      cm = new THREE.Mesh(
        new THREE.BoxGeometry(0.010, drop, panelLen * 0.93),
        curtainMat.clone()
      );
      cm.position.set(trackX1 + 0.018, curtainY, trackZ + (frac + 0.5/panels) * t_len);
    }}
    scene.add(cm);
    curtainMeshes.push({{ mesh: cm, panelLen, i }});

    /* fold lines — more folds for ripplefold, fewer for regular pleat */
    const numFolds = isSheer ? 6 : 3;
    for (let f2 = 1; f2 < numFolds; f2++) {{
      const foldMat = new THREE.LineBasicMaterial({{
        color: isSheer ? 0xaabbc8 : 0x8899aa,
        transparent: true,
        opacity: isSheer ? 0.22 : 0.28,
      }});
      const pts = [];
      if (trackAxis === 'x') {{
        const fx = trackX1 + (frac + f2 / (numFolds * panels)) * t_len;
        pts.push(new THREE.Vector3(fx, trackY,        trackZ + 0.025));
        pts.push(new THREE.Vector3(fx, trackY - drop, trackZ + 0.025));
      }} else {{
        const fz = trackZ + (frac + f2 / (numFolds * panels)) * t_len;
        pts.push(new THREE.Vector3(trackX1 + 0.025, trackY,        fz));
        pts.push(new THREE.Vector3(trackX1 + 0.025, trackY - drop, fz));
      }}
      scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), foldMat));
    }}
  }}

  /* load fabric texture (silent fail → keeps solid colour) */
  if (D.fabric_url) {{
    const loader = new THREE.TextureLoader();
    loader.load(D.fabric_url,
      (tex) => {{
        tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
        curtainMeshes.forEach(({{ mesh, panelLen }}) => {{
          const tClone = tex.clone();
          tClone.needsUpdate = true;
          /* ~3 pattern repeats per foot of panel width, ~2 per foot of drop */
          tClone.repeat.set(
            Math.max(1, Math.round(panelLen * 3)),
            Math.max(1, Math.round(drop * 2))
          );
          mesh.material.map = tClone;
          mesh.material.color.set(0xffffff);
          mesh.material.opacity = 0.92;
          mesh.material.needsUpdate = true;
        }});
      }},
      undefined,
      () => {{}}   // fail silently
    );
  }}

  /* lining overlay (second semi-transparent layer behind panels) */
  if (D.lining_url) {{
    const lLoader = new THREE.TextureLoader();
    lLoader.load(D.lining_url, (tex) => {{
      tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
      tex.repeat.set(2, 3);
      const lMat = new THREE.MeshStandardMaterial({{
        map: tex, transparent: true, opacity: 0.45, side: THREE.DoubleSide,
      }});
      curtainMeshes.forEach(({{ mesh }}) => {{
        const lm = mesh.clone();
        lm.material = lMat;
        if (trackAxis === 'x') lm.position.z += 0.015;
        else                   lm.position.x += 0.015;
        scene.add(lm);
      }});
    }}, undefined, () => {{}});
  }}
}}

/* ── windows ── */
D.windows.forEach(win => {{
  const wMat = new THREE.MeshLambertMaterial({{
    color: 0xa8d8ea, transparent: true, opacity: 0.55, side: THREE.DoubleSide
  }});
  let wm;
  const wt = 0.03;
  switch(win.wall) {{
    case 'top':
      wm = new THREE.Mesh(new THREE.BoxGeometry(win.width, rh*0.45, wt), wMat);
      wm.position.set(win.offset + win.width/2, rh*0.4, rl);
      break;
    case 'bottom':
      wm = new THREE.Mesh(new THREE.BoxGeometry(win.width, rh*0.45, wt), wMat);
      wm.position.set(win.offset + win.width/2, rh*0.4, 0);
      break;
    case 'left':
      wm = new THREE.Mesh(new THREE.BoxGeometry(wt, rh*0.45, win.width), wMat);
      wm.position.set(0, rh*0.4, win.offset + win.width/2);
      break;
    case 'right':
      wm = new THREE.Mesh(new THREE.BoxGeometry(wt, rh*0.45, win.width), wMat);
      wm.position.set(rw, rh*0.4, win.offset + win.width/2);
      break;
  }}
  if (wm) scene.add(wm);
}});

/* ── camera initial position ── */
let camX, camY, camZ, targetX, targetY, targetZ;
targetX = rw / 2; targetY = rh * 0.5; targetZ = rl / 2;
switch(wall) {{
  case 'top':    camX = rw*0.5; camY = rh*1.1; camZ = rl*2.0;  break;
  case 'bottom': camX = rw*0.5; camY = rh*1.1; camZ = -rl*0.8; break;
  case 'left':   camX = -rw*0.8; camY = rh*1.1; camZ = rl*0.5; break;
  case 'right':  camX = rw*1.8;  camY = rh*1.1; camZ = rl*0.5; break;
}}
camera.position.set(camX, camY, camZ);
controls.target.set(targetX, targetY, targetZ);
controls.update();

/* ── animate ── */
(function loop() {{
  requestAnimationFrame(loop);
  controls.update();
  renderer.render(scene, camera);
}})();

/* ── resize ── */
window.addEventListener('resize', () => {{
  const nw = canvas.parentElement.clientWidth;
  const nh = Math.round(nw * 0.52);
  canvas.style.width = nw+'px'; canvas.style.height = nh+'px';
  renderer.setSize(nw, nh);
  camera.aspect = nw / nh;
  camera.updateProjectionMatrix();
}});

</script>"""


# ── Specs table ───────────────────────────────────────────────────────────────

def specs_table(m):
    br_sp  = m.get("bracket_spacing", 24)
    n_br   = max(2, int(m["track_length"] / br_sp) + 1)
    hw_key = m.get("hardware_key", "custom")
    hw     = HARDWARE.get(hw_key, HARDWARE["custom"])

    # clearance warning
    warnings = []
    if br_sp > hw["bracket_spacing_max"]:
        warnings.append(
            f'⚠ Bracket spacing {fmt(br_sp)} exceeds max {fmt(hw["bracket_spacing_max"])} '
            f'for {hw["name"]}.'
        )
    curtain_bottom = m["soffit_bottom_from_floor"] - m.get("track_inset", 0) - m.get("curtain_drop", 0)
    if curtain_bottom < 0:
        warnings.append(f'⚠ Curtain drop extends {fmt(abs(curtain_bottom))} below floor.')
    elif curtain_bottom < 0.5:
        warnings.append(f'⚠ Curtain hem is within ½" of floor — confirm intended.')

    rows = [
        ("Room Width",       fmt(m["room_width"])),
        ("Room Length",      fmt(m["room_length"])),
        ("Ceiling Height",   fmt(m["ceiling_height"])),
        ("Soffit Bottom",    fmt(m["soffit_bottom_from_floor"]) + " from floor"),
        ("Soffit Depth",     fmt(m["soffit_depth"])),
        ("Soffit Length",    fmt(m["soffit_length"])),
        ("Track System",     hw["name"] + (" · Motorized" if hw["motorized"] else "")),
        ("Track Profile",    hw["profile"].title()),
        ("Track Length",     fmt(m["track_length"])),
        ("Track Inset",      fmt(m.get("track_inset", 0)) + " from soffit face"),
        ("Bracket Spacing",  fmt(br_sp) + f' (max {fmt(hw["bracket_spacing_max"])} for this track)'),
        ("Bracket Count",    str(n_br)),
        ("Curtain Drop",     fmt(m.get("curtain_drop", 0))),
        ("Panel Count",      str(m.get("panel_count", 0))),
    ]
    if m.get("fabric_name"):
        rows.append(("Main Fabric", m["fabric_name"]))
    if m.get("lining_name"):
        rows.append(("Lining", m["lining_name"]))
    if hw.get("note"):
        rows.append(("Hardware Note", hw["note"]))

    html = '<table class="specs">'
    for label, val in rows:
        html += f"<tr><td>{label}</td><td>{val}</td></tr>"
    html += "</table>"

    if warnings:
        html += '<div style="margin-top:10px;">'
        for w in warnings:
            html += (f'<div style="font-size:10px;color:#c0392b;margin-top:4px;'
                     f'font-family:Courier New,monospace;">{w}</div>')
        html += "</div>"

    return html


# ── HTML assembler ────────────────────────────────────────────────────────────

def render_blueprint_html(m):
    """Return complete HTML string for the blueprint."""
    m   = normalise(m)
    fp  = floor_plan_svg(m)
    el  = elevation_svg(m)
    sp  = specs_table(m)
    td  = three_scene_html(m)
    today = date.today().strftime("%B %d, %Y")

    client  = m.get("client",  "Client")
    project = m.get("project", "Project")
    room    = m.get("room",    "Room")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Blueprint — {client} / {room}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Courier New', Courier, monospace;
    font-size: 12px;
    background: #fff;
    color: #1a1a1a;
    padding: 0;
  }}
  .page {{
    width: 100%;
    max-width: 900px;
    margin: 0 auto;
    padding: 24px 30px 30px;
  }}
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    border-bottom: 2px solid #1a1a1a;
    padding-bottom: 10px;
    margin-bottom: 20px;
  }}
  .header-left h1 {{
    font-size: 18px;
    font-weight: bold;
    letter-spacing: 2px;
    text-transform: uppercase;
  }}
  .header-left p {{ font-size: 11px; color: #555; margin-top: 3px; }}
  .header-right {{ text-align: right; font-size: 11px; color: #555; line-height: 1.6; }}
  .drawing-title {{
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    color: #555;
    text-transform: uppercase;
    margin: 14px 0 4px;
  }}
  svg {{ display: block; border: 1px solid #e0e0e0; background: #fafafa; }}
  .specs-section {{ margin-top: 20px; }}
  .specs-title {{
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: #555;
    margin-bottom: 6px;
    border-bottom: 1px solid #ccc;
    padding-bottom: 4px;
  }}
  table.specs {{
    border-collapse: collapse;
    width: 50%;
    font-size: 11px;
  }}
  table.specs td {{
    padding: 3px 10px 3px 0;
    border-bottom: 1px solid #eee;
    color: #333;
  }}
  table.specs td:first-child {{ font-weight: bold; width: 220px; color: #1a1a1a; }}
  .footer {{
    margin-top: 18px;
    font-size: 9px;
    color: #aaa;
    border-top: 1px solid #eee;
    padding-top: 6px;
    text-align: right;
  }}
  .view3d-wrap {{
    width: 100%;
    border: 1px solid #e0e0e0;
    background: #f2f0ec;
    border-radius: 2px;
    overflow: hidden;
  }}
  .view3d-wrap canvas {{ display: block; }}
  .view3d-hint {{
    font-size: 10px;
    color: #999;
    margin-top: 4px;
    text-align: center;
  }}
  @media print {{
    body {{ background: white; }}
    .page {{ padding: 12px 16px; }}
    .no-print {{ display: none !important; }}
  }}
</style>
</head>
<body>
<div class="page">

  <div class="header">
    <div class="header-left">
      <h1>Glamour Upholstery</h1>
      <p>Installation Blueprint</p>
    </div>
    <div class="header-right">
      <strong>{client}</strong><br>
      Project: {project}<br>
      Room: {room}<br>
      Date: {today}
    </div>
  </div>

  <div class="drawing-title">Drawing 1 of 3 — Floor Plan (Top View)</div>
  {fp}

  <div class="drawing-title" style="margin-top:20px;">Drawing 2 of 3 — Elevation (Soffit Wall)</div>
  {el}

  <div class="drawing-title no-print" style="margin-top:20px;">Drawing 3 of 3 — 3D View (Interactive)</div>
  <div class="view3d-wrap no-print">
    <canvas id="bp-3d"></canvas>
  </div>
  <div class="view3d-hint no-print">Drag to rotate &nbsp;·&nbsp; Scroll to zoom &nbsp;·&nbsp; Right-drag to pan</div>

  <div class="specs-section">
    <div class="specs-title">Specifications</div>
    {sp}
  </div>

  <div class="footer">
    Generated by Glamour Blueprint Agent &nbsp;|&nbsp; {today} &nbsp;|&nbsp; All dimensions in inches unless noted
  </div>

</div>
{td}
</body>
</html>"""


# ── Input normalisation ───────────────────────────────────────────────────────

def normalise(m):
    """Convert all measurement fields to float inches."""
    inch_fields = [
        "room_width", "room_length", "ceiling_height",
        "soffit_length", "soffit_depth", "soffit_bottom_from_floor", "soffit_offset",
        "track_length", "track_offset", "track_inset", "bracket_spacing",
        "curtain_drop",
    ]
    out = dict(m)
    for f in inch_fields:
        if f in out:
            out[f] = to_in(out[f])
    for win in out.get("windows", []):
        for k in ("offset", "width"):
            if k in win:
                win[k] = to_in(win[k])
    return out


# ── Chrome PDF export ─────────────────────────────────────────────────────────

def find_chrome():
    system = platform.system()
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(local, r"Google\Chrome\Application\chrome.exe"),
        ]
    else:
        return "google-chrome"
    for c in candidates:
        if os.path.exists(c):
            return c
    return "google-chrome"


def export_pdf(html_path: Path, pdf_path: Path):
    chrome = find_chrome()
    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        str(html_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Chrome PDF export failed:\n{result.stderr}")


# ── Hardware catalog ──────────────────────────────────────────────────────────

HARDWARE = {
    "custom": {
        "name": "Custom / Specify",
        "bracket_spacing_max": 24,
        "profile": "flat",
        "profile_w": 1.75,
        "profile_h": 0.875,
        "motorized": False,
        "note": "Enter bracket spacing manually.",
    },
    "silent_gliss_6100": {
        "name": "Silent Gliss 6100 — Cord Operated",
        "bracket_spacing_max": 20,
        "profile": "round",
        "profile_r": 0.625,
        "motorized": False,
        "note": "Steel round rod. Max load 33 lbs/m. One-way or split draw.",
    },
    "silent_gliss_6840": {
        "name": "Silent Gliss 6840 — Motorized",
        "bracket_spacing_max": 20,
        "profile": "flat",
        "profile_w": 1.375,
        "profile_h": 1.0,
        "motorized": True,
        "note": "Motorized. Requires 110V within 6 ft of track end.",
    },
    "hunter_douglas_traverse": {
        "name": "Hunter Douglas Traverse Rod",
        "bracket_spacing_max": 30,
        "profile": "flat",
        "profile_w": 1.5,
        "profile_h": 0.75,
        "motorized": False,
        "note": "Two-way draw. Heavy duty. Wide spans up to 30\".",
    },
    "graber_steel_traverse": {
        "name": "Graber Steel Traverse",
        "bracket_spacing_max": 24,
        "profile": "flat",
        "profile_w": 1.25,
        "profile_h": 0.625,
        "motorized": False,
        "note": "Standard traverse. Widely available.",
    },
    "lutron_platinum": {
        "name": "Lutron Platinum — Motorized",
        "bracket_spacing_max": 18,
        "profile": "flat",
        "profile_w": 2.0,
        "profile_h": 1.25,
        "motorized": True,
        "note": "Smart home compatible. HomeKit, Alexa, Google. Quiet motor.",
    },
    "ripplefold": {
        "name": "Ripplefold Track",
        "bracket_spacing_max": 16,
        "profile": "flat",
        "profile_w": 1.0,
        "profile_h": 0.5,
        "motorized": False,
        "note": "Wave/ripple pleat heading required. 80% or 100% fullness.",
    },
    "kirsch_superfine": {
        "name": "Kirsch Superfine Rod",
        "bracket_spacing_max": 28,
        "profile": "round",
        "profile_r": 0.5,
        "motorized": False,
        "note": "Decorative round rod. Rings included. One-way or split.",
    },
}


# ── Demo measurements ─────────────────────────────────────────────────────────

DEMO = {
    "client":  "Alexx Boudreau",
    "project": "Living Room Curtains",
    "room":    "Living Room",

    "room_width":   "20-0",    # 20'0"
    "room_length":  "16-6",    # 16'6"
    "ceiling_height": "9-0",   # 9'0"

    "soffit_wall":              "top",
    "soffit_bottom_from_floor": "8-0",   # 8'0" — bottom of soffit
    "soffit_depth":             "14",    # 14" deep
    "soffit_length":            "18-0",  # 18'0" wide
    "soffit_offset":            "12",    # 12" from left wall

    "track_length":    "15-6",  # 15'6"
    "track_offset":    "9",     # 9" from start of soffit
    "track_inset":     "3",     # 3" down from soffit face
    "bracket_spacing": "24",    # every 24"

    "curtain_drop":  "90",   # 90" drop
    "panel_count":   4,

    "windows": [
        {"wall": "top", "offset": "24", "width": "72"}
    ],
}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    to_pdf = "--pdf" in args
    args   = [a for a in args if a != "--pdf"]

    if "--demo" in args or not args:
        m = DEMO
        stem = "boudreau_blueprint"
    else:
        path = Path(args[0])
        if not path.exists():
            print(f"Error: {path} not found.")
            sys.exit(1)
        m    = json.loads(path.read_text())
        stem = path.stem + "_blueprint"

    html = render_blueprint_html(m)

    out_dir  = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    html_path = out_dir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML → {html_path}")

    if to_pdf:
        pdf_path = out_dir / f"{stem}.pdf"
        print("Exporting PDF via Chrome headless...")
        try:
            export_pdf(html_path, pdf_path)
            print(f"PDF  → {pdf_path}")
        except Exception as e:
            print(f"PDF export failed: {e}")
            print("Open the HTML file manually and print to PDF.")
    else:
        print("Tip: add --pdf to export a PDF directly.")


if __name__ == "__main__":
    main()
