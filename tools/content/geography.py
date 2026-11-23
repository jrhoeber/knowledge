"""Geography questions: countries and US states on a map, flags, and capitals.

Five kinds of item fall into three categories, which the app rotates through evenly
(item IDs are contiguous per category and difficulty):

    map      country_map, state_map            name the highlighted country or state
    flag     country_flag                      name the country a flag belongs to
    capital  country_capital, state_capital    pick the capital of a named place

Countries are the 193 UN members plus Vatican City, Palestine and Taiwan; states are
the 50 US states. Both lists are curated by hand in `countries.csv` and `states.csv`:
display names in American usage, capitals (with a note where a country splits its
capital functions), famous non-capital cities that make tempting wrong answers
(`decoys`), the Wikipedia articles whose pageviews measure how familiar a place is,
and the Wikimedia Commons flag files. Capital questions are skipped where the answer
gives itself away (Mexico City, Tunis, Indianapolis) and where there is no
uncontested capital (Palestine, Nauru).

Sources, downloaded into `.cache/geography/` on first run:

- Natural Earth 1:10m Admin 0 countries, United States point of view (public
  domain). Borders follow US policy: Crimea is part of Ukraine, the Golan Heights of
  Israel, and Kashmir is divided along the Line of Control. The build also folds
  Abkhazia and South Ossetia into Georgia and Western Sahara into Morocco (US
  recognition since 2020), and draws Guantanamo Bay as part of Cuba.
- Natural Earth 1:10m Admin 1 states and provinces, lakes removed (the US states).
- Natural Earth 1:10m lakes: lakes over `MIN_LAKE_KM2` are cut out of the land so
  the Great Lakes, Lake Victoria and Lake Titicaca read as water.
- Flags from Wikimedia Commons, rendered to PNG by Commons. The build fails unless
  every file is in the public domain, except Oman's, which is under the Open
  Government Licence – Oman 1.0 (attribution required; see `FLAG_LICENSES`).
- English Wikipedia pageviews over the 60 days before the first build (batched
  through the MediaWiki API, since Wikimedia allows anonymous clients only a few
  requests a minute), cached so later builds reuse them.

Geometry: the world (countries and territories) and the states are each simplified
as a coverage, so shared borders stay identical, at two levels of detail (`fine` for
close-ups, `coarse` for the zoomed-out view), then stored as Float32 longitude and
latitude rings. The app projects them orthographically around each question's
place. For each place the build also stores a close-up frame (center and extent of
the main landmass, so French Guiana does not pull the view of France across the
Atlantic) and a zoomed-out frame (the globe for countries, the state together with
the lower 48 for states).

Difficulty: every kind is split into five equal levels by a familiarity score, the
log of pageviews plus, for maps, the log of the area (small places are hard to find)
and, for flags, how far a flag is from its nearest lookalike. Capitals score on the
capital's own pageviews, lowered when a decoy city is better known (Sydney, Toronto).
Wrong answers get closer as the level rises: other continents at level 1, the same
continent at level 3, and neighbors, lookalike flags or decoy cities at level 5.
"""

from __future__ import annotations

import csv
import json
import math
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import numpy as np
import shapefile
import shapely
from PIL import Image
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.ops import polylabel

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache" / "geography"
COUNTRIES_CSV = HERE / "countries.csv"
STATES_CSV = HERE / "states.csv"

USER_AGENT = "KnowledgeContentBuild/1.0 (offline quiz app content pipeline)"
NATURAL_EARTH = "https://naciscdn.org/naturalearth/10m/{folder}/{name}.zip"
COUNTRIES_LAYER = ("cultural", "ne_10m_admin_0_countries_usa")
STATES_LAYER = ("cultural", "ne_10m_admin_1_states_provinces_lakes")
LAKES_LAYER = ("physical", "ne_10m_lakes")
PAGEVIEW_DAYS = 60  # the most the batched pageviews API returns

