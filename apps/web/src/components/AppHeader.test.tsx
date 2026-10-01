import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "../i18n/I18nContext";
import { AppHeader } from "./AppHeader";

function wrap(ui: React.ReactElement) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

describe("AppHeader status pill", () => {
  it("renders LIVE (即時 AIS) when live", () => {
    const { container } = wrap(<AppHeader status="live" />);
    expect(screen.getByText("即時 AIS")).toBeInTheDocument();
    expect(container.querySelector(".live-pill.live-live")).toBeTruthy();
  });

  it("renders Reconnecting (重新連線中)", () => {
    wrap(<AppHeader status="reconnecting" />);
    expect(screen.getByText("重新連線中")).toBeInTheDocument();
  });

  it("renders Stale (資料較舊)", () => {
    wrap(<AppHeader status="stale" />);
    expect(screen.getByText("資料較舊")).toBeInTheDocument();
  });

  it("renders Offline Demo only for offline_demo status", () => {
    wrap(<AppHeader status="offline_demo" />);
    expect(screen.getByText("離線展示資料")).toBeInTheDocument();
  });
});
