import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { LineStringGeometry } from "../types";

// MapLibre requires a WebGL context that jsdom lacks, so we mock it. The mock
// records construction and exposes the control/event API MapView touches. The
// test focuses on MapView's rendered states rather than actual tiles.
vi.mock("maplibre-gl", () => {
  class FakeMap {
    on() {}
    once() {}
    addControl() {}
    addSource() {}
    addLayer() {}
    getSource() {
      return undefined;
    }
    fitBounds() {}
    remove() {}
  }
  class FakeLngLatBounds {
    extend() {
      return this;
    }
  }
  return {
    default: {
      Map: FakeMap,
      NavigationControl: class {},
      LngLatBounds: FakeLngLatBounds,
    },
  };
});

// jsdom has no CSS import handling; the map stylesheet import is a no-op here.
vi.mock("maplibre-gl/dist/maplibre-gl.css", () => ({}));

import { MapView } from "./MapView";

const geometry: LineStringGeometry = {
  type: "LineString",
  coordinates: [
    [-122.4, 37.7],
    [-122.3, 37.8],
  ],
};

describe("MapView states", () => {
  it("prompts to select a candidate when nothing is chosen", () => {
    render(<MapView geometry={null} selectedTrackId={null} />);
    expect(screen.getByText(/Select a review candidate/i)).toBeInTheDocument();
  });

  it("shows a loading state while geometry loads", () => {
    render(<MapView geometry={null} selectedTrackId="trk-a" loading />);
    expect(screen.getByText(/Loading track geometry/i)).toBeInTheDocument();
  });

  it("shows an error state when geometry is unavailable", () => {
    render(
      <MapView
        geometry={null}
        selectedTrackId="trk-a"
        error="No track geometry available."
      />,
    );
    expect(screen.getByText(/Track geometry unavailable/i)).toBeInTheDocument();
  });

  it("hides the overlay once geometry is present", () => {
    render(<MapView geometry={geometry} selectedTrackId="trk-a" />);
    expect(screen.queryByText(/Select a review candidate/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Loading track geometry/i)).not.toBeInTheDocument();
  });
});
