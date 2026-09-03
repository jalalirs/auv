// The six tasks a dive can be for.
//
// From docs/plan/todo.md, item 4. Each says what it asks of the vehicle and
// what it is judged on, because a task without a criterion is a suggestion.
// The platform does not evaluate them yet; a dive can be defined for one now
// so that the record says what the dive was for, and the score arrives when
// item 4 does.

export interface Task {
  key: string;
  name: string;
  asks: string;
  judgedOn: string[];
}

export const TASKS: Task[] = [
  { key: "hold", name: "Hold station",
    asks: "Stay at a point and depth for a set time.",
    judgedOn: ["radius held", "depth band held", "duration"] },
  { key: "waypoints", name: "Waypoints",
    asks: "Visit points in order.",
    judgedOn: ["each reached within a radius", "in order", "under a time"] },
  { key: "transect", name: "Transect",
    asks: "Fly a line at a fixed altitude above the seabed.",
    judgedOn: ["altitude band", "heading tolerance", "length covered"] },
  { key: "survey", name: "Survey",
    asks: "Cover a rectangle in passes.",
    judgedOn: ["fraction of the area seen", "overlap", "altitude"] },
  { key: "inspect", name: "Inspect",
    asks: "Approach a structure and circle it.",
    judgedOn: ["object in frame", "from how many bearings", "at what distance"] },
  { key: "return", name: "Return",
    asks: "Come home and surface.",
    judgedOn: ["distance from home", "final depth", "time taken"] },
];

/** A free dive: no task, no score, a person at the controls. */
export const PILOTED: Task = {
  key: "piloted", name: "Piloted",
  asks: "Fly it yourself. No score.",
  judgedOn: [],
};