EARTH_RADIUS_KM = 6371.0
# Natural Earth features drawn as part of another country (see the module docstring).
MERGED_INTO = {"B35": "GEO", "B37": "GEO", "SAH": "MAR", "USG": "CUB"}
# Coverage simplification tolerance, in degrees (about the square root of the area
# of the triangles removed). Fine detail is used for close-ups, coarse for the globe.
FINE_TOLERANCE = 0.01
COARSE_TOLERANCE = 0.08
MIN_LAKE_KM2 = 1_500
# Islands smaller than this are dropped (a place always keeps its largest part).
FINE_MIN_PART_KM2 = 1.0
COARSE_MIN_PART_KM2 = 400.0
# Small places keep smaller islands, so Tuvalu and the Maldives are more than a dot.
SMALL_PLACE_KM2 = 2_000.0
SMALL_PLACE_MIN_PART_KM2 = 0.05
# Close-up frames: which parts of a country the close-up is fitted to (see frame_parts).
FRAME_HOP_KM = 350.0
FRAME_LARGE_PART = 0.25
FRAME_MAIN_ONLY = {"USA"}
# Places that must fall inside a given country under US policy; checked every build.
POLICY_CHECKS = {
    "Simferopol, Crimea": ((34.10, 44.95), "UKR"), "Laayoune, Western Sahara": ((-13.20, 27.15), "MAR"),
    "Sukhumi, Abkhazia": ((41.00, 43.00), "GEO"), "Tskhinvali, South Ossetia": ((43.96, 42.23), "GEO"),
    "Katzrin, Golan Heights": ((35.69, 32.99), "ISR"), "Northern Cyprus": ((33.60, 35.25), "CYP"),
    "Hargeisa, Somaliland": ((44.06, 9.56), "SOM"), "Tiraspol, Transnistria": ((29.60, 46.84), "MDA"),
    "Pristina, Kosovo": ((21.17, 42.66), "KOS"), "Itanagar, Arunachal Pradesh": ((93.61, 27.08), "IND"),
}  # Alaska and Hawaii would push the lower 48 into a corner.
# Smallest close-up, as a half height in radians of the unit sphere (about 320 km for
# countries, 140 km for states), and the most a lonely island zooms out to show land.
MIN_FRAME = {"world": 0.05, "states": 0.022}
MAX_FRAME_FOR_CONTEXT = 0.25
# A remote island group with no other land within MAX_FRAME_FOR_CONTEXT gets this
# instead, so its islands stay big enough to see (the zoomed-out view gives context).
REMOTE_FRAME = 0.07
NEIGHBORS_KEPT = 12
LOOKALIKES_KEPT = 10
FLAG_MAX_SIDE = 720  # pixels
# Accepted flag licenses. Oman's flag is under the Open Government Licence – Oman,
# which asks for attribution; each flag's license is stored for the credits.
FLAG_LICENSES = {"Public domain", "CC0", "OGL-om 1.0"}

AREA_NAMES = {
    "South-Eastern Asia": "Southeast Asia", "Eastern Asia": "East Asia", "Southern Asia": "South Asia",
    "Central Asia": "Central Asia", "Western Asia": "the Middle East", "Northern Africa": "North Africa",
    "Western Africa": "West Africa", "Eastern Africa": "East Africa", "Middle Africa": "Central Africa",
    "Southern Africa": "southern Africa", "Northern Europe": "northern Europe", "Western Europe": "western Europe",
    "Southern Europe": "southern Europe", "Eastern Europe": "eastern Europe", "Northern America": "North America",
    "Central America": "Central America", "Caribbean": "the Caribbean", "South America": "South America",
    "Australia and New Zealand": "Oceania", "Melanesia": "the Pacific", "Micronesia": "the Pacific",
    "Polynesia": "the Pacific",
}
AREA_OVERRIDES = {
    "ARM": "the Caucasus", "AZE": "the Caucasus", "GEO": "the Caucasus", "CYP": "the eastern Mediterranean",
    "TUR": "western Asia and southeastern Europe", "IRN": "the Middle East", "MEX": "North America",
    "RUS": "eastern Europe and northern Asia",
}
STATE_AREAS = {"Northeast": "the Northeast", "Midwest": "the Midwest", "South": "the South", "West": "the West"}

# Difficulty score weights, on top of log10 pageviews (see the module docstring).
AREA_WEIGHT = 0.35  # per log10 km2: big places are easy to find
DISTINCT_FLAG_WEIGHT = 0.5  # per log10 of the mean Lab distance to the three nearest flags
DECOY_WEIGHT = 1.5  # per log10 that a decoy city out-views the capital (Sydney over Canberra)

ITEM_KINDS = {  # kind: category
    "country_map": "map", "state_map": "map", "country_flag": "flag",
    "country_capital": "capital", "state_capital": "capital",
}


# MARK: Data model


@dataclass
class Place:
    """A row of `countries.csv` or `states.csv`."""

    code: str
    name: str
    article: str
    capital: str
    capital_article: str
    decoys: list[str]
    capital_note: str = ""
    flag_file: str = ""
    flag_note: str = ""


