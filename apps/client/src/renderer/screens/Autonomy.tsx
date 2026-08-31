// What flies the vehicle.

import { Empty, PageHead } from "./parts.js";

export function Autonomy(): React.JSX.Element {
  return (
    <>
      <PageHead title="Autonomy"
        says="Your stack, in a container, pinned by digest. It talks ROS 2 to the vehicle exactly as it would to a real one, and imports nothing of ours — the same binary should run in a tank and in the sea." />
      <section>
        <h2>How it works today</h2>
        <Empty title="Register a stack from the console" soon="in the console, not here">
          An autonomy stack is an image and a digest. The platform checks what it
          subscribes to against the vehicle's topic contract before a dive is
          admitted, so a stack asking for a sensor the vehicle does not carry is
          refused at the door rather than left waiting for a message that never
          comes.
        </Empty>
      </section>
      <section>
        <h2>Coming</h2>
        <Empty title="Push a stack from here" soon="not built yet">
          Build, push and pin without leaving the application, and see which dives
          ran which digest.
        </Empty>
      </section>
    </>
  );
}
