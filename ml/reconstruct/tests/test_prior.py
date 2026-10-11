"""The coral library as the prior and the video's points as the measurement,
on a dome whose answer is known."""

import numpy as np

from iocean_reconstruct import prior


def _dome(radius=0.3, height=0.2, rings=24, sides=48):
    verts, faces = [(0.0, 0.0, height)], []
    for r in range(1, rings + 1):
        polar = (np.pi / 2) * r / rings
        for s in range(sides):
            az = 2 * np.pi * s / sides
            verts.append((radius * np.sin(polar) * np.cos(az), radius * np.sin(polar) * np.sin(az),
                          height * np.cos(polar)))
    for s in range(sides):
        faces.append((0, 1 + s, 1 + (s + 1) % sides))
    for r in range(rings - 1):
        for s in range(sides):
            a, b = 1 + r * sides + s, 1 + r * sides + (s + 1) % sides
            faces.append((a, a + sides, b))
            faces.append((b, a + sides, b + sides))
    v = np.array(verts)
    return v, np.array(faces), np.full((len(v), 3), 0.5)


def test_where_the_video_saw_the_colony_it_wins_and_where_it_did_not_the_library_stands():
    v, f, c = _dome()
    prediction = {"vertices": v, "faces": f, "colours": c}
    # The real colony is 5 cm taller on its east half; the camera saw only that half.
    rng = np.random.default_rng(0)
    east = v[v[:, 0] > 0.05]
    lifted = east * [1, 1, (0.25 / 0.2)]
    points = np.repeat(lifted, 6, 0) + rng.normal(0, 0.005, (len(lifted) * 6, 3))
    views = np.full(len(points), 8)
    colours = np.full((len(points), 3), 200, np.uint8)
    post = prior.update(prediction, points, colours, views)
    top_east = np.argmin(np.linalg.norm(v - [0.12, 0.0, 0.18], axis=1))
    west = np.argmin(np.linalg.norm(v - [-0.2, 0.0, 0.14], axis=1))
    assert post["gain"][top_east] > 0.8                          # many frames: the measurement wins
    assert post["vertices"][top_east, 2] > v[top_east, 2] + 0.02  # and the surface moved towards it
    assert post["gain"][west] == 0.0                              # no frame saw it: the prior stands
    assert np.allclose(post["vertices"][west], v[west])
    assert post["posteriorM"][west] == prior.PRIOR_M and post["posteriorM"][top_east] < prior.PRIOR_M / 2


def test_one_frame_moves_the_surface_less_than_many():
    v, f, c = _dome()
    target = v[np.argmin(np.linalg.norm(v - [0.0, 0.0, 0.2], axis=1))]
    points = np.repeat([target + [0, 0, 0.05]], 4, 0)
    colours = np.full((4, 3), 200, np.uint8)
    once = prior.update({"vertices": v, "faces": f, "colours": c}, points, colours, np.full(4, 1))
    often = prior.update({"vertices": v, "faces": f, "colours": c}, points, colours, np.full(4, 30))
    top = np.argmin(np.linalg.norm(v - target, axis=1))
    assert 0 < once["gain"][top] < often["gain"][top]


def test_the_prediction_takes_the_colonys_footprint_and_height():
    v, f, c = _dome(radius=0.5, height=0.5)
    rng = np.random.default_rng(1)
    xy = rng.uniform(-1, 1, (4000, 2)) * [0.4, 0.2]
    colony = np.c_[xy + [3.0, -1.0], rng.uniform(0, 0.3, 4000) - 7.0]
    said = prior.predict((v, f, c), colony, ground_z=-7.0)
    assert abs(said["acrossM"][0] - 0.76) < 0.05 and abs(said["acrossM"][1] - 0.38) < 0.05
    assert abs(said["heightM"] - 0.285) < 0.02
    assert abs(said["vertices"][:, 2].min() + 7.0) < 1e-6


def test_a_colony_seen_only_from_the_side_takes_its_height_from_what_corals_are():
    v, f, c = _dome(radius=0.5, height=0.5)
    rng = np.random.default_rng(2)
    # A wall: 40 cm wide, but its points stand 1.2 m tall, and few frames saw them.
    wall = np.c_[rng.uniform(-0.2, 0.2, 3000), rng.uniform(-0.2, 0.2, 3000), rng.uniform(0, 1.2, 3000)]
    said = prior.predict((v, f, c), wall, ground_z=0.0, views=np.full(3000, 2))
    assert not said["height"]["topSeen"]
    assert said["heightM"] < 0.4                      # the prior's, not the wall's 1.2 m
    seen = prior.predict((v, f, c), wall, ground_z=0.0, views=np.full(3000, 12))
    assert seen["heightM"] > 1.0                      # a top many frames saw is believed


def test_where_the_video_saw_the_surface_the_blend_is_the_video():
    v, f, c = _dome()
    prediction = {"vertices": v, "faces": f, "colours": c}
    # The measured surface: the dome's east half, 1 cm proud of the library's.
    east = np.flatnonzero(v[:, 0] > 0.0)
    seen_v = v.copy()
    seen_v[east] += 0.01 * (v[east] / np.linalg.norm(v[east], axis=1, keepdims=True))
    seen_f = f[np.isin(f, east).all(1)]
    seen_c = np.full((len(v), 3), 0.9)
    post = prior.blend(prediction, seen_v, seen_f, seen_c)
    n_seen = len(np.unique(seen_f))
    assert np.allclose(post["vertices"][:n_seen], seen_v[np.unique(seen_f)])   # the video's own surface
    library_part = post["vertices"][n_seen:]
    west = v[:, 0] < -0.15
    assert np.allclose(library_part[west], v[west])                           # unseen: the library's
    assert len(post["faces"]) < len(seen_f) + len(f)                          # covered library faces gone


def test_a_reconstruction_is_lined_up_with_the_scene_by_its_cameras():
    rng = np.random.default_rng(3)
    truth = rng.uniform(-3, 3, (40, 3))
    angle = 0.7
    rot = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    model = (truth - [1.0, 2.0, 0.5]) @ rot / 1.72              # the model: turned, shifted, a scale of its own
    s, r, t = prior.similarity(model, truth)
    assert abs(s - 1.72) < 1e-6
    assert np.allclose(s * model @ r.T + t, truth, atol=1e-6)


def test_two_colonies_that_touch_are_split_at_their_tops():
    rng = np.random.default_rng(4)
    xy = rng.uniform(-0.5, 0.5, (8000, 2)) * [1.0, 0.3]
    z = np.maximum(0.3 - 2.0 * np.hypot(xy[:, 0] + 0.25, xy[:, 1]), 0) + np.maximum(0.25 - 2.0 * np.hypot(xy[:, 0] - 0.25, xy[:, 1]), 0)
    parts = prior.split_at_peaks(np.c_[xy, z])
    assert len(parts) == 2
    left = min(parts, key=lambda p: xy[p, 0].mean())
    assert (xy[left, 0] < 0.05).mean() > 0.9


def test_what_stands_above_the_seabed_is_found_on_a_slope():
    rng = np.random.default_rng(5)
    xy = rng.uniform(0, 4, (20000, 2))
    z = 0.2 * xy[:, 0] + rng.normal(0, 0.01, len(xy))          # a sloping seabed
    bump = np.hypot(xy[:, 0] - 2, xy[:, 1] - 2) < 0.3
    z[bump] += 0.25
    found = prior.standing(np.c_[xy, z])
    assert found[bump].mean() > 0.8 and found[~bump].mean() < 0.05
