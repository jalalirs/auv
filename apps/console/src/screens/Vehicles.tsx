import { useState } from "react";

import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Tag, When } from "./parts.js";
import { AssetDetail } from "./Places.js";

/** The vehicles the platform publishes, and who may fly them. */
export function Vehicles() {
  const [opened, setOpened] = useState<string | null>(null);
  const vehicles = useAsked(() => api.vehicles(), []);

  return (
    <>
      <h2>Vehicles</h2>
      <p className="lede">
        Vehicles are the platform's to publish and to grant. What a person
        brings is autonomy, not a hull. A vehicle version must state how it
        moves before it can be published, so that nothing is ever flown by a
        model that does not exist.
      </p>

      <Answered
        asked={vehicles}
        empty={{
          of: (value) => value.vehicles.length === 0,
          say: "No vehicle is visible to you. Vehicles you have not been granted are not listed, and undiscoverable ones are not listed at all.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Handle</th><th>Name</th><th>Maker</th><th>Listing</th><th>Published</th></tr>
              </thead>
              <tbody>
                {value.vehicles.map((vehicle) => (
                  <tr key={vehicle.id}>
                    <td className="mono">
                      <a href="#" onClick={(event) => {
                        event.preventDefault();
                        setOpened(opened === vehicle.id ? null : vehicle.id);
                      }}>{vehicle.slug}</a>
                    </td>
                    <td>{vehicle.name}</td>
                    <td>{vehicle.manufacturer || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                    <td>
                      {vehicle.discoverable
                        ? <Tag kind="idle">discoverable</Tag>
                        : <Tag kind="accent">granted only</Tag>}
                    </td>
                    <td><When value={vehicle.createdAt} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>

      {opened && <AssetDetail
        key={opened}
        id={opened}
        versions={() => api.vehicleVersions(opened)}
        grants={() => api.vehicleGrants(opened)}
      />}
    </>
  );
}
