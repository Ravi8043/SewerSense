"""Illustrative Hyderabad gazetteer for the demo.

Locality centroids are approximate. Every road name, road geometry, and landmark
below is a fictional demo fixture — not HMWSSB or GIS data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import HYDERABAD_LAT_RANGE, HYDERABAD_LON_RANGE

GAZETTEER_VERSION = "2"
SENSITIVE_KINDS = frozenset({"school", "hospital", "market"})
METRES_PER_DEG_LAT = 111_111.0


@dataclass(frozen=True)
class Road:
    locality: str
    name: str
    start: tuple[float, float]
    end: tuple[float, float]

    @property
    def midpoint(self) -> tuple[float, float]:
        return ((self.start[0] + self.end[0]) / 2, (self.start[1] + self.end[1]) / 2)

    @property
    def length_m(self) -> float:
        return distance_m(*self.start, *self.end)


@dataclass(frozen=True)
class Landmark:
    locality: str
    road: str
    name: str
    kind: str
    lat: float
    lon: float


def distance_m(lat_one: float, lon_one: float, lat_two: float, lon_two: float) -> float:
    """Haversine distance in metres."""
    radius = 6_371_000
    phi_one, phi_two = math.radians(lat_one), math.radians(lat_two)
    delta_phi, delta_lambda = math.radians(lat_two - lat_one), math.radians(lon_two - lon_one)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi_one) * math.cos(phi_two) * math.sin(delta_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def offset_point(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    return (lat + north_m / METRES_PER_DEG_LAT, lon + east_m / (METRES_PER_DEG_LAT * math.cos(math.radians(lat))))


LOCALITIES: dict[str, tuple[float, float]] = {
    "Kukatpally": (17.4948, 78.3996),
    "KPHB": (17.4867, 78.3911),
    "Miyapur": (17.4961, 78.3570),
    "Madhapur": (17.4483, 78.3908),
    "Gachibowli": (17.4401, 78.3489),
    "Kondapur": (17.4698, 78.3617),
    "Ameerpet": (17.4375, 78.4483),
    "Begumpet": (17.4447, 78.4661),
    "Secunderabad": (17.4399, 78.4983),
    "Tarnaka": (17.4298, 78.5380),
    "Uppal": (17.4058, 78.5591),
    "LB Nagar": (17.3457, 78.5522),
    "Dilsukhnagar": (17.3688, 78.5247),
    "Mehdipatnam": (17.3992, 78.4385),
    "Attapur": (17.3674, 78.4290),
    "Charminar": (17.3616, 78.4747),
    "Jubilee Hills": (17.4326, 78.4071),
    "Malkajgiri": (17.4515, 78.5352),
}

# Informal names residents might use for a locality.
LOCALITY_ALIASES: dict[str, str] = {
    "kukatpalli": "Kukatpally",
    "kphb colony": "KPHB",
    "k.p.h.b": "KPHB",
    "hitech city": "Madhapur",
    "hi-tech city": "Madhapur",
    "secunderabad station": "Secunderabad",
    "dsnr": "Dilsukhnagar",
    "l.b. nagar": "LB Nagar",
    "l b nagar": "LB Nagar",
    "jubilee hills": "Jubilee Hills",
}

# (road name, bearing in degrees from north, length m, centre offset north m, centre offset east m,
#  [(landmark name, kind, fraction along road), ...])
_ROAD_SPECS: dict[str, list[tuple[str, float, float, float, float, list[tuple[str, str, float]]]]] = {
    "Kukatpally": [
        ("Road No. 5", 70, 210, 0, 0, [("Kukatpally Government School", "school", 0.55), ("Sai Baba Temple", "temple", 0.15), ("Road No. 5 Bus Stop", "bus_stop", 0.85)]),
        ("Housing Board Road", 20, 260, 420, -380, [("Kukatpally Metro Station", "metro", 0.3), ("Vivekananda Park", "park", 0.8)]),
        ("Bhagya Nagar Colony Road", 110, 240, -450, 420, [("Bhagya Nagar Community Hall", "community_hall", 0.4), ("Kukatpally Rythu Bazar", "market", 0.9)]),
    ],
    "KPHB": [
        ("KPHB Phase 1 Road", 45, 250, 0, 0, [("KPHB Phase 1 Park", "park", 0.3), ("Lakeview Apartments", "apartments", 0.75)]),
        ("KPHB 4th Phase Main Road", 150, 280, -420, 300, [("Sri Chaitanya School KPHB", "school", 0.6), ("KPHB Water Tank", "utility", 0.2)]),
        ("Forum Mall Road", 85, 230, 380, -350, [("Forum Mall Junction", "junction", 0.5), ("KPHB Bus Depot", "bus_stop", 0.9)]),
    ],
    "Miyapur": [
        ("Miyapur X Roads", 95, 240, 0, 0, [("Miyapur Metro Depot Gate", "metro", 0.2), ("Allwyn Colony Arch", "junction", 0.8)]),
        ("Hafeezpet Road", 30, 220, -400, 380, [("Miyapur Zilla Parishad School", "school", 0.5), ("Hafeezpet Railway Gate", "junction", 0.9)]),
        ("Deepthisri Nagar Main Road", 130, 260, 430, -300, [("Deepthisri Nagar Temple", "temple", 0.35), ("Miyapur Vegetable Market", "market", 0.8)]),
    ],
    "Madhapur": [
        ("Ayyappa Society Road", 60, 250, 0, 0, [("Ayyappa Society Arch", "junction", 0.2), ("Madhapur Police Station", "police", 0.7)]),
        ("Image Gardens Road", 160, 270, 400, 380, [("Image Hospital Madhapur", "hospital", 0.5), ("Shilparamam Gate", "landmark", 0.9)]),
        ("Kavuri Hills Road", 100, 230, -430, -350, [("Kavuri Hills Park", "park", 0.4), ("Kavuri Hills Clubhouse", "community_hall", 0.85)]),
    ],
    "Gachibowli": [
        ("Old Mumbai Highway Service Road", 80, 300, 0, 0, [("Gachibowli Flyover Pillar 12", "junction", 0.3), ("Gachibowli Stadium Gate", "landmark", 0.75)]),
        ("Telecom Nagar Road", 20, 240, 420, 350, [("Telecom Nagar Government School", "school", 0.5), ("Telecom Nagar Park", "park", 0.1)]),
        ("DLF Road", 140, 260, -400, -380, [("DLF Cyber City Gate", "office", 0.3), ("Gachibowli Food Street", "market", 0.8)]),
    ],
    "Kondapur": [
        ("Botanical Garden Road", 50, 280, 0, 0, [("Botanical Garden Gate", "park", 0.2), ("Kondapur Area Hospital", "hospital", 0.8)]),
        ("Raghavendra Colony Road", 120, 230, 400, -360, [("Raghavendra Colony Temple", "temple", 0.5), ("Kondapur Bus Stop", "bus_stop", 0.9)]),
        ("Kothaguda Main Road", 10, 250, -420, 400, [("Kothaguda Junction", "junction", 0.4), ("Kothaguda Apartments", "apartments", 0.85)]),
    ],
    "Ameerpet": [
        ("Satyam Theatre Road", 90, 260, 0, 0, [("Ameerpet Metro Interchange", "metro", 0.3), ("Satyam Theatre", "landmark", 0.7)]),
        ("Mythrivanam Road", 20, 220, 380, 350, [("Mythrivanam Complex", "office", 0.4), ("Ameerpet Vegetable Market", "market", 0.9)]),
        ("Srinivasa Nagar Road", 140, 240, -420, -300, [("Srinivasa Nagar Park", "park", 0.3), ("Ameerpet Community Hall", "community_hall", 0.75)]),
    ],
    "Begumpet": [
        ("Prakash Nagar Road", 60, 250, 0, 0, [("Prakash Nagar Metro Station", "metro", 0.25), ("Begumpet Community Hall", "community_hall", 0.8)]),
        ("Brahmanwadi Road", 150, 230, 400, -380, [("Brahmanwadi Government School", "school", 0.5), ("Brahmanwadi Temple", "temple", 0.1)]),
        ("Airport Road Service Lane", 100, 290, -400, 380, [("Old Airport Gate", "landmark", 0.3), ("Begumpet Railway Station", "station", 0.85)]),
    ],
    "Secunderabad": [
        ("Station Road", 80, 280, 0, 0, [("Secunderabad Station Gate 1", "station", 0.3), ("Clock Tower", "landmark", 0.8)]),
        ("Market Street", 20, 230, 380, 360, [("Monda Market", "market", 0.5), ("St. Mary's Church", "worship", 0.9)]),
        ("SD Road", 130, 260, -420, -380, [("Gandhi Hospital Gate", "hospital", 0.4), ("Paradise Circle", "junction", 0.85)]),
    ],
    "Tarnaka": [
        ("Tarnaka Main Road", 70, 260, 0, 0, [("Tarnaka Metro Station", "metro", 0.3), ("Tarnaka Junction", "junction", 0.8)]),
        ("Lalapet Road", 160, 240, 400, -350, [("Lalapet Bus Stop", "bus_stop", 0.5), ("Lalapet Flyover", "junction", 0.9)]),
        ("Osmania University Road", 30, 270, -420, 380, [("OU Arts College Gate", "school", 0.4), ("Tarnaka Park", "park", 0.8)]),
    ],
    "Uppal": [
        ("Uppal Ring Road", 90, 290, 0, 0, [("Uppal Bus Depot", "bus_stop", 0.25), ("Uppal Stadium Gate", "landmark", 0.75)]),
        ("Ramanthapur Road", 20, 230, 400, 380, [("Ramanthapur Temple", "temple", 0.3), ("Ramanthapur Park", "park", 0.8)]),
        ("Uppal Bhagayath Road", 140, 250, -420, -350, [("Bhagayath Layout Arch", "junction", 0.4), ("Uppal Market", "market", 0.85)]),
    ],
    "LB Nagar": [
        ("LB Nagar Ring Road", 60, 280, 0, 0, [("LB Nagar Metro Station", "metro", 0.3), ("LB Nagar Circle", "junction", 0.8)]),
        ("Kothapet Road", 150, 240, 380, -380, [("Kothapet Fruit Market", "market", 0.5), ("Kothapet Temple", "temple", 0.1)]),
        ("Sagar Ring Road Service Lane", 110, 250, -400, 380, [("Sagar Ring Road Bus Stop", "bus_stop", 0.4), ("Sagar Complex", "office", 0.85)]),
    ],
    "Dilsukhnagar": [
        ("Dilsukhnagar Main Road", 80, 270, 0, 0, [("Dilsukhnagar Bus Stand", "bus_stop", 0.25), ("Konark Theatre", "landmark", 0.75)]),
        ("Chaitanyapuri Road", 30, 230, 400, 360, [("Chaitanyapuri Metro Station", "metro", 0.4), ("Chaitanyapuri Park", "park", 0.85)]),
        ("Kamala Nagar Road", 140, 240, -420, -350, [("Kamala Nagar Government School", "school", 0.5), ("Kamala Nagar Temple", "temple", 0.1)]),
    ],
    "Mehdipatnam": [
        ("Rythu Bazar Road", 90, 260, 0, 0, [("Mehdipatnam Rythu Bazar", "market", 0.5), ("Mehdipatnam Bus Depot", "bus_stop", 0.15)]),
        ("Gudimalkapur Road", 20, 240, 400, -360, [("Gudimalkapur Flower Market", "market", 0.4), ("Gudimalkapur Arch", "junction", 0.9)]),
        ("Asif Nagar Road", 130, 250, -420, 380, [("Asif Nagar Park", "park", 0.3), ("Asif Nagar Community Hall", "community_hall", 0.8)]),
    ],
    "Attapur": [
        ("Pillar No. 120 Road", 70, 260, 0, 0, [("PVNR Expressway Pillar 120", "junction", 0.3), ("Attapur Community Hall", "community_hall", 0.8)]),
        ("Hyderguda Road", 160, 230, 380, 360, [("Hyderguda Temple", "temple", 0.4), ("Hyderguda Bus Stop", "bus_stop", 0.9)]),
        ("Rambagh Road", 20, 240, -420, -380, [("Rambagh Colony Park", "park", 0.5), ("Attapur Apartments", "apartments", 0.85)]),
    ],
    "Charminar": [
        ("Pathargatti Road", 80, 250, 0, 0, [("Pathargatti Market", "market", 0.4), ("Charminar Monument Gate", "landmark", 0.9)]),
        ("Laad Bazaar Lane", 150, 220, 380, -350, [("Laad Bazaar", "market", 0.5), ("Mecca Masjid Gate", "worship", 0.9)]),
        ("Shalibanda Road", 30, 250, -400, 380, [("Shalibanda Clock Tower", "landmark", 0.3), ("Shalibanda Community Hall", "community_hall", 0.8)]),
    ],
    "Jubilee Hills": [
        ("Road No. 36", 70, 280, 0, 0, [("Jubilee Hills Checkpost", "junction", 0.2), ("Road No. 36 Metro Station", "metro", 0.7)]),
        ("Road No. 10", 150, 250, 400, 380, [("Jubilee Hills Public School", "school", 0.5), ("KBR Park Gate", "park", 0.95)]),
        ("Film Nagar Road", 20, 240, -420, -380, [("Film Nagar Temple", "temple", 0.4), ("Film Nagar Community Hall", "community_hall", 0.85)]),
    ],
    "Malkajgiri": [
        ("Malkajgiri Main Road", 60, 260, 0, 0, [("Malkajgiri Railway Station", "station", 0.3), ("Malkajgiri Circle", "junction", 0.8)]),
        ("Anandbagh Road", 140, 240, 400, -380, [("Anandbagh Park", "park", 0.3), ("Anandbagh Area Hospital", "hospital", 0.8)]),
        ("Vinayak Nagar Road", 20, 230, -420, 360, [("Vinayak Nagar Temple", "temple", 0.4), ("Vinayak Nagar Bus Stop", "bus_stop", 0.9)]),
    ],
}


def point_on_road(road: Road, fraction: float) -> tuple[float, float]:
    fraction = min(1.0, max(0.0, fraction))
    return (
        road.start[0] + (road.end[0] - road.start[0]) * fraction,
        road.start[1] + (road.end[1] - road.start[1]) * fraction,
    )


def _build() -> tuple[list[Road], list[Landmark]]:
    roads: list[Road] = []
    landmarks: list[Landmark] = []
    for locality, specs in _ROAD_SPECS.items():
        base_lat, base_lon = LOCALITIES[locality]
        for name, bearing, length, north, east, landmark_specs in specs:
            centre = offset_point(base_lat, base_lon, north, east)
            half_n = math.cos(math.radians(bearing)) * length / 2
            half_e = math.sin(math.radians(bearing)) * length / 2
            road = Road(locality, name, offset_point(*centre, -half_n, -half_e), offset_point(*centre, half_n, half_e))
            roads.append(road)
            for landmark_name, kind, fraction in landmark_specs:
                # Landmarks sit ~15 m off the carriageway, not on its centreline.
                lat, lon = point_on_road(road, fraction)
                lat, lon = offset_point(lat, lon, -math.sin(math.radians(bearing)) * 15, math.cos(math.radians(bearing)) * 15)
                landmarks.append(Landmark(locality, name, landmark_name, kind, round(lat, 6), round(lon, 6)))
    return roads, landmarks


ROADS, LANDMARKS = _build()


def road_for(locality: str | None, name: str | None) -> Road | None:
    if not name:
        return None
    for road in ROADS:
        if road.name.lower() == name.lower() and (not locality or road.locality.lower() == locality.lower()):
            return road
    return None


def landmark_for(name: str | None, locality: str | None = None) -> Landmark | None:
    if not name:
        return None
    for landmark in LANDMARKS:
        if landmark.name.lower() == name.lower() and (not locality or landmark.locality.lower() == locality.lower()):
            return landmark
    return None


def roads_for_locality(locality: str) -> list[Road]:
    return [road for road in ROADS if road.locality == locality]


def landmarks_for_road(locality: str, road: str) -> list[Landmark]:
    return [landmark for landmark in LANDMARKS if landmark.locality == locality and landmark.road == road]


def nearest_sensitive(lat: float, lon: float, within_m: float) -> tuple[Landmark, float] | None:
    """Closest school/hospital/market within `within_m` metres of a point."""
    best: tuple[Landmark, float] | None = None
    for landmark in LANDMARKS:
        if landmark.kind not in SENSITIVE_KINDS:
            continue
        distance = distance_m(lat, lon, landmark.lat, landmark.lon)
        if distance <= within_m and (best is None or distance < best[1]):
            best = (landmark, distance)
    return best


def in_hyderabad_bounds(lat: float, lon: float) -> bool:
    return HYDERABAD_LAT_RANGE[0] <= lat <= HYDERABAD_LAT_RANGE[1] and HYDERABAD_LON_RANGE[0] <= lon <= HYDERABAD_LON_RANGE[1]


def validate_gazetteer() -> list[str]:
    errors: list[str] = []
    for name, (lat, lon) in LOCALITIES.items():
        if not in_hyderabad_bounds(lat, lon):
            errors.append(f"Locality outside Hyderabad bounds: {name}")
    for road in ROADS:
        for point in (road.start, road.end):
            if not in_hyderabad_bounds(*point):
                errors.append(f"Road outside Hyderabad bounds: {road.locality}/{road.name}")
        if not 150 <= road.length_m <= 400:
            errors.append(f"Road length outside 150-400 m: {road.locality}/{road.name} ({road.length_m:.0f} m)")
    for locality in LOCALITIES:
        count = len(roads_for_locality(locality))
        if not 3 <= count <= 5:
            errors.append(f"Locality must have 3-5 roads: {locality}")
    for road in ROADS:
        count = len(landmarks_for_road(road.locality, road.name))
        if not 2 <= count <= 3:
            errors.append(f"Road must have 2-3 landmarks: {road.locality}/{road.name}")
    for landmark in LANDMARKS:
        if not in_hyderabad_bounds(landmark.lat, landmark.lon):
            errors.append(f"Landmark outside Hyderabad bounds: {landmark.name}")
    names = [landmark.name.lower() for landmark in LANDMARKS]
    if len(names) != len(set(names)):
        errors.append("Landmark names must be unique")
    return errors
