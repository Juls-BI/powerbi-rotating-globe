"""
Rotating-globe sample for Power BI.

Reads   data/sample-countries.csv  (iso_code, country, continent, lat, lon, co2_mt)
        land/globe-static.txt      land dots (see make_land_dots.py)
Writes  data/globe-data.csv        same rows + the geometry columns the DAX measure needs
        dax/Globe.dax              ready-to-paste measures (land dots already inlined)
        preview.svg                what the measure will draw, to check in a browser

Run:    python scripts/make_globe_data.py
Needs:  Python 3 only (no packages). Runs on your machine, not inside Power BI.

How the geometry works
----------------------
The globe is an orthographic view seen from slightly above the equator (TILT degrees).
Seen that way, every line of latitude is a flat ellipse. So each country bubble lives
on its own latitude "ring":
  * ring_y   - vertical centre of that ring's ellipse on screen
  * px, py   - the country's position on the ring before squashing into an ellipse
Each ring is drawn as  translate(CX ring_y) scale(1 sin(TILT))  and its contents spin
with an SVG <animateTransform type='rotate'>, so a dot circles the ring and, once
squashed, appears to travel round the globe.
When a bubble passes behind the globe it should fade out. Because the rotation speed is
fixed, we can precompute *when* that happens:
  * op_values - the opacities to step through (0.88 in front, 0.10 behind)
  * op_keys   - the fractions of one 70 s turn at which each opacity starts
"""
import csv, math, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CX, CY, R = 450, 236, 205          # globe centre and radius in SVG units
TILT = math.radians(22)             # how far above the equator we look from
SE, CE, TE = math.sin(TILT), math.cos(TILT), math.tan(TILT)
STEPS = 720                         # resolution of the front/back timing (0.5 degree)


def geometry(lat, lon):
    a, L = math.radians(lat), math.radians(lon)
    r = R * math.cos(a)                          # ring radius at this latitude
    px, py = r * math.sin(L), r * math.cos(L)    # position on the ring at rotation 0
    ring_y = CY - R * math.sin(a) * CE           # where the ring's ellipse sits on screen
    clip = -R * math.sin(a) * TE                 # points below this (ring coords) face us
    # visible at step i?  rotate (px, py) by -i/STEPS of a turn and test the y coordinate
    vis = [(-px * math.sin(2 * math.pi * i / STEPS) + py * math.cos(2 * math.pi * i / STEPS)) > clip
           for i in range(STEPS)]
    keys, vals = ["0"], [vis[0]]
    for i in range(1, STEPS):
        if vis[i] != vis[i - 1]:
            keys.append("%.4f" % (i / STEPS))
            vals.append(vis[i])
    return {
        "ring_y": "%.1f" % ring_y,
        "px": "%.1f" % px,
        "py": "%.1f" % py,
        "op_values": ";".join("0.88" if v else "0.10" for v in vals),
        "op_keys": ";".join(keys),
    }


rows = []
with open(os.path.join(ROOT, "data", "sample-countries.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        r.update(geometry(float(r["lat"]), float(r["lon"])))
        rows.append(r)

cols = ["iso_code", "country", "continent", "lat", "lon", "co2_mt", "ring_y", "px", "py", "op_values", "op_keys"]
with open(os.path.join(ROOT, "data", "globe-data.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

static = open(os.path.join(ROOT, "land", "globe-static.txt"), encoding="utf-8").read()
assert '"' not in static, "the land fragment must not contain double quotes (it goes inside a DAX string)"

ROT = "<animateTransform attributeName='transform' type='rotate' from='0' to='-360' dur='70s' repeatCount='indefinite'/>"
OPEN = "<svg xmlns='http://www.w3.org/2000/svg' width='570' height='570' viewBox='165 -49 570 570' preserveAspectRatio='xMidYMid meet'>"


def bubble(r, size):
    return ("<g transform='translate(450 %s) scale(1 %.4f)'><g>%s<path d='M%s %sh0' stroke='#5C6B7A' "
            "stroke-width='%d'><animate attributeName='stroke-opacity' values='%s' keyTimes='%s' "
            "calcMode='discrete' dur='70s' repeatCount='indefinite'/><title>%s</title></path></g></g>"
            % (r["ring_y"], SE, ROT, r["px"], r["py"], size, r["op_values"], r["op_keys"], r["country"]))


# ---- preview.svg: exactly what the DAX measure produces, for a quick check in any browser
mx = max(float(r["co2_mt"]) for r in rows)
body = "".join(bubble(r, round(4 + 44 * math.sqrt(float(r["co2_mt"]) / mx))) for r in rows)
open(os.path.join(ROOT, "preview.svg"), "w", encoding="utf-8").write(OPEN + static + body + "</svg>")

# ---- Globe.dax: the measure, with the land dots inlined
dax = f'''Globe =
// Table: 'Globe Data' loaded from globe-data.csv
// Set this measure's Data category to "Image URL", then use it in an Image visual
// (Image > Image type: Image URL > fx > this measure, Scaling: Fill).
VAR _static = "{static}"
VAR _max = MAX ( 'Globe Data'[co2_mt] )
VAR _bubbles =
    CONCATENATEX (
        'Globe Data',
        VAR _size = 4 + 44 * SQRT ( DIVIDE ( 'Globe Data'[co2_mt], _max ) )   // bubble diameter
        RETURN
            "<g transform='translate(450 " & 'Globe Data'[ring_y] & ") scale(1 {SE:.4f})'><g>"
                & "{ROT}"
                & "<path d='M" & 'Globe Data'[px] & " " & 'Globe Data'[py] & "h0' stroke='#5C6B7A' stroke-width='"
                & ROUND ( _size, 0 ) & "'>"
                & "<animate attributeName='stroke-opacity' values='" & 'Globe Data'[op_values]
                & "' keyTimes='" & 'Globe Data'[op_keys] & "' calcMode='discrete' dur='70s' repeatCount='indefinite'/>"
                & "<title>" & 'Globe Data'[country] & "</title></path></g></g>",
        ""
    )
VAR _svg = "{OPEN}" & _static & _bubbles & "</svg>"
RETURN
    // '#' has to be escaped inside a data URI
    "data:image/svg+xml;utf8," & SUBSTITUTE ( _svg, "#", "%23" )


Globe motion table (Modeling > New table):

Globe motion = DATATABLE ( "Motion", STRING, "Order", INTEGER, {{ {{ "Play", 1 }}, {{ "Pause", 2 }} }} )


Pause-aware measure (Data category: Image URL) - use this one in the Image visual
and add a button slicer on 'Globe motion'[Motion] with Single select on:

Globe live =
VAR _paused = SELECTEDVALUE ( 'Globe motion'[Motion] ) = "Pause"
RETURN
    IF ( _paused, SUBSTITUTE ( [Globe], "dur='70s'", "dur='9999999s'" ), [Globe] )
'''
open(os.path.join(ROOT, "dax", "Globe.dax"), "w", encoding="utf-8").write(dax)
print(f"{len(rows)} countries -> globe-data.csv, Globe.dax, preview.svg")
