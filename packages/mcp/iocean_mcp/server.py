"""iocean over MCP, on stdio.

Speaks the protocol directly rather than through a framework. There is not much
of it — initialize, tools/list, tools/call — and a dependency that has to be
installed before a customer's assistant can reach the platform is a dependency
between us and the sale.

    IOCEAN_PLATFORM=http://... IOCEAN_EMAIL=... IOCEAN_SECRET=... \
        python -m iocean_mcp

Credentials come from the environment and never from a tool argument: an agent
that can be told a password in a prompt is an agent that can be told somebody
else's.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

from .platform import Platform, Refused
from . import tools

VERSION = "2024-11-05"

# name -> (what it does, what it takes, the function)
TOOLS: dict[str, tuple[str, dict, Callable[..., Any]]] = {
    "places_list": (
        "Every place this session has been granted, with its name and summary.",
        {"type": "object", "properties": {}},
        tools.places_list),
    "places_get": (
        "One place in full: what its ground came from, how deep it is, how deep "
        "that depth is actually calibrated to, its reef and its water. Every "
        "number comes back marked measured, derived, chosen or assumed.",
        {"type": "object",
         "properties": {"place": {"type": "string",
                                  "description": "the place's id or slug"}},
         "required": ["place"]},
        lambda p, place: tools.places_get(p, place)),
    "places_sources": (
        "What a place can be built from: the public sources (the global depth grid, satellite "
        "imagery, the laser altimeter's depths, the coral atlas, the learned depth model) and the "
        "kinds of file an institution can add.",
        {"type": "object", "properties": {}},
        tools.places_sources),
    "places_build": (
        "Found a place of this institution's own, private to it, and build it from its data. "
        "THIS SPENDS TIME ON A MACHINE: the platform fetches the public data and builds the seabed "
        "as a job. Every public source that reaches the place is used unless sources names some. "
        "Ask store_places with the area first: if iOcean already publishes it, store_adopt it, or "
        "build on it with base_place and the institution's own files. Returns at once with a build "
        "to watch with places_build_status; when it is ready it has made a draft version, which "
        "places_publish lets dives use.",
        {"type": "object",
         "properties": {
             "name": {"type": "string", "description": "what to call the place"},
             "centre": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
                        "description": "[latitude, longitude] in degrees, the middle of the square; "
                                       "with base_place, the base's own square is used"},
             "across_m": {"type": "number", "default": 1000, "description": "how wide the square is, 100 m to 20 km"},
             "flat_depth_m": {"type": "number",
                              "description": "a flat seabed at this depth (0.5 to 60 m) instead of any data, "
                                             "said to be assumed: the ground for assets nobody can place"},
             "coral": {"type": "boolean", "description": "false grows no colonies: bare ground round what is put in it"},
             "base_place": {"type": "string",
                            "description": "a place to build on (from store_places): its seabed first, "
                                           "the institution's files laid over it"},
             "sources": {"type": "array", "items": {"type": "string",
                                                    "enum": ["gebco", "sentinel2", "icesat2",
                                                             "allen-coral-atlas", "learned-depth"]},
                         "description": "only these public sources; default every one (none with base_place)"},
             "files": {"type": "array", "items": {"type": "object"},
                       "description": "the institution's own uploaded files: "
                                      "[{\"objectId\": ..., \"use\": \"raster\"|\"points\"|\"ortho\", \"name\": ..., \"errorM\": 0.1}]"},
             "cells": {"type": "integer", "description": "grid cells across, 64 to 2048; default 512"},
             "survey": {"type": "array", "items": {"type": "string"},
                        "description": "ready bathymetry assets (assets_list kind bathymetry) laid in as the "
                                       "ground, with their datum and error; without centre, the first one's square"}},
         "required": ["name"]},
        lambda p, name, centre=None, across_m=1000.0, sources=None, files=None, cells=None, base_place="",
               flat_depth_m=None, coral=None, survey=None:
            tools.places_build(p, name, centre, across_m, sources, files, cells, base_place, flat_depth_m, coral,
                               survey)),
    "store_places": (
        "The iOcean map store: places iOcean built from public data, checked and published, open to "
        "everybody. Each with how deep it is, how much of its depth was measured, its reef, and whether "
        "this institution already has it. Given near (and across_m), only those overlapping that area, "
        "nearest first: ask before building a place, so nobody rebuilds what iOcean publishes.",
        {"type": "object",
         "properties": {
             "near": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
                      "description": "[latitude, longitude] of the middle of an area"},
             "across_m": {"type": "number", "description": "how wide the area is; default 1000"}}},
        lambda p, near=None, across_m=None: tools.store_places(p, near, across_m)),
    "store_adopt": (
        "Use a place from the map store: add it to this institution's places as it is, so dives can fly in it.",
        {"type": "object",
         "properties": {
             "place": {"type": "string", "description": "the store place's id"},
             "org": {"type": "string", "description": "the organisation; this session's own when absent"}},
         "required": ["place"]},
        lambda p, place, org="": tools.store_adopt(p, place, org)),
    "places_build_status": (
        "How a build is going: the steps it has done, and when it is ready, the version it made, "
        "how wrong its depth may be, and which source made how much of it.",
        {"type": "object",
         "properties": {"build": {"type": "string"}},
         "required": ["build"]},
        lambda p, build: tools.places_build_status(p, build)),
    "places_publish": (
        "Publish a version a build made, so dives can fly in it.",
        {"type": "object",
         "properties": {"version": {"type": "string"}},
         "required": ["version"]},
        lambda p, version: tools.places_publish(p, version)),
    "uploads_start": (
        "Place a file (a dive video) in this institution's storage. Give its length and sha256; "
        "the answer says how many parts to PUT and where. Finish with uploads_confirm.",
        {"type": "object",
         "properties": {
             "size_bytes": {"type": "integer", "description": "the file's length in bytes"},
             "sha256": {"type": "string", "description": "the file's sha256, 64 hex characters"},
             "media_type": {"type": "string", "description": "e.g. video/mp4"},
             "org": {"type": "string", "description": "the organisation; this session's own when absent"}},
         "required": ["size_bytes", "sha256"]},
        lambda p, size_bytes, sha256, media_type="", org="": tools.uploads_start(p, size_bytes, sha256, media_type, org)),
    "uploads_confirm": (
        "Finish an upload: the platform checks every byte against the sha256 and returns the object id.",
        {"type": "object",
         "properties": {"grant": {"type": "string"},
                        "org": {"type": "string", "description": "the organisation; this session's own when absent"}},
         "required": ["grant"]},
        lambda p, grant, org="": tools.uploads_confirm(p, grant, org)),
    "reconstructions_create": (
        "Make a reef from a dive video this institution has uploaded: the reef as Gaussian splats, "
        "the ground under it and the path the camera took. THIS SPENDS HOURS ON A GPU. Returns at "
        "once with a reconstruction to watch with reconstructions_status. Laying the reef into a "
        "place is a separate step, not this one.",
        {"type": "object",
         "properties": {
             "video": {"type": "string", "description": "the uploaded video's object id (an .mp4, .mov or .mkv)"},
             "name": {"type": "string", "description": "the video file's own name, e.g. GX010123.MP4"},
             "org": {"type": "string", "description": "the organisation; this session's own when absent"},
             "camera_height_m": {"type": "number",
                                 "description": "how high over the reef the camera was, 0.2 to 20 m; it gives the "
                                                "reef its scale. When absent 1.92 m is assumed, and said to be"},
             "start": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
                       "description": "[latitude, longitude] where the video starts; recorded only"},
             "label": {"type": "string", "description": "what to call it; the video's name when absent"},
             "fps": {"type": "number", "description": "frames read a second, 0.5 to 5; default 2"},
             "tape": {"type": "string", "enum": ["auto", "keep"],
                      "description": "a survey tape in the frames is taken out (auto, the default) or kept"}},
         "required": ["video"]},
        lambda p, video, name="", org="", camera_height_m=None, start=None, label="", fps=None, tape="":
            tools.reconstructions_create(p, video, name, org, camera_height_m, start, label, fps, tape)),
    "reconstructions_status": (
        "How a reconstruction is going: the last steps it reported, and when it is ready, how many "
        "frames it placed, its pieces and splats, and how big the reef is and where its scale came from.",
        {"type": "object",
         "properties": {"reconstruction": {"type": "string"}},
         "required": ["reconstruction"]},
        lambda p, reconstruction: tools.reconstructions_status(p, reconstruction)),
    "reconstructions_list": (
        "This institution's reconstructions, newest first, each with its state.",
        {"type": "object",
         "properties": {"org": {"type": "string", "description": "the organisation; this session's own when absent"}}},
        lambda p, org="": tools.reconstructions_list(p, org)),
    "assets_create": (
        "Make a structure or a seabed survey into an asset, as a job; watch it with assets_status. "
        "bathymetry: an uploaded GeoTIFF or xyz (object), datum, error_m. structure: a type and an "
        "uploaded glb/gltf/obj (object; it stands), or a pipeline route with diameter_m (it drapes). "
        "A reef comes from reconstructions_create.",
        {"type": "object",
         "properties": {
             "kind": {"type": "string", "enum": ["structure", "bathymetry"]},
             "object": {"type": "string", "description": "the uploaded file's object id (uploads_confirm); not for a route"},
             "name": {"type": "string", "description": "the file's own name; its format is read from it"},
             "format": {"type": "string", "enum": ["geotiff", "xyz", "glb", "gltf", "obj"]},
             "type": {"type": "string", "enum": ["pipeline", "platform", "wind-foundation", "other"]},
             "meets": {"type": "string", "enum": ["stands", "drapes"],
                       "description": "default: a model stands, a route drapes"},
             "datum": {"type": "string", "description": "a survey's vertical datum: MSL, LAT, ..."},
             "error_m": {"type": "number", "description": "how wrong a survey's depths may be, in metres"},
             "citation": {"type": "string", "description": "what a place built on the survey cites it as"},
             "scale": {"type": "number", "description": "a model's metres per unit; default 1"},
             "up": {"type": "string", "enum": ["y", "z"], "description": "a model's up axis; default y"},
             "route": {"type": "array", "items": {"type": "array", "items": {"type": "number"}},
                       "description": "a pipeline's [latitude, longitude] points, two or more"},
             "diameter_m": {"type": "number", "description": "a route's pipe diameter"},
             "burial_m": {"type": "number", "description": "how deep a route's pipe is buried"},
             "label": {"type": "string", "description": "what to call it; the file's name when absent"},
             "org": {"type": "string", "description": "the organisation; this session's own when absent"}},
         "required": ["kind"]},
        lambda p, kind, object="", name="", format="", type="", meets="", datum="", error_m=None, citation="",
               scale=None, up="", route=None, diameter_m=None, burial_m=None, label="", org="":
            tools.assets_create(p, kind, object, name, format, type, meets, datum, error_m, citation, scale, up,
                                route, diameter_m, burial_m, label, org)),
    "assets_status": (
        "How an asset is going, and when it is ready: its kind, type, how it meets the seabed, what it "
        "was made from, its footprint and stats.",
        {"type": "object",
         "properties": {"asset": {"type": "string"}},
         "required": ["asset"]},
        lambda p, asset: tools.assets_status(p, asset)),
    "assets_list": (
        "This institution's assets of every kind (reefs, structures, surveys), newest first, each with its state.",
        {"type": "object",
         "properties": {"kind": {"type": "string", "enum": ["reef", "structure", "bathymetry"]},
                        "org": {"type": "string", "description": "the organisation; this session's own when absent"}}},
        lambda p, kind="", org="": tools.assets_list(p, kind, org)),
    "mappings_create": (
        "Put a ready reconstruction onto a place. mode onto: a place that exists (place, its id); a job "
        "searches its seabed near where the video starts for where the reef's ground fits, and waits for "
        "mappings_accept. mode own: a new place of this institution's own (name), a flat seabed built for "
        "it, and the reef laid in its middle. A ready structure asset goes onto a place too, with no "
        "search: placement when it stands, nothing when it drapes. THIS SPENDS TIME ON MACHINES, laying "
        "on a GPU. Either way the place gains a draft version, which places_publish lets dives use.",
        {"type": "object",
         "properties": {
             "reconstruction": {"type": "string"},
             "mode": {"type": "string", "enum": ["onto", "own"]},
             "place": {"type": "string", "description": "onto: the place's id"},
             "version": {"type": "string", "description": "onto: which of its versions; its newest when absent"},
             "start": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
                       "description": "[latitude, longitude] where the video starts; the reconstruction's own when absent"},
             "within_m": {"type": "number", "description": "onto: how far from the start to search; default 400"},
             "depth_m": {"type": "number",
                         "description": "onto: how deep the reef is, a hint; own: the flat seabed's depth, default 8"},
             "count": {"type": "integer", "description": "onto: how many candidates; default 5"},
             "name": {"type": "string", "description": "own: the new place's name"},
             "across_m": {"type": "number", "description": "own: 100 to 2000 m; default 300"},
             "pad": {"type": "string", "enum": ["sand", "coral"], "description": "own: the ground around the reef"},
             "heading_deg": {"type": "number", "description": "own: which way the reef faces; default 0"},
             "assets": {"type": "array",
                        "items": {"oneOf": [{"type": "string"}, {"type": "object"}]},
                        "description": "onto: several at once, each an asset id or "
                                       "{\"asset\": id, \"start\": [lat, lon], \"depth_m\": 8, "
                                       "\"within_m\": 400} for a reef (one search each), or "
                                       "{\"asset\": id, \"placement\": [lat, lon, heading_deg]} for a structure "
                                       "that stands (no search; one that drapes needs nothing); one job lays them all in"},
             "placement": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 3,
                           "description": "onto: [latitude, longitude, heading_deg] for a structure that stands"}},
         "required": ["mode"]},
        lambda p, reconstruction="", mode="onto", place="", version="", start=None, within_m=None, depth_m=None,
               count=None, name="", across_m=None, pad="", heading_deg=None, assets=None, placement=None:
            tools.mappings_create(p, reconstruction, mode, place, version, start, within_m, depth_m,
                                  count, name, across_m, pad, heading_deg, assets, placement)),
    "mappings_status": (
        "How a mapping is going: its state, the steps of each job, and for each reef its state and, "
        "when its search has finished, its candidates (index, where, heading, how well the ground fits, "
        "the seabed's depth there), and which reefs overlap once laid.",
        {"type": "object",
         "properties": {"mapping": {"type": "string"}},
         "required": ["mapping"]},
        lambda p, mapping: tools.mappings_status(p, mapping)),
    "mappings_accept": (
        "Choose where the reef goes and lay it in: a candidate's index from mappings_status, or a "
        "placement by hand (at [x, y] in the place's metres, heading_deg, dz). Only while the mapping is "
        "choosing. THIS SPENDS TIME ON A GPU.",
        {"type": "object",
         "properties": {
             "mapping": {"type": "string"},
             "asset": {"type": "integer", "description": "which reef, by its number in mappings_status; the first when absent"},
             "candidate": {"type": "integer"},
             "at": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
             "heading_deg": {"type": "number"},
             "dz": {"type": "number"}},
         "required": ["mapping"]},
        lambda p, mapping, candidate=None, at=None, heading_deg=None, dz=None, asset=None:
            tools.mappings_accept(p, mapping, candidate, at, heading_deg, dz, asset)),
    "mappings_drop": (
        "Take a reef out of a mapping before the reefs are laid in: one whose search failed, which holds "
        "the rest up until it is dropped, or one not wanted after all.",
        {"type": "object",
         "properties": {"mapping": {"type": "string"}, "asset": {"type": "integer"}},
         "required": ["mapping", "asset"]},
        lambda p, mapping, asset: tools.mappings_drop(p, mapping, asset)),
    "controllers_build": (
        "Deploy controllers from their source: a public GitHub repository (url, and a branch, tag or "
        "commit and a folder) or a zip this institution uploaded. One source may hold several "
        "(controllers_look lists them); every one is built unless controllers names some. THIS SPENDS "
        "TIME ON A MACHINE: the platform builds each one's image, flies it in a tank against the SDK's "
        "topic contract, and registers each that passes as a new build of that controller. Watch it "
        "with controllers_build_status.",
        {"type": "object",
         "properties": {
             "url": {"type": "string", "description": "https://github.com/owner/repository"},
             "ref": {"type": "string", "description": "branch, tag or commit; the repository's default when absent"},
             "path": {"type": "string", "description": "the folder the controller is in"},
             "zip_object": {"type": "string", "description": "an uploaded zip's object id, instead of a repository"},
             "zip_name": {"type": "string", "description": "the zip's file name"},
             "slug": {"type": "string"}, "name": {"type": "string"},
             "controller": {"type": "string",
                            "description": "file.py:Class, one controller said outright for a source with no index"},
             "controllers": {"type": "array", "items": {"type": "string"},
                             "description": "which of the source's controllers to build, by slug; all when absent"},
             "org": {"type": "string", "description": "the organisation; this session's own when absent"}}},
        lambda p, url="", ref="", path="", zip_object="", zip_name="", slug="", name="", controller="", org="",
               controllers=None:
            tools.controllers_build(p, url, ref, path, zip_object, zip_name, slug, name, controller, org,
                                    controllers)),
    "controllers_look": (
        "Which controllers a public GitHub repository holds: what its iocean.toml lists, and any folder "
        "under controllers/ with a controller.py. Cheap: nothing is built.",
        {"type": "object",
         "properties": {"url": {"type": "string"}, "ref": {"type": "string"}, "path": {"type": "string"}},
         "required": ["url"]},
        lambda p, url, ref="", path="": tools.controllers_look(p, url, ref, path)),
    "controllers_build_status": (
        "How a controller build is going: its log, and for each controller it found, its tank check, "
        "why it failed if it did, and the stack it registered.",
        {"type": "object", "properties": {"build": {"type": "string"}}, "required": ["build"]},
        lambda p, build: tools.controllers_build_status(p, build)),
    "controllers_build_again": (
        "Build the same source again; from a repository, the newest commit on the same branch (Pull latest).",
        {"type": "object", "properties": {"build": {"type": "string"}}, "required": ["build"]},
        lambda p, build: tools.controllers_build_again(p, build)),
    "vehicles_list": (
        "Every vehicle, and whether it can actually fly. Read `flyable`: a "
        "package with dynamics and no hull cannot be put in the water however "
        "complete it looks.",
        {"type": "object", "properties": {}},
        tools.vehicles_list),
    "controllers_list": (
        "The autonomy deployed to this institution.",
        {"type": "object", "properties": {}},
        tools.controllers_list),
    "layouts_list": (
        "Every arrangement of a place: where transponders, moorings, plots and "
        "lines have been laid out on it.",
        {"type": "object",
         "properties": {"place": {"type": "string", "description": "id or slug"}},
         "required": ["place"]},
        lambda p, place: tools.layouts_list(p, place)),
    "layouts_create": (
        "Start your own arrangement of a place. Anybody who can look at a "
        "place can have their own scenarios over it; you can only change the "
        "ones you made.",
        {"type": "object",
         "properties": {"place": {"type": "string"}, "name": {"type": "string"},
                        "slug": {"type": "string"}},
         "required": ["place", "name"]},
        lambda p, place, name, slug="": tools.layouts_create(p, place, name, slug)),
    "layouts_get": (
        "What is in the water, as one arrangement says: every thing, its kind "
        "and where it is in site metres.",
        {"type": "object", "properties": {"layout": {"type": "string"}},
         "required": ["layout"]},
        lambda p, layout: tools.layouts_get(p, layout)),
    "layouts_add_line": (
        "Put a row of marks along a line, evenly spaced, and save it as a new "
        "version. Coordinates are [x, y] in site metres: origin at the middle "
        "of the site, +x east, +y north. Returns the arrangement, NOT a "
        "picture — ask layouts_chart to look at it. Depth is the place's "
        "business: a transponder lands on the ground, a buoy floats.",
        {"type": "object",
         "properties": {
             "layout": {"type": "string"},
             "start": {"type": "array", "items": {"type": "number"},
                       "description": "[x, y] in site metres"},
             "end": {"type": "array", "items": {"type": "number"},
                     "description": "[x, y] in site metres"},
             "spacing_m": {"type": "number"},
             "kind": {"type": "string",
                      "description": "transponder, buoy, block, post, ship",
                      "default": "transponder"},
             "name": {"type": "string"}},
         "required": ["layout", "start", "end", "spacing_m"]},
        lambda p, layout, start, end, spacing_m, kind="transponder", name="":
            tools.layouts_add_line(p, layout, start, end, spacing_m, kind, name)),
    "layouts_chart": (
        "A plan view of the place with the arrangement drawn on it, as a PNG. "
        "North up, shaded by depth from the place's own heightfield, with a "
        "scale bar. Cheap: no scene, no camera, no GPU. It answers where "
        "things are, and cannot answer what they look like — a camera view is "
        "a separate operation.",
        {"type": "object", "properties": {"layout": {"type": "string"}},
         "required": ["layout"]},
        lambda p, layout: tools.layouts_chart(p, layout)),
    "dives_list": (
        "Dives this institution has defined, newest first.",
        {"type": "object",
         "properties": {"limit": {"type": "integer", "default": 20}}},
        lambda p, limit=20: tools.dives_list(p, limit)),
    "dives_start": (
        "Put a dive in the water. THIS SPENDS TIME ON A MACHINE — everything "
        "else here only reads. A dive names a place, a vehicle, the sea it was "
        "flown in and what it is for; the sea is required, because a dive whose "
        "water nobody stated cannot be compared with another. `pictures` "
        "renders every frame: a drawn dive runs at about a sixth of real time "
        "and an undrawn one at fifteen times it on the same trajectory, so ask "
        "for pictures only when somebody is going to look.",
        {"type": "object",
         "properties": {
             "place": {"type": "string"},
             "vehicle": {"type": "string",
                         "description": "must have a hull; see vehicles_list"},
             "objective": {"type": "object",
                           "description": "what it is for, e.g. "
                                          "{\"kind\": \"hold-station\", \"seconds\": 120}. It may also say "
                                          "when the dive is — \"day\": {\"localTimeH\": 20, \"dayLengthS\": 300} "
                                          "(fish keep that day; a tank's lights follow it) — and, for a "
                                          "vehicle with no thrusters such as edgetech-2300, the tow that flies "
                                          "it: \"tow\": {\"speedKn\": 4, \"headingDeg\": 90, \"cableOutM\": 300, "
                                          "\"frequencykHz\": 120}; and the camera the vehicle carries, over its own: "
                                          "\"camera\": {\"lens\": \"gopro-wide\", \"port\": \"flat\", \"filter\": \"red\", "
                                          "\"iso\": 1600, \"whiteBalance\": \"daylight\"}"},
             "water": {"type": "string",
                       "enum": ["still", "gentle", "half-knot", "one-knot",
                                "tank-still", "fan-low", "fan-high", "pump", "fan-and-pump"],
                       "description": "the sea; in a tank, the fan blows across the surface and the pump makes a current",
                       "default": "still"},
             "pictures": {"type": "boolean", "default": False},
             "views": {"type": "array", "items": {"type": "string"},
                       "description": "cycle the camera through these, e.g. "
                                      "[\"room\", \"chase\", \"front\", \"overhead\"]; "
                                      "places_get lists a place's own views"},
             "view_every_s": {"type": "number", "default": 4.0,
                              "description": "seconds of dive on each view"},
             "start": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                       "description": "where the vehicle goes in, instead of where the place says a dive "
                                      "begins: [x, y, z] in the site's metres, +x east, +y north, z up "
                                      "(a depth is negative); places_get lists what a place holds and where"},
             "controller": {"type": "string",
                            "description": "what flies it: a deployed controller's slug or id (its newest "
                                           "build; controllers_list), or one of the platform's own by name; "
                                           "the vehicle holds station when absent"},
             "name": {"type": "string"}},
         "required": ["place", "vehicle", "objective"]},
        lambda p, place, vehicle, objective, water="still", pictures=False,
               name="", controller="", views=None, view_every_s=4.0, start=None:
            tools.dives_start(p, place, vehicle, objective, water, controller,
                              name, pictures, views, view_every_s, start)),
    "dives_film": (
        "The path-traced film of a run already flown — one watched live, or "
        "flown by a controller, or flown undrawn for its numbers. THIS SPENDS "
        "TIME ON A MACHINE. The run is flown again from the commands it "
        "recorded, on its seed: the same dive, tick for tick, with pictures. "
        "Only a run that succeeded and kept its commands (flown on or after "
        "4 October 2026) can be filmed.",
        {"type": "object",
         "properties": {"dive": {"type": "string"},
                        "run": {"type": "string",
                                "description": "the run to film; the dive's latest when left out"},
                        "views": {"type": "array", "items": {"type": "string"}},
                        "view_every_s": {"type": "number", "default": 6.0},
                        "film": {"type": "object",
                                 "description": "{fps, width, height, spp, bitrate}; 24 fps 1280x720 16 spp when left out"}},
         "required": ["dive"]},
        lambda p, dive, run=None, views=None, view_every_s=6.0, film=None:
            tools.dives_film(p, dive, run, views, view_every_s, film)),
    "dives_frame": (
        "What the camera saw at a moment of a dive, as an image — and from "
        "where: the position, heading and camera it was seen from come back "
        "beside the picture, because a picture an agent cannot place is one it "
        "will describe as though it knew. Only a dive flown with pictures=true "
        "has frames.",
        {"type": "object",
         "properties": {"dive": {"type": "string"},
                        "at_seconds": {"type": "number",
                                       "description": "seconds into the dive"},
                        "run": {"type": "string"}},
         "required": ["dive", "at_seconds"]},
        lambda p, dive, at_seconds, run=None: tools.dives_frame(p, dive, at_seconds, run)),
    "missions_list": (
        "A place's plans of work. A sweep flies a mission, not a place.",
        {"type": "object", "properties": {"place": {"type": "string"}},
         "required": ["place"]},
        lambda p, place: tools.missions_list(p, place)),
    "sweeps_run": (
        "Fly one mission against every combination of the doubts named, each "
        "several times. THIS SPENDS A LOT: scenarios x repeats dives. Doubts "
        "are named by the app's own catalogue, e.g. "
        "{\"current\": [\"still\", \"one knot\"], "
        "\"the mooring\": [\"as drawn\", \"thirty metres off\"]}. "
        "Dimensions: current, fix, water clarity, trouble, the array, "
        "the mooring, where it goes in, which way it faces, how long. "
        "A best-launch sweep is the last three: e.g. {\"where it goes in\": [\"as planned\", "
        "\"20 m north\", \"20 m east\"], \"which way it faces\": [\"east\", \"north\"]}; "
        "sweeps_findings then ranks them by energy under `cheapest`.",
        {"type": "object",
         "properties": {"mission": {"type": "string"},
                        "vehicle": {"type": "string"},
                        "doubts": {"type": "object"},
                        "repeats": {"type": "integer", "default": 2},
                        "name": {"type": "string"}},
         "required": ["mission", "vehicle", "doubts"]},
        lambda p, mission, vehicle, doubts, repeats=2, name="":
            tools.sweeps_run(p, mission, vehicle, doubts, repeats, name)),
    "sweeps_findings": (
        "What breaks the mission and the one change that saves the most of it, "
        "ranked by how much each doubt changes the outcome. Readable before "
        "the sweep finishes.",
        {"type": "object", "properties": {"sweep": {"type": "string"}},
         "required": ["sweep"]},
        lambda p, sweep: tools.sweeps_findings(p, sweep)),
    "dives_result": (
        "What a run scored. A run that did not finish comes back as unknown "
        "rather than as a score of zero.",
        {"type": "object",
         "properties": {"dive": {"type": "string"}, "run": {"type": "string"}},
         "required": ["dive"]},
        lambda p, dive, run=None: tools.dives_result(p, dive, run)),
    "dives_deliverables": (
        "The geometry a run produced, with the files' contents inline: "
        "track.geojson (where it was AND where it believed it was, as separate "
        "features), coverage.geojson (what was actually seen), planting.geojson, "
        "and provenance.json (what each of those numbers is). Read the contents, "
        "not the links — the links point inside the platform's network.",
        {"type": "object",
         "properties": {"dive": {"type": "string"}, "run": {"type": "string"}},
         "required": ["dive"]},
        lambda p, dive, run=None: tools.dives_deliverables(p, dive, run)),
}


def answer(said: dict, result: Any = None, error: dict | None = None) -> dict:
    out: dict[str, Any] = {"jsonrpc": "2.0", "id": said.get("id")}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    return out


def handle(said: dict, platform: Platform | None,
           no_session: Refused | None = None) -> dict | None:
    method = said.get("method")

    if method == "initialize":
        return answer(said, {
            "protocolVersion": VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "iocean", "version": "0.1.0"},
            "instructions": (
                "iocean: underwater vehicles, real reefs, and dives whose "
                "every number says who measured it. Values arrive as "
                "{value, kind, from} where kind is measured, derived, chosen or "
                "assumed. Report the kind with the number — a derived figure "
                "stated as a measurement is wrong even when the figure is right."),
        })

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "tools/list":
        return answer(said, {"tools": [
            {"name": name, "description": about, "inputSchema": schema}
            for name, (about, schema, _) in TOOLS.items()]})

    if method == "tools/call":
        asked = said.get("params") or {}
        name = asked.get("name")
        if name not in TOOLS:
            return answer(said, error={"code": -32601,
                                       "message": f"no tool called {name!r}"})
        if platform is None:
            # Why there is no session, not a recital of what to set.
            #
            # This said "set IOCEAN_PLATFORM and either IOCEAN_TOKEN or
            # IOCEAN_EMAIL/SECRET" whatever had happened — including when
            # all three were set and the platform had rejected them, which
            # tells an agent to do the thing it already did. The same failure
            # as a vehicle line reading "0 to choose from".
            return answer(said, {"isError": True, "content": [{
                "type": "text",
                "text": json.dumps({"refused": no_session.code,
                                    "why": no_session.message}, indent=1)}]}
                          ) if no_session is not None else answer(said, {
                "isError": True, "content": [{
                    "type": "text",
                    "text": "not signed in: set IOCEAN_PLATFORM and either "
                            "IOCEAN_TOKEN or IOCEAN_EMAIL/SECRET"}]})
        _, _, run = TOOLS[name]
        try:
            got = run(platform, **(asked.get("arguments") or {}))
        except Refused as no:
            # A refusal is the platform working. It comes back as content
            # rather than a protocol error so the agent reads the reason and
            # asks for something else, instead of treating it as a crash.
            return answer(said, {"isError": True, "content": [{
                "type": "text",
                "text": json.dumps({"refused": no.code, "why": no.message},
                                   indent=1)}]})
        except Exception as problem:
            return answer(said, {"isError": True, "content": [{
                "type": "text", "text": f"{type(problem).__name__}: {problem}"}]})
        # An image comes back as an image. MCP carries pictures, and a chart
        # handed over as a base64 string inside a JSON blob is a chart nothing
        # will look at.
        content: list[dict] = []
        if isinstance(got, dict) and "image" in got:
            picture = got.pop("image")
            content.append({"type": "image", "data": picture,
                            "mimeType": "image/png"})
        content.append({"type": "text",
                        "text": json.dumps(got, indent=1, ensure_ascii=False)})
        return answer(said, {"content": content})

    return answer(said, error={"code": -32601, "message": f"no method {method!r}"})


def main() -> int:
    if "--http" in sys.argv:
        at = sys.argv[sys.argv.index("--http") + 1]
        host, _, port = at.rpartition(":")
        serve_http(host or "0.0.0.0", int(port))
        return 0
    no_session: Refused | None = None
    try:
        platform: Platform | None = Platform.from_environment()
    except Refused as why:
        # Serve anyway: an agent listing the tools should see what is here even
        # when nobody has configured a session yet, and be told plainly on the
        # first call rather than watching the server fail to start. The reason
        # is kept, because "not configured" and "the platform rejected those
        # credentials" are different problems with different fixes.
        platform, no_session = None, why

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            said = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle(said, platform, no_session)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


# ── over HTTP, for an agent that is not on this machine ──────────────────────
#
# MCP's streamable HTTP transport, the part of it a tool server needs: one
# endpoint, a JSON-RPC message posted to it, the answer in the response. No
# event stream, because nothing here pushes — every tool answers when asked.
#
# The server holds no credential. Each caller sends its own — `Service
# <principal>:<secret>` or `Bearer <session>` — and it is forwarded to the
# platform untouched, so every agent acts as the principal it was issued as and
# the platform's grants decide what it may do. A shared credential baked into a
# server reachable from the whole tailnet would make every agent the same agent,
# and the audit log would say so.

def _platform_for(header: str | None) -> tuple[Platform | None, Refused | None]:
    base = os.environ.get("IOCEAN_PLATFORM", "http://control-plane:8080")
    if not header:
        return None, Refused(401, "unauthenticated",
                             "send your own credential: make a token in the Coral "
                             "City application under Profile → Tokens for your "
                             "assistant, and send it as Authorization: Bearer cc_…")
    scheme, _, credential = header.partition(" ")
    if scheme.lower() == "service" and credential:
        return Platform(base, service=credential), None
    if scheme.lower() == "bearer" and credential:
        return Platform(base, token=credential), None
    return None, Refused(401, "unauthenticated",
                         "Authorization must be `Service <principal>:<secret>` "
                         "or `Bearer <session>`")


def serve_http(host: str, port: int) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class One(BaseHTTPRequestHandler):
        def _send(self, status: int, body: object | None) -> None:
            raw = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            if body is not None:
                self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {"ok": True, "tools": len(TOOLS)})
                return
            # Nothing is pushed, so there is no stream to open.
            self._send(405, {"error": "POST a JSON-RPC message to /mcp"})

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/mcp":
                self._send(404, {"error": "the endpoint is /mcp"})
                return
            length = int(self.headers.get("content-length") or 0)
            try:
                said = json.loads(self.rfile.read(length) or b"null")
            except json.JSONDecodeError:
                self._send(400, {"jsonrpc": "2.0", "id": None,
                                 "error": {"code": -32700, "message": "not JSON"}})
                return
            platform, why = _platform_for(self.headers.get("authorization"))
            batch = said if isinstance(said, list) else [said]
            replies = [r for r in (handle(one, platform, why) for one in batch
                                   if isinstance(one, dict)) if r is not None]
            if not replies:
                self._send(202, None)       # notifications only
            elif isinstance(said, list):
                self._send(200, replies)
            else:
                self._send(200, replies[0])

        def log_message(self, *_):        # one line per call, not per header
            pass

    print(f"iocean MCP on http://{host}:{port}/mcp, {len(TOOLS)} tools",
          flush=True)
    ThreadingHTTPServer((host, port), One).serve_forever()
