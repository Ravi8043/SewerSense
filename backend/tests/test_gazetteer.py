from app.config import HYDERABAD_LAT_RANGE, HYDERABAD_LON_RANGE
from app.gazetteer import LANDMARKS, LOCALITIES, ROADS, SENSITIVE_KINDS, landmark_for, nearest_sensitive, road_for, roads_for_locality, validate_gazetteer

REQUIRED = {"Kukatpally", "KPHB", "Miyapur", "Madhapur", "Gachibowli", "Kondapur", "Ameerpet", "Begumpet", "Secunderabad", "Tarnaka",
            "Uppal", "LB Nagar", "Dilsukhnagar", "Mehdipatnam", "Attapur", "Charminar", "Jubilee Hills", "Malkajgiri"}


def test_gazetteer_is_valid():
    assert validate_gazetteer() == []


def test_required_localities_present():
    assert set(LOCALITIES) == REQUIRED


def test_every_point_inside_hyderabad_bounds():
    points = list(LOCALITIES.values()) + [point for road in ROADS for point in (road.start, road.end)] + [(item.lat, item.lon) for item in LANDMARKS]
    for lat, lon in points:
        assert HYDERABAD_LAT_RANGE[0] <= lat <= HYDERABAD_LAT_RANGE[1]
        assert HYDERABAD_LON_RANGE[0] <= lon <= HYDERABAD_LON_RANGE[1]


def test_roads_and_landmarks_consistent():
    for locality in LOCALITIES:
        assert 3 <= len(roads_for_locality(locality)) <= 5
    for landmark in LANDMARKS:
        road = road_for(landmark.locality, landmark.road)
        assert road is not None
        # Landmarks sit beside their road.
        from app.extract import _point_segment_distance
        assert _point_segment_distance(landmark.lat, landmark.lon, road) < 40


def test_lookups():
    assert road_for("Kukatpally", "road no. 5").name == "Road No. 5"
    assert road_for("Kukatpally", "Nonexistent Road") is None
    assert landmark_for("Kukatpally Government School").kind == "school"
    assert landmark_for("Fake Landmark") is None


def test_hero_road_is_school_adjacent():
    road = road_for("Kukatpally", "Road No. 5")
    found = nearest_sensitive(*road.midpoint, within_m=100)
    assert found is not None and found[0].kind in SENSITIVE_KINDS
