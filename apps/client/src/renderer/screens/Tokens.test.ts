// The address and the block a person pastes into their assistant.
//
// Both derived rather than typed, because a person copying an MCP config out of
// a settings page should be copying something that works, not something that
// needs the box's address filled in by hand.

import { describe, expect, it } from "vitest";

import { mcpAddressFor, mcpConfig } from "./Tokens.js";

describe("the MCP address", () => {
  it("is the platform's host on the MCP server's port", () => {
    expect(mcpAddressFor("http://100.76.65.1:18080")).toBe("http://100.76.65.1:18083/mcp");
    expect(mcpAddressFor("https://box.tail1234.ts.net:18080/")).toBe("https://box.tail1234.ts.net:18083/mcp");
  });

  it("says what to fill in when nobody remembered where the platform is", () => {
    expect(mcpAddressFor(null)).toContain("<the box>");
    expect(mcpAddressFor("not a url")).toContain("<the box>");
  });
});

describe("the block to paste", () => {
  it("is an HTTP server with the token as a Bearer", () => {
    const said = JSON.parse(mcpConfig("http://h:18083/mcp", "cc_abc"));
    const server = said.mcpServers["coral-city"];
    expect(server.type).toBe("http");
    expect(server.url).toBe("http://h:18083/mcp");
    expect(server.headers.Authorization).toBe("Bearer cc_abc");
  });
});