@dataclass
class Region:
    """Something drawn on the map. Quiz places carry a `Place`."""

    layer: str  # "world" or "states"
    code: str
    name: str
    continent: str
    subregion: str
    area_name: str
    geometry: MultiPolygon
    place: Place | None = None
    fine: MultiPolygon | None = None
    coarse: MultiPolygon | None = None
    area_km2: float = 0.0
    label: tuple[float, float] = (0.0, 0.0)
    frame: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # lon, lat, half width, half height
    frame_min: float = 0.0
    context: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    neighbors: list[Region] = field(default_factory=list)  # nearest quiz places in the same layer
    nearest_km: float = 0.0
    flag: bytes | None = None
    flag_size: tuple[int, int] = (0, 0)
    flag_license: str = ""
    lookalikes: list[Region] = field(default_factory=list)  # countries with the most similar flags
    distinctiveness: float = 0.0


@dataclass
class Item:
    kind: str
    region: Region
    score: float
    difficulty: int = 0


@dataclass
class Atlas:
    regions: list[Region]
    items: list[Item]
    counts: dict[str, int]


# MARK: Downloads


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def _fetch(url: str, attempts: int = 40) -> bytes:
    """Downloads `url`, waiting out rate limits (Wikimedia allows anonymous clients
    only a few requests a minute, so the first build spends a while on pageviews)."""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(_request(url), timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise
            wait = int(error.headers.get("Retry-After") or 0) or min(60, 5 * (attempt + 1))
            print(f"    {error.code}; retrying in {wait}s", file=sys.stderr)
            time.sleep(wait + 1)
        except (urllib.error.URLError, TimeoutError) as error:
            print(f"    {error} for {url}; retrying", file=sys.stderr)
            time.sleep(5)
    raise RuntimeError(f"Could not download {url}")


def natural_earth(layer: tuple[str, str]) -> Path:
    """Downloads and unpacks a Natural Earth layer once; returns the .shp path."""
    folder, name = layer
    directory = CACHE / "naturalearth" / name
    shp = directory / f"{name}.shp"
    if not shp.exists():
        directory.mkdir(parents=True, exist_ok=True)
        print(f"  downloading {name}")
        data = _fetch(NATURAL_EARTH.format(folder=folder, name=name))
        with zipfile.ZipFile(BytesIO(data)) as archive:
            for member in archive.namelist():
                target = (directory / Path(member).name).resolve()
                if target.parent == directory.resolve() and member.endswith((".shp", ".shx", ".dbf", ".prj", ".cpg", ".txt")):
                    target.write_bytes(archive.read(member))
    return shp


def _json_cache(name: str) -> tuple[Path, dict]:
    path = CACHE / name
    return path, (json.loads(path.read_text()) if path.exists() else {})


def pageviews(titles: set[str]) -> dict[str, int]:
    """English Wikipedia views per article over the `PAGEVIEW_DAYS` days before the
    first build, 50 articles per request. Cached in `.cache/geography/pageviews.json`
    (with the dates covered), so later builds reuse the same numbers."""
    path, cached = _json_cache("pageviews.json")
    views: dict[str, int] = cached.setdefault("views", {})
    days: set[str] = set(cached.get("days", []))
    missing = sorted(t for t in titles if t not in views)
    if missing:
        print(f"  fetching pageviews for {len(missing)} articles")
    for start in range(0, len(missing), 50):
        batch = missing[start:start + 50]
        params = {"action": "query", "prop": "pageviews", "titles": "|".join(batch), "pvipdays": PAGEVIEW_DAYS,
                  "redirects": 1, "format": "json", "formatversion": 2}
        totals: dict[str, int] = {}
        while True:  # each continuation fills in pageviews for more of the batch
            response = json.loads(_fetch("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)))
            query = response["query"]
            # Views of a redirect ("Zurich") are counted on its target ("Zürich").
            normalized = {n["to"]: n["from"] for n in query.get("normalized", [])}
            redirects = {r["to"]: r["from"] for r in query.get("redirects", [])}
            for page in query["pages"]:
                title = redirects.get(page["title"], page["title"])
                title = normalized.get(title, title)
                if page.get("missing") or page.get("invalid"):
                    raise SystemExit(f"No Wikipedia article {title!r}; fix the CSV.")
                if "pageviews" in page:
                    totals[title] = sum(count or 0 for count in page["pageviews"].values())
                    days.update(page["pageviews"])
            if "continue" not in response:
                break
            params.update(response["continue"])
        unanswered = [title for title in batch if title not in totals]
        if unanswered:
            raise SystemExit(f"No pageviews returned for {unanswered}")
        views.update(totals)
        cached["days"] = sorted(days)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cached, indent=1, sort_keys=True, ensure_ascii=False))
    return {title: views[title] for title in titles}


def pageview_window() -> str:
    days = json.loads((CACHE / "pageviews.json").read_text()).get("days", [])
    return f"{days[0]} to {days[-1]}" if days else "none"


def flag_images(files: dict[str, str]) -> dict[str, tuple[bytes, str]]:
    """Downloads each Commons flag (code → file name) as a PNG; returns PNG bytes and license."""
    info_path, info = _json_cache("flag-info.json")
    wanted = sorted(set(files.values()) - set(info))
    for start in range(0, len(wanted), 40):
        batch = wanted[start:start + 40]
        query = urllib.parse.urlencode({
            "action": "query", "prop": "imageinfo", "iiprop": "extmetadata|size", "format": "json",
            "titles": "|".join(f"File:{name}" for name in batch),
        })
        pages = json.loads(_fetch(f"https://commons.wikimedia.org/w/api.php?{query}"))["query"]
        normalized = {n["to"]: n["from"] for n in pages.get("normalized", [])}
        for page in pages["pages"].values():
            title = normalized.get(page["title"], page["title"]).removeprefix("File:")
            if "imageinfo" not in page:
                raise SystemExit(f"Wikimedia Commons has no file {title!r}; fix the CSV.")
            meta = page["imageinfo"][0]["extmetadata"]
            info[title] = {"license": meta.get("LicenseShortName", {}).get("value", "")}
        time.sleep(1)
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text(json.dumps(info, indent=1, sort_keys=True, ensure_ascii=False))

    unlicensed = {code: info[name]["license"] for code, name in files.items() if info[name]["license"] not in FLAG_LICENSES}
    if unlicensed:
        raise SystemExit(f"Flags without a public domain license: {unlicensed}")

    directory = CACHE / "flags"
    directory.mkdir(parents=True, exist_ok=True)
    result = {}
    for code, name in sorted(files.items()):
        png = directory / f"{code}.png"
        source = directory / f"{code}.source"
        if not png.exists() or not source.exists() or source.read_text() != name:
            print(f"  downloading flag {name}")
            title = urllib.parse.quote(name.replace(" ", "_"))
            png.write_bytes(_fetch(f"https://commons.wikimedia.org/wiki/Special:FilePath/{title}?width=960"))
            source.write_text(name)
            time.sleep(1)
        result[code] = (png.read_bytes(), info[name]["license"])
    return result


# MARK: Spherical helpers


def unit_vectors(coords: np.ndarray) -> np.ndarray:
    """(N, 2) longitude/latitude degrees → (N, 3) points on the unit sphere."""
    lon, lat = np.radians(coords[:, 0]), np.radians(coords[:, 1])
    return np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=1)


