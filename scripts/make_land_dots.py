"""
Generate land/globe-static.txt: the dotted land, sphere and styles for the globe.

You only need this to change the look (dot spacing, tilt, colours). The repo already
ships a ready-made land/globe-static.txt.

Run:    python scripts/make_land_dots.py                 (downloads land-110m.json)
        python scripts/make_land_dots.py path/to/land-110m.json
Needs:  Python 3 only (no packages).

Land outlines: Natural Earth 1:110m (public domain), via the world-atlas package
https://github.com/topojson/world-atlas

How it works
------------
We walk round the world in latitude rings STEP degrees apart. On each ring we place
evenly spaced points and keep the ones that fall on land. Each ring is then drawn as an
ellipse (translate + scale(1, sin TILT)) whose contents rotate once every DUR.
Every ring is drawn twice: a pale copy clipped to the far side of the globe and a darker
copy clipped to the near side, with a translucent sphere between them.
"""
import json, math, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/land-110m.json"

CX, CY, R = 450, 236, 205          # must match make_globe_data.py
TILT = math.radians(22)
STEP = 3.6                         # degrees between dots (smaller = denser globe)
DUR = "70s"                        # one full turn
BACK, FRONT = "#CDD3DA", "#8E98A5" # far-side and near-side dot colours

SE, CE, TE = math.sin(TILT), math.cos(TILT), math.tan(TILT)
ROT = ("<animateTransform attributeName='transform' type='rotate' from='0' to='-360' "
       "dur='%s' repeatCount='indefinite'/>" % DUR)

# ---------------------------------------------------------------- load + decode TopoJSON
if len(sys.argv) > 1:
    topo = json.load(open(sys.argv[1], encoding="utf-8"))
else:
    print("downloading", URL)
    with urllib.request.urlopen(URL) as r:
        topo = json.load(r)

sx, sy = topo["transform"]["scale"]
tx, ty = topo["transform"]["translate"]
arcs = []
for arc in topo["arcs"]:
    x = y = 0
    pts = []
    for dx, dy in arc:                       # arcs are delta-encoded
        x += dx; y += dy
        pts.append((x * sx + tx, y * sy + ty))
    arcs.append(pts)


def ring(idx):
    out = []
    for i in idx:
        pts = arcs[i] if i >= 0 else arcs[~i][::-1]
        out.extend(pts if not out else pts[1:])
    return out


polys = []
for g in topo["objects"]["land"]["geometries"]:
    parts = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
    for p in parts:
        polys.append([ring(r) for r in p])


def inside(pt, rg):                          # ray casting
    x, y = pt
    c = False
    for i in range(len(rg)):
        x1, y1 = rg[i]; x2, y2 = rg[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def is_land(lon, lat):
    return any(inside((lon, lat), p[0]) and not any(inside((lon, lat), h) for h in p[1:]) for p in polys)


# ---------------------------------------------------------------- dots per latitude ring
defs, back, front = [], [], []
dots = k = 0
lat = -56.0
while lat <= 82:
    a = math.radians(lat)
    r = R * math.cos(a)
    n = max(1, int(round(360 * math.cos(a) / STEP)))
    d = ""
    for i in range(n):
        lon = -180 + (i + 0.5) * 360 / n
        if is_land(lon, lat):
            L = math.radians(lon)
            d += "M%d %dh0" % (round(r * math.sin(L)), round(r * math.cos(L)))
            dots += 1
    if d:
        ring_y = CY - R * math.sin(a) * CE
        clip = -R * math.sin(a) * TE         # ring y-coordinate where the near side begins
        defs.append("<path id='r%d' d='%s'/><clipPath id='f%d'><rect x='-260' y='%.1f' width='520' height='1300'/></clipPath>"
                    "<clipPath id='b%d'><rect x='-260' y='-1300' width='520' height='%.1f'/></clipPath>"
                    % (k, d, k, clip, k, 1300 + clip))
        tr = "translate(%d %.1f) scale(1 %.4f)" % (CX, ring_y, SE)
        back.append("<g transform='%s'><g clip-path='url(#b%d)'><g>%s<use href='#r%d'/></g></g></g>" % (tr, k, ROT, k))
        front.append("<g transform='%s'><g clip-path='url(#f%d)'><g>%s<use href='#r%d'/></g></g></g>" % (tr, k, ROT, k))
        k += 1
    lat += STEP

style = ("<style>path{fill:none;stroke-linecap:round;vector-effect:non-scaling-stroke}"
         ".bk{stroke:%s;stroke-width:2.6}.fr{stroke:%s;stroke-width:3.2}"
         "text{font-family:Segoe UI,sans-serif}</style>" % (BACK, FRONT))
grad = ("<radialGradient id='oc' cx='0.38' cy='0.32' r='0.75'><stop offset='0' stop-color='#FFFFFF'/>"
        "<stop offset='1' stop-color='#E4EAF0'/></radialGradient>")
static = ("<defs>" + style + grad + "".join(defs) + "</defs>"
          + "<g class='bk'>" + "".join(back) + "</g>"
          + "<circle cx='%d' cy='%d' r='%d' fill='url(#oc)' fill-opacity='0.82' stroke='#D9DEE4' stroke-width='1.2'/>"
          % (CX, CY, R)
          + "<g class='fr'>" + "".join(front) + "</g>")
assert '"' not in static                      # it goes inside a DAX string literal

out = os.path.join(ROOT, "land", "globe-static.txt")
open(out, "w", encoding="utf-8").write(static)
print(f"{dots} land dots on {k} rings, {len(static):,} characters -> {out}")
