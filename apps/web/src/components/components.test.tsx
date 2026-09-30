import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AlertList } from "./AlertList";
import { AlertDetail } from "./AlertDetail";
import type { AlertDetail as AlertDetailData, AlertSummary } from "../types";

const sampleAlert: AlertSummary = {
  alert_id: "2024-01-03__isolation_forest__trk-a__w-001",
  track_id: "trk-a",
  date: "2024-01-03",
  ranking_score: 99,
  ranking_method: "isolation_forest",
  rank: 1,
  shortlisted: true,
  explanation_reasons: [],
};

const sampleDetail: AlertDetailData = {
  ...sampleAlert,
  review_status: "unreviewed",
  explanation_reasons: [
    {
      reason_code: "speed_lower",
      feature_group: "speed",
      feature_name: "low_speed_duration",
      observed_value: 1800,
      unit: "s",
      reference_percentile: 0.98,
      direction: "higher",
      severity: 2.1,
      message: "Low-speed duration above background range.",
      attribution_kind: "supporting_evidence",
    },
  ],
  supporting_features: [
    {
      feature_name: "low_speed_duration",
      feature_group: "speed",
      observed_value: 1800,
      unit: "s",
      reference_percentile: 0.98,
    },
  ],
  data_quality: {
    observation_count: 118,
    observed_duration_seconds: 3540,
    max_gap_seconds: 120,
    sog_valid_fraction: 0.99,
    cog_valid_fraction: 0.98,
  },
};

describe("AlertList", () => {
  it("renders ranked rows and fires selection", () => {
    const onSelect = vi.fn();
    render(
      <AlertList alerts={[sampleAlert]} selectedId={null} onSelect={onSelect} />,
    );

    expect(screen.getByText("Review Candidates")).toBeInTheDocument();
    expect(screen.getByText("isolation_forest")).toBeInTheDocument();
    // Score rendered as a percentage.
    expect(screen.getByText("99%")).toBeInTheDocument();

    fireEvent.click(screen.getByText("trk-a"));
    expect(onSelect).toHaveBeenCalledWith(sampleAlert.alert_id);
  });

  it("shows an empty state without data", () => {
    render(<AlertList alerts={[]} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText(/No review candidates/i)).toBeInTheDocument();
  });
});

describe("AlertDetail", () => {
  it("shows the review priority and neutral explanation", () => {
    render(<AlertDetail alert={sampleDetail} />);
    expect(screen.getByText("Review Priority")).toBeInTheDocument();
    // The priority banner shows the score as a percentage. Query the specific
    // element to avoid colliding with other coincidental "99%" values.
    const priority = document.querySelector(".priority-value");
    expect(priority?.textContent).toBe("99%");
    expect(
      screen.getByText(/Low-speed duration above background range/i),
    ).toBeInTheDocument();

    // Terminology guard: prohibited vocabulary must not appear.
    const text = document.body.textContent?.toLowerCase() ?? "";
    expect(text).not.toContain("threat");
    expect(text).not.toContain("hostile");
    expect(text).not.toContain("illegal");
  });

  it("prompts to select when no alert is chosen", () => {
    render(<AlertDetail alert={null} />);
    expect(screen.getByText(/Select a review candidate/i)).toBeInTheDocument();
  });
});