def to_lon_lat(vector: np.ndarray) -> tuple[float, float]:
    x, y, z = vector / np.linalg.norm(vector)
    return math.degrees(math.atan2(y, x)), math.degrees(math.asin(max(-1.0, min(1.0, z))))


def basis(center: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """East and north unit vectors at `center`, the axes of an orthographic view."""
    east = np.cross([0.0, 0.0, 1.0], center)
    if np.linalg.norm(east) < 1e-9:
        east = np.array([0.0, 1.0, 0.0])
    east /= np.linalg.norm(east)
    return east, np.cross(center, east)


def orthographic(center: np.ndarray):
    """Shapely transformation to an orthographic plane (unit sphere) around `center`."""
    east, north = basis(center)

    def project(coords: np.ndarray) -> np.ndarray:
        points = unit_vectors(coords)
        return np.stack([points @ east, points @ north], axis=1)

    return project


def equal_area(center: np.ndarray):
    """Shapely transformation to a Lambert azimuthal equal-area plane in kilometers."""
    east, north = basis(center)

    def project(coords: np.ndarray) -> np.ndarray:
        points = unit_vectors(coords)
        k = np.sqrt(2.0 / np.maximum(1.0 + points @ center, 1e-12)) * EARTH_RADIUS_KM
        return np.stack([k * (points @ east), k * (points @ north)], axis=1)

    return project


def center_of(geometry) -> np.ndarray:
    points = unit_vectors(shapely.get_coordinates(geometry))
    mean = points.mean(axis=0)
    return mean / np.linalg.norm(mean)


def area_km2(geometry) -> float:
    return sum(shapely.transform(part, equal_area(center_of(part))).area for part in shapely.get_parts(geometry))


def cap(geometry) -> tuple[np.ndarray, float]:
    """Center and angular radius (radians) of a circle on the sphere around `geometry`."""
    points = unit_vectors(shapely.get_coordinates(geometry))
    center = points.mean(axis=0)
    center /= np.linalg.norm(center)
    return center, float(np.arccos(np.clip(points @ center, -1, 1)).max())


def as_multipolygon(geometry) -> MultiPolygon:
    geometry = shapely.make_valid(geometry)
    parts = [p for p in shapely.get_parts(geometry) if isinstance(p, Polygon) and not p.is_empty]
    if not parts:  # make_valid can return collections with lines; keep the polygons
        parts = [g for p in shapely.get_parts(geometry) for g in shapely.get_parts(p) if isinstance(g, Polygon)]
    return MultiPolygon(parts)


# MARK: Loading


def read_places(path: Path) -> dict[str, Place]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {
        row["code"]: Place(
            code=row["code"], name=row["name"], article=row["article"], capital=row["capital"],
            capital_article=row["capital_article"], decoys=[d for d in row["decoys"].split(";") if d],
            capital_note=row.get("capital_note", ""), flag_file=row.get("flag_file", ""),
            flag_note=row.get("flag_note", ""),
        )
        for row in rows
    }


def _records(path: Path, fields: list[str]):
    reader = shapefile.Reader(str(path), encoding="utf-8")
    for item in reader.iterShapeRecords(fields=fields):
        yield item.record.as_dict(), shape(item.shape.__geo_interface__)


def load_world(countries: dict[str, Place]) -> list[Region]:
    """Countries and territories, with the merges in `MERGED_INTO` applied."""
    fields = ["ADM0_A3", "NAME_EN", "CONTINENT", "SUBREGION"]
    records: dict[str, tuple[dict, list]] = {}
    for record, geometry in _records(natural_earth(COUNTRIES_LAYER), fields):
        code = MERGED_INTO.get(record["ADM0_A3"], record["ADM0_A3"])
        entry = records.setdefault(code, ({}, []))
        if code == record["ADM0_A3"]:
            entry[0].update(record)
        entry[1].append(geometry)
    missing = set(countries) - set(records)
    assert not missing, f"countries.csv codes missing from Natural Earth: {missing}"
    regions = []
    for code in sorted(records):
        record, geometries = records[code]
        place = countries.get(code)
        geometry = as_multipolygon(shapely.union_all(geometries)) if len(geometries) > 1 else as_multipolygon(geometries[0])
        regions.append(Region(
            layer="world", code=code, name=place.name if place else record["NAME_EN"],
            continent=record["CONTINENT"], subregion=record["SUBREGION"],
            area_name=AREA_OVERRIDES.get(code) or AREA_NAMES.get(record["SUBREGION"], record["SUBREGION"]),
            geometry=geometry, place=place,
        ))
    return regions


def load_states(states: dict[str, Place]) -> list[Region]:
    regions = []
    for record, geometry in _records(natural_earth(STATES_LAYER), ["adm0_a3", "postal", "name", "region", "region_sub"]):
        if record["adm0_a3"] != "USA":
            continue
        code = record["postal"]
        place = states.get(code)
        area = "New England" if record["region_sub"] == "New England" else STATE_AREAS[record["region"]]
        regions.append(Region(
            layer="states", code=code, name=place.name if place else record["name"],
            continent=record["region"], subregion=record["region_sub"], area_name=area,
            geometry=as_multipolygon(geometry), place=place,
        ))
    missing = set(states) - {r.code for r in regions}
    assert not missing, f"states.csv codes missing from Natural Earth: {missing}"
    return sorted(regions, key=lambda r: r.code)


def load_lakes() -> list:
    lakes = [g for _, g in _records(natural_earth(LAKES_LAYER), ["name"])]
    return [as_multipolygon(g) for g in lakes if area_km2(g) >= MIN_LAKE_KM2]


# MARK: Geometry


def simplify(regions: list[Region], lakes: list) -> None:
    """Simplifies each layer as a coverage at two levels of detail and cuts out lakes."""
    geometries = np.array([r.geometry for r in regions], dtype=object)
    for tolerance, attribute, min_part in (
        (FINE_TOLERANCE, "fine", FINE_MIN_PART_KM2),
        (COARSE_TOLERANCE, "coarse", COARSE_MIN_PART_KM2),
    ):
        simplified = shapely.coverage_simplify(geometries, tolerance)
        water = shapely.coverage_simplify(np.array(lakes, dtype=object), tolerance)
        tree = shapely.STRtree(water)
        for region, geometry in zip(regions, simplified):
            hits = tree.query(geometry, predicate="intersects")
            if len(hits):
                geometry = shapely.difference(geometry, shapely.union_all(water[hits]))
            setattr(region, attribute, drop_small_parts(as_multipolygon(geometry), min_part, attribute == "fine"))


def drop_small_parts(geometry: MultiPolygon, min_part_km2: float, keep_holes: bool) -> MultiPolygon:
    parts = sorted(shapely.get_parts(geometry), key=area_km2, reverse=True)
    if not parts:
        return geometry
    total = sum(area_km2(p) for p in parts)
    threshold = SMALL_PLACE_MIN_PART_KM2 if total < SMALL_PLACE_KM2 else min_part_km2
    kept = [parts[0]] + [p for p in parts[1:] if area_km2(p) >= threshold]
    if not keep_holes:
        kept = [Polygon(p.exterior, [h for h in p.interiors if area_km2(Polygon(h)) >= threshold]) for p in kept]
    return MultiPolygon(kept)


def frame_parts(region: Region) -> list[Polygon]:
    """The landmass a close-up centers on: the largest part, parts at least
    `FRAME_LARGE_PART` of its size (both halves of Malaysia), and every island
    reachable from those in hops of up to `FRAME_HOP_KM` (all of Indonesia, but not
    French Guiana, the Galapagos or Svalbard)."""
    parts = sorted(shapely.get_parts(region.fine), key=area_km2, reverse=True)
    if region.code in FRAME_MAIN_ONLY:
        return parts[:1]
    project = equal_area(center_of(parts[0]))
    flat = [shapely.transform(p, project) for p in parts]
    largest = area_km2(parts[0])
    chosen = {0} | {i for i, p in enumerate(parts) if area_km2(p) >= FRAME_LARGE_PART * largest}
    tree = shapely.STRtree(flat)
    frontier = sorted(chosen)
    while frontier:
        for j in tree.query(flat[frontier.pop()], predicate="dwithin", distance=FRAME_HOP_KM):
            if int(j) not in chosen:
                chosen.add(int(j))
                frontier.append(int(j))
    return [parts[i] for i in sorted(chosen)]


def fit(geometries: list) -> tuple[float, float, float, float]:
    """Center (lon, lat) and half extents (unit sphere) of an orthographic view around geometries."""
    combined = shapely.union_all([g for g in geometries])
    center = center_of(combined)
    for _ in range(2):  # recenter on the projected bounding box
        flat = shapely.transform(combined, orthographic(center))
        x0, y0, x1, y1 = flat.bounds
        east, north = basis(center)
        bx, by = (x0 + x1) / 2, (y0 + y1) / 2
        center = bx * east + by * north + math.sqrt(max(0.0, 1 - bx * bx - by * by)) * center
        center /= np.linalg.norm(center)
    x0, y0, x1, y1 = shapely.transform(combined, orthographic(center)).bounds
    lon, lat = to_lon_lat(center)
    return lon, lat, max(abs(x0), abs(x1)), max(abs(y0), abs(y1))


def label_point(region: Region) -> tuple[float, float]:
    main = max(frame_parts(region), key=area_km2)
    center = center_of(main)
    flat = shapely.transform(main, orthographic(center))
    point = polylabel(flat, tolerance=max(flat.length / 2000, 1e-6))
    east, north = basis(center)
    vector = point.x * east + point.y * north + math.sqrt(max(0.0, 1 - point.x ** 2 - point.y ** 2)) * center
    return to_lon_lat(vector)


def measure_neighbors(targets: list[Region], others: list[Region]) -> None:
    """Ranks each target's nearest regions: touching ones by shared border, then by distance.

    `nearest_km` counts any land in `others`; `neighbors` keeps quiz places of the same layer.
    """
    caps = [cap(r.coarse) for r in others]
    for target in targets:
        center = unit_vectors(np.array([target.frame[:2]]))[0]
        project = orthographic(center)
        flat_target = shapely.transform(target.coarse, project)
        candidates = []
        for region, (cap_center, radius) in zip(others, caps):
            if region is target or math.acos(float(np.clip(cap_center @ center, -1, 1))) - radius > math.radians(60):
                continue
            flat = shapely.transform(region.coarse, project)
            distance = flat_target.distance(flat) * EARTH_RADIUS_KM
            shared = flat_target.boundary.intersection(flat.boundary).length if distance < 1 else 0.0
            candidates.append((distance, -shared, region.code, region))
        candidates.sort(key=lambda c: c[:3])
        target.nearest_km = candidates[0][0] if candidates else 0.0
        target.neighbors = [r for *_, r in candidates if r.place and r.layer == target.layer][:NEIGHBORS_KEPT]


def prepare_regions(world: list[Region], states: list[Region]) -> None:
    lakes = load_lakes()
    print(f"  {len(lakes)} lakes over {MIN_LAKE_KM2} km2")
    simplify(world, lakes)
    simplify(states, lakes)
    usa = next(r for r in world if r.code == "USA")
    lower48 = max(shapely.get_parts(usa.fine), key=area_km2)
    for region in world + states:
        region.area_km2 = area_km2(region.geometry)  # simplification skews tiny places
        region.label = label_point(region)
        region.frame = fit(frame_parts(region))
    for region in states:
        region.context = fit([region.fine, lower48])
    for region in world:
        region.context = (region.frame[0], region.frame[1], 1.0, 1.0)
    quiz_world = [r for r in world if r.place]
    quiz_states = [r for r in states if r.place]
    measure_neighbors(quiz_world, world)
    measure_neighbors(quiz_states, states + [r for r in world if r.code != "USA"])
    for region in quiz_world + quiz_states:
        extent = max(region.frame[2], region.frame[3])
        reach = (extent + region.nearest_km / EARTH_RADIUS_KM) * 1.15
        region.frame_min = max(MIN_FRAME[region.layer], reach if reach <= MAX_FRAME_FOR_CONTEXT else REMOTE_FRAME)


# MARK: Flags


def _lab(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float64) / 255
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = linear @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]])
    xyz /= np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def prepare_flags(regions: list[Region]) -> None:
    """Re-encodes flags as WebP and finds each flag's lookalikes."""
    downloads = flag_images({r.code: r.place.flag_file for r in regions})
    signatures = []
    for region in regions:
        png, region.flag_license = downloads[region.code]
        image = Image.open(BytesIO(png))
        image.load()
        image = image.convert("RGBA")
        scale = FLAG_MAX_SIDE / max(image.size)
        if scale < 1:
            image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
        region.flag_size = image.size
        alpha = np.asarray(image.getchannel("A"))
        if alpha.min() == 255:
            image = image.convert("RGB")
        lossless, lossy = BytesIO(), BytesIO()
        image.save(lossless, "WEBP", lossless=True, method=6)
        image.save(lossy, "WEBP", quality=92, method=6)
        region.flag = lossless.getvalue() if lossless.tell() <= 1.5 * lossy.tell() else lossy.getvalue()
        flat = Image.new("RGB", image.size, "white")
        flat.paste(image, mask=image.getchannel("A") if image.mode == "RGBA" else None)
        signatures.append(_lab(flat.resize((30, 20), Image.Resampling.BOX)))
    # A flag mirrored or flipped (Ireland and Cote d'Ivoire, Poland and Indonesia) is a lookalike.
    variants = [[s, s[:, ::-1], s[::-1, :], s[::-1, ::-1]] for s in signatures]
    count = len(regions)
    distance = np.zeros((count, count))
    for i in range(count):
        for j in range(i + 1, count):
            d = min(float(np.linalg.norm(variants[i][0] - v, axis=-1).mean()) for v in variants[j])
            distance[i, j] = distance[j, i] = d
    for i, region in enumerate(regions):
        order = [j for j in np.argsort(distance[i], kind="stable") if j != i]
        region.lookalikes = [regions[j] for j in order[:LOOKALIKES_KEPT]]
        region.distinctiveness = float(np.mean(distance[i, order[:3]]))


