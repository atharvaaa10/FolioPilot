import * as React from "react";
import { renderToString } from "react-dom/server";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LocalTime } from "./local-time";

describe("LocalTime component", () => {
  const testTimestamp = 1700000000000; // 2023-11-14T22:13:20.000Z

  it("renderToString outputs placeholder and does not match a clock-like pattern", () => {
    const html = renderToString(<LocalTime timestamp={testTimestamp} />);
    expect(html).toContain("—");
    expect(html).not.toMatch(/\d{1,2}:\d{2}/);
  });

  it("after client mount, it renders the formatted time", () => {
    render(<LocalTime timestamp={testTimestamp} />);
    expect(screen.getByText(/\d{1,2}:\d{2}/)).toBeInTheDocument();
  });

  it("renders placeholder when timestamp is undefined or null", () => {
    const html = renderToString(<LocalTime />);
    expect(html).toContain("—");

    const { container } = render(<LocalTime />);
    expect(container.textContent).toBe("—");
  });
});

