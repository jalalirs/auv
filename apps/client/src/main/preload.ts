// Nothing crosses here yet.
//
// The renderer talks to a platform over HTTP and draws what comes back, and
// neither needs privilege. When something does need the main process — keeping
// a session between launches, say — it is added here one call at a time, named
// for what it does rather than exposing a channel to send anything down.
export {};
