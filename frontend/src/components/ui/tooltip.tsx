/** Hover/focus tooltip.
 *
 * Replaces the native `title` attribute, which waits about a second before
 * appearing, cannot be styled, and never shows on touch. This appears quickly,
 * follows the app's tokens, and — because it also triggers on keyboard focus —
 * reaches people tabbing through icon-only buttons, who get nothing from a
 * mouse-only affordance.
 *
 * Portal-positioned like the Select, so a table's `overflow` cannot clip it.
 */

import {
  cloneElement,
  isValidElement,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

const SHOW_DELAY = 250;
const GAP = 8;

type Side = "top" | "bottom" | "left" | "right";

export function Tooltip({
  content,
  side = "top",
  children,
  className,
}: {
  /** Omit to render the child untouched — lets callers pass a maybe-empty hint. */
  content?: ReactNode;
  side?: Side;
  children: ReactElement;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const id = useId();

  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const show = () => {
    clear();
    timer.current = setTimeout(() => {
      setRect(triggerRef.current?.getBoundingClientRect() ?? null);
      setOpen(true);
    }, SHOW_DELAY);
  };

  const hide = () => {
    clear();
    setOpen(false);
  };

  // Escape closes, matching every other transient surface in the app.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") hide();
    };
    window.addEventListener("keydown", onKey);
    // Any scroll invalidates the measured position; simplest correct answer
    // is to dismiss rather than track.
    window.addEventListener("scroll", hide, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hide, true);
    };
  }, [open]);

  useEffect(() => clear, []);

  if (!content || !isValidElement(children)) return children;

  const child = children as ReactElement<Record<string, unknown>>;
  const trigger = cloneElement(child, {
    ref: (node: HTMLElement | null) => {
      triggerRef.current = node;
      const ref = (child as unknown as { ref?: unknown }).ref;
      if (typeof ref === "function") (ref as (n: HTMLElement | null) => void)(node);
      else if (ref && typeof ref === "object")
        (ref as { current: HTMLElement | null }).current = node;
    },
    "aria-describedby": open ? id : undefined,
    onMouseEnter: (e: React.MouseEvent) => {
      (child.props.onMouseEnter as ((e: React.MouseEvent) => void) | undefined)?.(e);
      show();
    },
    onMouseLeave: (e: React.MouseEvent) => {
      (child.props.onMouseLeave as ((e: React.MouseEvent) => void) | undefined)?.(e);
      hide();
    },
    onFocus: (e: React.FocusEvent) => {
      (child.props.onFocus as ((e: React.FocusEvent) => void) | undefined)?.(e);
      show();
    },
    onBlur: (e: React.FocusEvent) => {
      (child.props.onBlur as ((e: React.FocusEvent) => void) | undefined)?.(e);
      hide();
    },
    // A tooltip must never survive the click that navigates away.
    onClick: (e: React.MouseEvent) => {
      (child.props.onClick as ((e: React.MouseEvent) => void) | undefined)?.(e);
      hide();
    },
  } as Record<string, unknown>);

  // Above dialogs (50), toasts (2000) and select panels (2100): a hint that
  // renders behind the thing it describes is worse than no hint.
  const style: React.CSSProperties = { position: "fixed", zIndex: 2200 };
  if (rect) {
    if (side === "top") {
      style.left = rect.left + rect.width / 2;
      style.top = rect.top - GAP;
      style.transform = "translate(-50%, -100%)";
    } else if (side === "bottom") {
      style.left = rect.left + rect.width / 2;
      style.top = rect.bottom + GAP;
      style.transform = "translate(-50%, 0)";
    } else if (side === "left") {
      style.left = rect.left - GAP;
      style.top = rect.top + rect.height / 2;
      style.transform = "translate(-100%, -50%)";
    } else {
      style.left = rect.right + GAP;
      style.top = rect.top + rect.height / 2;
      style.transform = "translate(0, -50%)";
    }
  }

  return (
    <>
      {trigger}
      {open &&
        rect &&
        createPortal(
          <div
            id={id}
            role="tooltip"
            style={style}
            className={cn(
              "pointer-events-none max-w-64 rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background shadow-md",
              className,
            )}
          >
            {content}
          </div>,
          document.body,
        )}
    </>
  );
}
