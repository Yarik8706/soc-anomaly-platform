import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("calls the handler and exposes loading state", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Запустить</Button>);
    await user.click(screen.getByRole("button", { name: "Запустить" }));
    expect(onClick).toHaveBeenCalledOnce();

    rerender(<Button loading>Запустить</Button>);
    expect(screen.getByRole("button", { name: "Запустить" })).toBeDisabled();
    expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true");
  });
});
