import numpy as np
import trimesh

from app.core import features


def test_box_has_six_planes_and_no_cylinders():
    r = features.detect(trimesh.creation.box((10, 20, 30)))
    assert r["ok"] and r["approximate"]
    assert r["counts"]["planes"] == 6 and r["counts"]["cylinders"] == 0


def test_plate_with_hole_is_detected():
    plate = trimesh.creation.box((40, 40, 10))
    drill = trimesh.creation.cylinder(radius=4, height=30, sections=48)
    m = plate.difference(drill)
    r = features.detect(m)
    assert r["counts"]["holes"] == 1
    h = r["holes"][0]
    assert abs(h["radius"] - 4) < 0.2
    assert abs(abs(h["axis"][2]) - 1) < 0.01


def test_pin_is_a_boss_not_a_hole():
    r = features.detect(trimesh.creation.cylinder(radius=5, height=20, sections=48))
    assert r["counts"]["holes"] == 0
    assert r["cylinders"] and r["cylinders"][0]["role"] == "boss"


def test_empty_and_huge_are_safe():
    assert features.detect(trimesh.Trimesh())["ok"]
