import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App.js";

function renderAt(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App", () => {
  it("renders the landing page on / with the product name and a tagline", () => {
    renderAt("/");
    expect(screen.getByRole("heading", { name: "Shrink" })).toBeInTheDocument();
    expect(screen.getByText(/short links, clear analytics/i)).toBeInTheDocument();
  });

  it("renders the /login placeholder page", () => {
    renderAt("/login");
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByText(/auth ui lands in t10/i)).toBeInTheDocument();
  });

  it("landing exposes a router link to /login (SPA navigation, no full reload)", () => {
    renderAt("/");
    const signIn = screen.getByRole("link", { name: /sign in/i });
    expect(signIn).toBeInTheDocument();
    expect(signIn.getAttribute("href")).toBe("/login");
  });

  it("login placeholder exposes a router link back to /", () => {
    renderAt("/login");
    const back = screen.getByRole("link", { name: /back to home/i });
    expect(back).toBeInTheDocument();
    expect(back.getAttribute("href")).toBe("/");
  });
});