# MARK: Items and difficulty


def giveaway(place: Place) -> bool:
    """True when the capital's name contains the place's name or the reverse."""
    capital, name = place.capital.casefold(), place.name.casefold()
    return capital in name or name in capital


def build_items(world: list[Region], states: list[Region]) -> list[Item]:
    countries = [r for r in world if r.place]
    us_states = [r for r in states if r.place]
    titles = {r.place.article for r in countries + us_states}
    titles |= {r.place.capital_article for r in countries + us_states if r.place.capital_article}
    views = pageviews(titles)

    def log_views(title: str) -> float:
        return math.log10(max(views[title], 1))

    decoy_views = decoy_pageviews(countries + us_states)
    items = []
    for region in countries:
        familiarity = log_views(region.place.article)
        items.append(Item("country_map", region, familiarity + AREA_WEIGHT * math.log10(region.area_km2)))
        items.append(Item("country_flag", region, familiarity + DISTINCT_FLAG_WEIGHT * math.log10(region.distinctiveness)))
    for region in us_states:
        items.append(Item("state_map", region, log_views(region.place.article) + AREA_WEIGHT * math.log10(region.area_km2)))
    for region in countries + us_states:
        place = region.place
        if not place.capital or giveaway(place):
            continue
        own = log_views(place.capital_article)
        rival = max((decoy_views.get(d, 0.0) for d in place.decoys), default=0.0)
        score = own - DECOY_WEIGHT * max(0.0, rival - own) + 0.3 * log_views(place.article)
        items.append(Item("state_capital" if region.layer == "states" else "country_capital", region, score))

    for kind in ITEM_KINDS:
        group = sorted((i for i in items if i.kind == kind), key=lambda i: (-i.score, i.region.code))
        for rank, item in enumerate(group):
            item.difficulty = 1 + rank * 5 // len(group)
    return items


