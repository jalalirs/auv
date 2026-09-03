// The sea at a place, drawn.
//
// Two sizes: a pill for a card's corner, which says the one number and how
// worried to be; and a panel for a place's own page, which says everything the
// record holds and where each number came from.

import type { SeaRecord } from "../../shared/bridge.js";
import { alertKind, alertName, compassName, leadTemperature, type SeaState } from "../ocean/sea.js";
import { Pill, Row, ago, fixed } from "./common.js";
import { Chart } from "./Chart.js";

export function SeaPill({ sea }: { sea: SeaState }): React.JSX.Element | null {
  if (sea.at === "asking") return <Pill>reading the sea…</Pill>;
  if (sea.at === "none") return <Pill title={`Nobody monitors the sea within ${sea.withinKm} km`}>unmonitored</Pill>;
  if (sea.at !== "known") return null;
  const lead = leadTemperature(sea.record);
  const alert = sea.record.now.alertLevel?.value;
  return (
    <Pill kind={alertKind(alert)}
          title={lead === undefined ? undefined : `${lead.where}, by ${lead.source}; ${alertName(alert) ?? ""}`}>
      {lead === undefined ? "no reading" : `${lead.value.toFixed(1)} °C`}
      {sea.record.site.hasBuoy ? " · buoy" : ""}
    </Pill>
  );
}

function Source({ of }: { of: { source: string; at: string } | undefined }): React.JSX.Element | null {
  if (of === undefined) return null;
  return <em className="source">{of.source === "noaa" ? "satellite" : of.source}, {ago(of.at)}</em>;
}

export function SeaPanel({ sea }: { sea: SeaState }): React.JSX.Element {
  if (sea.at === "nowhere") {
    return <p className="note">This place does not say where it is on the globe, so nothing can be said about its sea.</p>;
  }
  if (sea.at === "asking") return <p className="note">Reading the sea…</p>;
  if (sea.at === "none") return <p className="note">Nobody monitors the sea within {sea.withinKm} km of here.</p>;
  if (sea.at === "unreachable") return <p className="note">Aqualink could not be reached: {sea.why}</p>;
  const { record } = sea;
  return <SeaKnown record={record} />;
}

function SeaKnown({ record }: { record: SeaRecord }): React.JSX.Element {
  const { site, now, days, surveys } = record;
  const alert = now.alertLevel?.value;
  const wind = now.windSpeedMs;
  const wave = now.significantWaveHeightM;
  return (
    <div className="sea-panel">
      <div className="sea-head">
        <div>
          <strong>{site.name}</strong>
          <span>
            {site.hasBuoy ? "a buoy in the water" : "satellite only"} · {Math.round(site.distanceM)} m from the site centre
            {site.depthM === undefined ? "" : ` · ${site.depthM} m deep`}
          </span>
        </div>
        <a href={site.url} target="_blank" rel="noreferrer">on Aqualink ↗</a>
      </div>

      <div className="kvs">
        {now.bottomTemperatureC ? (
          <Row of="water at the bottom" is={<>{fixed(now.bottomTemperatureC.value, 1, " °C")} <Source of={now.bottomTemperatureC} /></>} />
        ) : null}
        {now.topTemperatureC ? (
          <Row of="water at the surface" is={<>{fixed(now.topTemperatureC.value, 1, " °C")} <Source of={now.topTemperatureC} /></>} />
        ) : null}
        <Row of="sea surface, by satellite" is={<>{fixed(now.satelliteTemperatureC?.value, 1, " °C")} <Source of={now.satelliteTemperatureC} /></>} />
        <Row of="against the usual" is={now.sstAnomalyC ? `${now.sstAnomalyC.value >= 0 ? "+" : ""}${now.sstAnomalyC.value.toFixed(1)} °C` : "—"}
             note="Anomaly against the long-term mean for this week of the year" />
        <Row of="heat stress" is={<>{fixed(now.degreeHeatingWeeks?.value, 1, " °C-weeks")} </>}
             note="Degree heating weeks: accumulated heat above the bleaching threshold over twelve weeks. Bleaching likely above 4, severe above 8." />
        <Row of="alert" is={<Pill kind={alertKind(alert)}>{alertName(alert) ?? "—"}</Pill>}
             note="NOAA Coral Reef Watch alert level" />
        {wind ? (
          <Row of="wind" is={`${fixed(wind.value, 1, " m/s")}${now.windDirectionDeg ? ` from ${compassName(now.windDirectionDeg.value)}` : ""}`} />
        ) : null}
        {wave ? (
          <Row of="waves" is={`${fixed(wave.value, 2, " m")}${now.waveMeanPeriodS ? ` every ${now.waveMeanPeriodS.value.toFixed(0)} s` : ""}${now.waveMeanDirectionDeg ? ` from ${compassName(now.waveMeanDirectionDeg.value)}` : ""}`} />
        ) : null}
        {site.maxMonthlyMeanC === undefined ? null : (
          <Row of="bleaching threshold" is={`${(site.maxMonthlyMeanC + 1).toFixed(1)} °C`}
               note="One degree above the warmest month this site normally sees" />
        )}
      </div>

      {days.length > 1 ? (
        <Chart days={days} threshold={site.maxMonthlyMeanC === undefined ? undefined : site.maxMonthlyMeanC + 1} />
      ) : null}

      {surveys.length > 0 ? (
        <div className="surveys">
          <h3>Dives logged here</h3>
          {surveys.slice(0, 6).map((s) => (
            <div className="survey" key={s.id}>
              {s.pictureUrl ? <img src={s.pictureUrl} alt="" loading="lazy" /> : <div className="no-picture" />}
              <div>
                <strong>{s.on}{s.by ? ` · ${s.by}` : ""}</strong>
                <span>
                  {s.temperatureC === undefined ? "" : `${s.temperatureC.toFixed(1)} °C · `}
                  {s.weather ?? ""}{s.observations && s.observations !== "no-data" ? ` · ${s.observations}` : ""}
                </span>
                {s.comments ? <p>{s.comments}</p> : null}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <p className="note fine">
        NOAA Coral Reef Watch and Sofar buoy readings, kept by Aqualink. Fetched {ago(record.fetchedAt)}.
      </p>
    </div>
  );
}
