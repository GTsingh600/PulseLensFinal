import numpy as np
import pytest

from pulselens.vision.face import regions_from_landmarks
from pulselens.vision.frames import region_means
from pulselens.vision.linearize import linear_to_srgb, srgb_to_linear
from tests.fixtures.synth import H, W, synthetic_landmarks


def test_linearize_known_values_and_round_trip() -> None:
    assert srgb_to_linear(np.array([0.0, 1.0])).tolist() == [0.0, 1.0]
    assert srgb_to_linear(np.array([0.5]))[0] == pytest.approx(0.21404, abs=1e-5)
    x = np.linspace(0, 1, 101)
    assert np.allclose(linear_to_srgb(srgb_to_linear(x)), x)


def test_linearize_accepts_uint8_images() -> None:
    img = np.array([[[0, 128, 255]]], dtype=np.uint8)
    out = srgb_to_linear(img)
    assert out.dtype == np.float64
    assert out[0, 0, 0] == 0.0 and out[0, 0, 2] == 1.0
    assert out[0, 0, 1] == pytest.approx(srgb_to_linear(np.array([128 / 255]))[0])


def test_neck_box_follows_spec_geometry() -> None:
    r = regions_from_landmarks(synthetic_landmarks(chin_y=150), W, H)
    # face 80 wide, 110 tall: neck 0.6 widths wide, from 0.05 to 0.45 heights below the chin
    assert (r.neck.x0, r.neck.x1) == pytest.approx((160 - 24, 160 + 24))
    assert (r.neck.y0, r.neck.y1) == pytest.approx((150 + 5.5, 150 + 49.5))
    assert r.neck_coverage == pytest.approx(1.0)


def test_neck_box_is_clipped_and_reports_coverage() -> None:
    partly = regions_from_landmarks(synthetic_landmarks(chin_y=210), W, H)  # box runs from 215.5 to 259.5
    assert partly.neck.y1 == H
    assert partly.neck_coverage == pytest.approx((H - 215.5) / 44, abs=1e-6)
    gone = regions_from_landmarks(synthetic_landmarks(chin_y=236), W, H)
    assert gone.neck_coverage < 0.1


def test_skin_regions_sit_inside_the_face_and_avoid_eyes_and_lips() -> None:
    r = regions_from_landmarks(synthetic_landmarks(), W, H)
    eye_y = 40 + 44
    lip_y = 40 + 88
    for b in r.skin:
        assert r.face_box.x0 <= b.x0 < b.x1 <= r.face_box.x1
        assert r.face_box.y0 <= b.y0 < b.y1 <= r.face_box.y1
        assert b.area > 0
    assert r.forehead.y1 < 40 + 21  # above the brows
    for cheek in (r.cheek_left, r.cheek_right):
        assert cheek.y0 > eye_y and cheek.y1 < lip_y
    assert r.cheek_left.x1 <= 160 <= r.cheek_right.x0  # image left and image right


def test_region_means_and_background_mask() -> None:
    img = np.full((H, W, 3), 0.2)
    img[40:150, 120:200] = 0.6  # face
    img[150:, 130:190] = 0.9  # neck and body
    r = regions_from_landmarks(synthetic_landmarks(), W, H)
    means = region_means(img, r)
    assert means["skin"][0] == pytest.approx([0.6, 0.6, 0.6])
    assert means["neck"][0] == pytest.approx([0.9, 0.9, 0.9])
    assert means["background"][0] == pytest.approx([0.2, 0.2, 0.2])  # dilated face box and body block excluded
    assert means["neck"][1] == pytest.approx(1.0)


def test_region_means_without_a_face() -> None:
    means = region_means(np.full((H, W, 3), 0.3), None)
    assert means["skin"][1] == 0 and means["neck"][1] == 0
    assert means["background"][0] == pytest.approx([0.3, 0.3, 0.3])
