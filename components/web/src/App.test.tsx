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
});
