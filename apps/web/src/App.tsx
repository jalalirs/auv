import { Loading, Shell } from "./components/Shell";
import { match, usePath } from "./router";
import { Catalogue } from "./routes/Catalogue";
import { City } from "./routes/City";
import { Layer } from "./routes/Layer";
import { Refusals } from "./routes/Refusals";
import { SignIn } from "./routes/SignIn";
import { Version } from "./routes/Version";
import { Work, WorkDetail } from "./routes/Work";
import { World } from "./routes/World";
import { SessionProvider, useSession } from "./session";

export function App() {
  return (
    <SessionProvider>
      <Routes />
    </SessionProvider>
  );
}

function Routes() {
  const { status } = useSession();
  const path = usePath();

  // There is no anonymous read, so nothing at all is shown until the platform
  // has said who is asking.
  if (status === "checking") {
    return (
      <div className="signin">
        <Loading what="your session" />
      </div>
    );
  }
  if (status === "signed-out") {
    return <SignIn />;
  }

  return <Shell>{screenFor(path)}</Shell>;
}

function screenFor(path: string) {
  const version = match("/layers/:layerId/versions/:versionId", path);
  if (version) {
    return <Version layerId={version["layerId"]!} versionId={version["versionId"]!} />;
  }

  const layer = match("/layers/:layerId", path);
  if (layer) return <Layer layerId={layer["layerId"]!} />;

  const city = match("/cities/:cityId", path);
  if (city) return <City cityId={city["cityId"]!} />;

  const job = match("/work/:jobId", path);
  if (job) return <WorkDetail jobId={job["jobId"]!} />;

  if (match("/work", path)) return <Work />;
  if (match("/world", path)) return <World />;
  if (match("/refusals", path)) return <Refusals />;
  if (match("/", path)) return <Catalogue />;

  return (
    <div className="page">
      <h1>Nothing here</h1>
      <p className="quiet">There is no screen at this address.</p>
    </div>
  );
}
