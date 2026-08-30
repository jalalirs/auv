import { useState } from "react";

import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Digest, Tag, When } from "./parts.js";
import { Grants } from "./Access.js";

/** The places a dive can happen in, and who may enter them. */
export function Places() {
  const [opened, setOpened] = useState<string | null>(null);
  const cities = useAsked(() => api.cities(), []);

  return (
    <>
      <h2>Places</h2>
      <p className="lede">
        A place exists at the platform and outlives the institutions granted
        access to it. One that is neither discoverable nor granted to you is not
        listed here, and is indistinguishable from one that does not exist.
      </p>

      <Answered
        asked={cities}
        empty={{
          of: (value) => value.cities.length === 0,
          say: "No place is visible to you. Places you have not been granted are not listed, and undiscoverable places are not listed at all.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Handle</th><th>Name</th><th>Vertical datum</th>
                  <th>Listing</th><th>Founded</th>
                </tr>
              </thead>
              <tbody>
                {value.cities.map((city) => (
                  <tr key={city.id}>
                    <td className="mono">
                      <a href="#" onClick={(event) => {
                        event.preventDefault();
                        setOpened(opened === city.id ? null : city.id);
                      }}>{city.slug}</a>
                    </td>
                    <td>{city.name}</td>
                    <td>{city.verticalDatum}</td>
                    <td>
                      {city.discoverable
                        ? <Tag kind="idle">discoverable</Tag>
                        : <Tag kind="accent">granted only</Tag>}
                    </td>
                    <td><When value={city.createdAt} /></td>
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
        noun="place"
        versions={() => api.cityVersions(opened)}
        grants={() => api.cityGrants(opened)}
        grantTo={(kind, subject, role) => api.grantCity(opened, kind, subject, role)}
        revokeFrom={(bindingId) => api.revokeCityGrant(opened, bindingId)}
      />}
    </>
  );
}

/** A place's or a vehicle's packages, and who holds a grant on it. */
export function AssetDetail({
  id, noun, versions, grants, grantTo, revokeFrom,
}: {
  id: string;
  noun: string;
  versions: () => Promise<{ versions: import("../api/client.js").AssetVersion[] }>;
  grants: () => Promise<{ grants: import("../api/client.js").Binding[] }>;
  grantTo: (kind: string, subject: string, role: string) => Promise<import("../api/client.js").Binding>;
  revokeFrom: (bindingId: string) => Promise<void>;
}) {
  const packaged = useAsked(versions, [id]);

  return (
    <>
      <h3>Packages</h3>
      <Answered
        asked={packaged}
        empty={{
          of: (value) => value.versions.length === 0,
          say: "Nothing has been packaged for this yet. A dive names a published package, so until there is one, nothing can be flown here.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead>
                <tr><th>#</th><th>Label</th><th>Digest</th><th>Size</th><th>State</th><th>Recorded</th></tr>
              </thead>
              <tbody>
                {value.versions.map((version) => (
                  <tr key={version.id}>
                    <td className="num">{version.ordinal}</td>
                    <td>{version.label || <span style={{ color: "var(--muted)" }}>unlabelled</span>}</td>
                    <td><Digest value={version.digest} /></td>
                    <td className="num">{(version.totalBytes / 1024).toFixed(1)} KiB</td>
                    <td>
                      {version.publishedAt
                        ? <Tag kind="good">published</Tag>
                        : <Tag kind="warn">draft</Tag>}
                    </td>
                    <td><When value={version.createdAt} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>

      <Grants
        assetId={id}
        noun={noun}
        grants={grants}
        grant={(kind, subject, role) => grantTo(kind, subject, role)}
        revoke={revokeFrom}
      />
    </>
  );
}
