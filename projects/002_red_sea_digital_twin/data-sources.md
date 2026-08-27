# Initial data sources

Discovery does not authorize redistribution. Each source must receive a local
manifest recording access date, license, citation, checksum, coordinate
metadata, and allowed uses before its data enters the pipeline.

| Source | Candidate use | Initial status |
| --- | --- | --- |
| [Reefs4D](https://zenodo.org/records/14616671) | Seven Gulf of Aqaba reefs at three survey times | preferred M1 geometry candidate; verify file-level license |
| [Smithsonian Corals](https://3d.si.edu/corals) | Open-access coral specimen models, including Saudi Red Sea material | useful semantic/specimen assets; not a site reconstruction |
| [NOAA SfM procedures](https://www.fisheries.noaa.gov/resource/document/processing-photomosaic-imagery-coral-reefs-using-structure-motion-standard) | Field acquisition and processing protocol | methods reference |
| [Sofar Spotter API](https://docs.sofarocean.com/spotter-and-smart-mooring/spotter-data) | Waves, wind, surface temperature, position, device state | requires an owned/shared device and API token |
| [Sofar Smart Mooring API](https://docs.sofarocean.com/spotter-and-smart-mooring/smart-mooring-sensor-data) | Subsurface sensor profiles | future authorized field integration |
| [KAUST integrated Red Sea modeling](https://climatics.kaust.edu.sa/old/towards-an-end-to-end-analysis-and-prediction-system-for-weather-climate-and-marine-applications-in-the-red-sea) | Regional atmosphere, ocean, wave, ecosystem, and transport products | partnership/access investigation |

## Required manifest fields

- stable source identifier and retrieval URL;
- creator, citation, and license;
- retrieval timestamp and cryptographic checksum;
- original coordinate reference system, vertical datum, units, and time basis;
- spatial and temporal coverage;
- processing software, parameters, and derived-file lineage;
- access restrictions and redistribution policy; and
- known quality limitations and uncertainty.
