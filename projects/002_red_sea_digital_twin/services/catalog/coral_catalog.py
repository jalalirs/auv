#!/usr/bin/env python3
"""Validate reef-survey manifests and build the deterministic Coral City catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml


ASSET_ID = re.compile(r"^[a-z0-9][a-z0-9._-]+$")
MD5 = re.compile(r"^[a-f0-9]{32}$")
TRUTH_CLASSES = {"observation", "analysis", "forecast", "scenario", "simulation"}


class ManifestError(ValueError):
    """Raised when a source manifest violates the Coral City contract."""


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def require(mapping: dict[str, Any], fields: tuple[str, ...], location: str) -> None:
    missing = [field for field in fields if field not in mapping]
    if missing:
        raise ManifestError(f"{location}: missing {', '.join(missing)}")


def vector3(value: Any, location: str, *, positive: bool = False) -> list[float]:
    if not isinstance(value, list) or len(value) != 3 or not all(isinstance(item, (int, float)) for item in value):
        raise ManifestError(f"{location}: expected three numbers")
    if positive and any(item <= 0 for item in value):
        raise ManifestError(f"{location}: every extent must be positive")
    return [float(item) for item in value]


def validate_manifest(document: dict[str, Any]) -> list[str]:
    require(document, ("schema_version", "asset_id", "truth_class", "source", "license", "site", "files", "geometry", "known_limitations"), "manifest")
    if document["schema_version"] != 1:
        raise ManifestError("schema_version: only version 1 is accepted")
    if not isinstance(document["asset_id"], str) or not ASSET_ID.fullmatch(document["asset_id"]):
        raise ManifestError("asset_id: use lowercase letters, numbers, dots, dashes, or underscores")
    if document["truth_class"] not in TRUTH_CLASSES:
        raise ManifestError(f"truth_class: expected one of {sorted(TRUTH_CLASSES)}")

    source = document["source"]
    require(source, ("title", "record_url", "version", "retrieval_date", "creators"), "source")
    if not str(source["record_url"]).startswith("https://"):
        raise ManifestError("source.record_url: HTTPS is required")
    if not isinstance(source["creators"], list) or not source["creators"]:
        raise ManifestError("source.creators: at least one creator is required")

    rights = document["license"]
    require(rights, ("record_identifier", "project_use", "redistribution", "commercial_use"), "license")

    site = document["site"]
    require(site, ("name", "locality", "survey_period", "depth_range_m", "wgs84_anchor", "vertical_datum"), "site")
    depths = site["depth_range_m"]
    if not isinstance(depths, list) or len(depths) != 2 or not all(isinstance(item, (int, float)) for item in depths):
        raise ManifestError("site.depth_range_m: expected [minimum, maximum]")
    if depths[0] > depths[1]:
        raise ManifestError("site.depth_range_m: minimum exceeds maximum")
    anchor = site["wgs84_anchor"]
    require(anchor, ("latitude_deg", "longitude_deg", "method", "horizontal_uncertainty_m", "survey_grade"), "site.wgs84_anchor")
    if not -90 <= anchor["latitude_deg"] <= 90:
        raise ManifestError("site.wgs84_anchor.latitude_deg: outside WGS84 range")
    if not -180 <= anchor["longitude_deg"] <= 180:
        raise ManifestError("site.wgs84_anchor.longitude_deg: outside WGS84 range")
    if anchor["horizontal_uncertainty_m"] < 0:
        raise ManifestError("site.wgs84_anchor.horizontal_uncertainty_m: cannot be negative")
    if not isinstance(anchor["survey_grade"], bool):
        raise ManifestError("site.wgs84_anchor.survey_grade: expected boolean")

    files = document["files"]
    if not isinstance(files, dict) or not files:
        raise ManifestError("files: at least one immutable source file is required")
    for role, item in files.items():
        require(item, ("name", "url", "bytes", "md5", "format"), f"files.{role}")
        if not str(item["url"]).startswith("https://"):
            raise ManifestError(f"files.{role}.url: HTTPS is required")
        if not isinstance(item["bytes"], int) or item["bytes"] <= 0:
            raise ManifestError(f"files.{role}.bytes: expected a positive integer")
        if not isinstance(item["md5"], str) or not MD5.fullmatch(item["md5"]):
            raise ManifestError(f"files.{role}.md5: expected lowercase MD5")

    geometry = document["geometry"]
    require(geometry, ("units", "up_axis", "bounds_min_m", "bounds_max_m", "extent_m"), "geometry")
    if geometry["units"] != "meters":
        raise ManifestError("geometry.units: Coral City canonical geometry uses meters")
    if geometry["up_axis"] not in {"X", "Y", "Z"}:
        raise ManifestError("geometry.up_axis: expected X, Y, or Z")
    minimum = vector3(geometry["bounds_min_m"], "geometry.bounds_min_m")
    maximum = vector3(geometry["bounds_max_m"], "geometry.bounds_max_m")
    extent = vector3(geometry["extent_m"], "geometry.extent_m", positive=True)
    if any(low >= high for low, high in zip(minimum, maximum, strict=True)):
        raise ManifestError("geometry bounds: every minimum must be below its maximum")
    calculated = [high - low for low, high in zip(minimum, maximum, strict=True)]
    if any(abs(expected - actual) > 0.01 for expected, actual in zip(extent, calculated, strict=True)):
        raise ManifestError("geometry.extent_m: inconsistent with declared bounds by more than 1 cm")

    limitations = document["known_limitations"]
    if not isinstance(limitations, list) or not limitations:
        raise ManifestError("known_limitations: scientific limitations must be explicit")

    blockers: list[str] = []
    if not anchor["survey_grade"]:
        blockers.append("anchor is not survey-grade")
    if str(site["vertical_datum"]).strip().lower() in {"unknown", "unspecified"}:
        blockers.append("vertical datum is unknown")
    if anchor["horizontal_uncertainty_m"] > 5:
        blockers.append("horizontal uncertainty exceeds 5 m")
    return blockers


def load_manifest(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text())
    if not isinstance(document, dict):
        raise ManifestError(f"{path}: manifest root must be an object")
    return document


def catalog_record(path: Path, root: Path) -> dict[str, Any]:
    document = load_manifest(path)
    blockers = validate_manifest(document)
    site = document["site"]
    anchor = site["wgs84_anchor"]
    return {
        "asset_id": document["asset_id"],
        "truth_class": document["truth_class"],
        "title": document["source"]["title"],
        "site": {
            "name": site["name"],
            "locality": site["locality"],
            "survey_period": site["survey_period"],
            "latitude_deg": anchor["latitude_deg"],
            "longitude_deg": anchor["longitude_deg"],
            "horizontal_uncertainty_m": anchor["horizontal_uncertainty_m"],
            "vertical_datum": site["vertical_datum"],
        },
        "source": {
            "record_url": document["source"]["record_url"],
            "record_doi": document["source"].get("record_doi"),
            "version": document["source"]["version"],
        },
        "rights": {
            "identifier": document["license"]["record_identifier"],
            "project_use": document["license"]["project_use"],
        },
        "geometry": {
            "units": document["geometry"]["units"],
            "up_axis": document["geometry"]["up_axis"],
            "extent_m": document["geometry"]["extent_m"],
        },
        "files": sorted(document["files"]),
        "readiness": "blocked" if blockers else "publishable",
        "readiness_blockers": blockers,
        "manifest_path": path.relative_to(root).as_posix(),
        "manifest_sha256": digest(path),
    }


def discover(root: Path) -> list[Path]:
    return sorted((root / "projects/002_red_sea_digital_twin/assets/sources").glob("**/*.yaml"))


def build_catalog(paths: list[Path], root: Path) -> dict[str, Any]:
    records = [catalog_record(path, root) for path in paths]
    identifiers = [record["asset_id"] for record in records]
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        raise ManifestError(f"duplicate asset_id: {', '.join(duplicates)}")
    records.sort(key=lambda item: item["asset_id"])
    return {"schema_version": 1, "record_count": len(records), "records": records}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--output", type=Path)
    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("asset_id")
    args = parser.parse_args()

    root = repo_root()
    try:
        catalog = build_catalog(discover(root), root)
        if args.command == "validate":
            for record in catalog["records"]:
                print(f"VALID  {record['asset_id']}  readiness={record['readiness']}")
                for blocker in record["readiness_blockers"]:
                    print(f"  BLOCKER  {blocker}")
        elif args.command == "build":
            payload = json.dumps(catalog, indent=2, sort_keys=True) + "\n"
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(payload)
                print(args.output)
            else:
                print(payload, end="")
        elif args.command == "show":
            record = next((item for item in catalog["records"] if item["asset_id"] == args.asset_id), None)
            if record is None:
                raise ManifestError(f"unknown asset_id: {args.asset_id}")
            print(json.dumps(record, indent=2, sort_keys=True))
    except (ManifestError, OSError, yaml.YAMLError) as error:
        print(f"ERROR  {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