def decoy_pageviews(regions: list[Region]) -> dict[str, float]:
    """Log pageviews of decoy cities, looked up by "City" or "City, State"."""
    titles = {}
    for region in regions:
        for decoy in region.place.decoys:
            if region.layer == "states" and decoy not in NO_STATE_SUFFIX:
                titles[decoy] = f"{decoy}, {region.place.name}"
            else:
                titles[decoy] = DECOY_ARTICLES.get(decoy, decoy)
    views = pageviews(set(titles.values()))
    return {decoy: math.log10(max(views[title], 1)) for decoy, title in titles.items()}


# US decoy cities whose Wikipedia article is the bare name rather than "City, State".
NO_STATE_SUFFIX = {
    "Los Angeles", "San Francisco", "Chicago", "New Orleans", "Baltimore", "Detroit", "Minneapolis", "St. Louis",
    "Las Vegas", "New York City", "Philadelphia", "Pittsburgh", "Houston", "Dallas", "Seattle", "Milwaukee", "Miami",
    "Cleveland", "Cincinnati",
}
# Other decoys whose article title differs from the city's name.
DECOY_ARTICLES = {"Cork": "Cork (city)"}


# MARK: Encoding and entry point


def encode_shape(geometry: MultiPolygon) -> bytes:
    """Little-endian: ring count, then per ring a point count and Float32 lon/lat pairs.

    Rings of every part (outer edges and holes) are listed together; the app fills
    them with the even-odd rule. The closing point of each ring is not repeated.
    """
    rings = []
    for polygon in shapely.get_parts(geometry):
        for ring in [polygon.exterior, *polygon.interiors]:
            coords = np.asarray(ring.coords, dtype=np.float32)[:-1]
            if len(coords) >= 3:
                rings.append(coords)
    chunks = [struct.pack("<I", len(rings))]
    for coords in rings:
        chunks.append(struct.pack("<I", len(coords)))
        chunks.append(coords.astype("<f4").tobytes())
    return b"".join(chunks)


