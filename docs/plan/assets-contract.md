# Item 70: assets of every kind. The contract between platform, jobs and client

Agreed with the user 2026-10-22 (steps 1 to 4).

## Kinds
- reef: made from a video (item 67's reconstruction, unchanged).
- structure: type pipeline | platform | wind-foundation | other; meets stands | drapes.
  Made from a 3D model file (glb, gltf, obj), or for a pipeline from a route.
- bathymetry: a seabed survey file (GeoTIFF raster, or xyz/csv soundings lat,lon,depth),
  with its datum and its error in metres.

Every asset, whatever its kind, is made by a job and lives in catalog.reconstruction
(columns added: kind, made_from video|survey|model|route, structure jsonb). Existing rows are reefs.

## The import job (new; same image as reconstruct, IOCEAN_RECONSTRUCT_IMAGE)
    python -m iocean_reconstruct.asset '<brief>'
Briefs:
    {"kind":"bathymetry","file":{"path":"source/<name>","name":"<name>","format":"geotiff|xyz"},
     "datum":"MSL|LAT|...","errorM":0.3}
    {"kind":"structure","type":"platform|wind-foundation|pipeline|other","meets":"stands|drapes",
     "model":{"path":"source/<name>","name":"<name>","format":"glb|gltf|obj","scale":1.0,"up":"y|z"}}
    {"kind":"structure","type":"pipeline","meets":"drapes",
     "route":{"points":[[lat,lon],...],"diameterM":0.5,"burial":0.3}}
Inputs: /work/inputs/source/<name> (the uploaded object; absent for a route).
Output: /work/outputs/asset.tar holding
    asset.json  {"kind","type","meets","madeFrom",
                 "footprint": {"sizeM":[x,y,z]} (a model, local metres, base at z=0, centred in x,y)
                            | {"bbox":[south,west,north,east]} (a survey or a route, degrees),
                 "stats": {...} (survey: depth range, cell size or point count, datum, errorM;
                                 model: triangles, size; route: length m, diameter),
                 "preview":"preview.png"}
    preview.png a picture for the library card
    model.usdc  (a model; metres, z up, base on z=0)
    survey file (a bathymetry asset, as uploaded; named in asset.json "file")
Progress lines on stdout as the other jobs do (tell()).

## Laying structures (lay.py, extended)
Brief assets entries gain "kind":
    {"name","path":"asset/<id>","kind":"structure","meets":"stands",
     "placement":{"lat":..,"lon":..,"headingDeg":..}}      the model stands on the seabed there
    {"name","path":"asset/<id>","kind":"structure","meets":"drapes"}   a route: its own lat,lon
Reef entries are unchanged ("kind" absent or "reef"). A structure needs no resolve search:
its placement is given (stands) or in its own route (drapes). Structures are written into the
place as meshes the runtime draws and vehicles collide with, recorded in site.json.

## Places build
A bathymetry asset chosen as a place's ground goes in the places brief as a "files" entry:
    {"use":"raster"|"points","path":"files/<n>/<file>","name","datum","errorM","citation"}
(packages/places/iocean_places/job.py already reads these).

## Platform
- POST /api/v1/organisations/{org}/assets  {kind, ...brief fields, object (uploaded object id,
  not for a route), label}  starts an import job; returns the asset (state queued).
- GET  /api/v1/organisations/{org}/assets  every kind, newest first, with kind/type/meets/madeFrom,
  state, footprint, stats, preview link.
- GET  /api/v1/assets/{id}
- The reconstruction routes stay (a reef from a video).
- Mapping assets accept structure assets: no resolve job; stands needs placement {lat,lon,headingDeg}.
- A place build accepts "survey": [asset ids] which becomes "files" entries.
- MCP: assets_create, assets_list, assets_status; mappings_create takes structure assets;
  places_build takes survey assets. uploads_start/uploads_confirm exist already.