def build() -> Atlas:
    countries = read_places(COUNTRIES_CSV)
    states = read_places(STATES_CSV)
    print("  geography: loading Natural Earth")
    world = load_world(countries)
    by_code = {r.code: r for r in world}
    for place, ((lon, lat), code) in POLICY_CHECKS.items():
        assert by_code[code].geometry.contains(shapely.Point(lon, lat)), f"{place} should be in {code}"
    us_states = load_states(states)
    print("  geography: simplifying and framing")
    prepare_regions(world, us_states)
    print("  geography: flags")
    prepare_flags([r for r in world if r.place])
    items = build_items(world, us_states)
    counts = {kind: sum(1 for i in items if i.kind == kind) for kind in ITEM_KINDS}
    return Atlas(world + us_states, items, counts)


if __name__ == "__main__":
    # Diagnostics: python geography.py [kind] prints the items of a kind by level.
    atlas = build()
    print(atlas.counts)
    fine = sum(len(encode_shape(r.fine)) for r in atlas.regions) / 1e6
    coarse = sum(len(encode_shape(r.coarse)) for r in atlas.regions) / 1e6
    flags = sum(len(r.flag or b"") for r in atlas.regions) / 1e6
    print(f"shapes: fine {fine:.1f} MB, coarse {coarse:.1f} MB; flags {flags:.1f} MB")
    kinds = [a for a in sys.argv[1:] if a in ITEM_KINDS] or list(ITEM_KINDS)
    for kind in kinds:
        print(f"\n== {kind}")
        for level in range(1, 6):
            names = [i.region.place.name for i in sorted(atlas.items, key=lambda i: -i.score)
                     if i.kind == kind and i.difficulty == level]
            print(f"  L{level} ({len(names)}): {', '.join(names)}")
