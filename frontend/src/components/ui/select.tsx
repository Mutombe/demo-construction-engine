/** Custom listbox Select (no native <select> chrome).
 *
 * Drop-in compatible with the previous styled-native component: call sites
 * keep passing `value`, `onChange` (receives `{target: {value}}`), `className`,
 * `disabled` and plain `<option>` children — this component parses the options
 * out of the children and renders its own trigger + portal-positioned panel,
 * so it is never clipped by dialog/table overflow.
 *
 * Keyboard: Enter/Space/ArrowDown opens; arrows move; Enter selects;
 * Escape/Tab closes; typing jumps to the first matching option.
 */

import { CaretDown, Check } from "@phosphor-icons/react";
import {
  Children,
  isValidElement,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

interface OptionSpec {
  value: string;
  label: string;
  disabled?: boolean;
}

function collectOptions(children: ReactNode): OptionSpec[] {
  const out: OptionSpec[] = [];
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return;
    if (child.type === "option") {
      const props = child.props as {
        value?: string | number;
        children?: ReactNode;
        disabled?: boolean;
      };
      const label = flattenText(props.children);
      out.push({
        value: props.value !== undefined ? String(props.value) : label,
        label,
        disabled: props.disabled,
      });
    } else {
      // fragments / arrays of options
      const inner = (child.props as { children?: ReactNode })?.children;
      if (inner) out.push(...collectOptions(inner));
    }
  });
  return out;
}

function flattenText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(flattenText).join("");
  if (isValidElement(node)) {
    return flattenText((node.props as { children?: ReactNode }).children);
  }
  return "";
}

type Props = Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange" | "value"> & {
  value?: string;
  onChange?: (event: { target: { value: string } }) => void;
};

export function Select({ className, children, value, onChange, disabled, ...rest }: Props) {
  const options = useMemo(() => collectOptions(children), [children]);
  const current = options.find((o) => o.value === String(value ?? ""));
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const typeahead = useRef({ text: "", at: 0 });

  const openPanel = () => {
    if (disabled) return;
    const index = options.findIndex((o) => o.value === String(value ?? ""));
    setActive(index >= 0 ? index : 0);
    setRect(triggerRef.current?.getBoundingClientRect() ?? null);
    setOpen(true);
  };

  const select = (option: OptionSpec) => {
    if (option.disabled) return;
    onChange?.({ target: { value: option.value } });
    setOpen(false);
    triggerRef.current?.focus();
  };

  // Close on outside interaction / viewport changes (position is fixed).
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (
        !panelRef.current?.contains(e.target as Node) &&
        !triggerRef.current?.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    const onScroll = (e: Event) => {
      if (panelRef.current?.contains(e.target as Node)) return; // panel's own scroll
      setOpen(false);
    };
    const onResize = () => setOpen(false);
    document.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
  }, [open]);

  // Keep the active option in view while navigating.
  useLayoutEffect(() => {
    if (!open) return;
    panelRef.current
      ?.querySelector(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const move = (delta: number) => {
    if (options.length === 0) return;
    let next = active;
    for (let i = 0; i < options.length; i++) {
      next = (next + delta + options.length) % options.length;
      if (!options[next]?.disabled) break;
    }
    setActive(next);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (!open) {
      if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(e.key)) {
        e.preventDefault();
        openPanel();
      }
      return;
    }
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        move(1);
        break;
      case "ArrowUp":
        e.preventDefault();
        move(-1);
        break;
      case "Home":
        e.preventDefault();
        setActive(0);
        break;
      case "End":
        e.preventDefault();
        setActive(options.length - 1);
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (options[active]) select(options[active]);
        break;
      case "Escape":
      case "Tab":
        setOpen(false);
        break;
      default: {
        if (e.key.length === 1) {
          const now = Date.now();
          const state = typeahead.current;
          state.text = now - state.at < 600 ? state.text + e.key : e.key;
          state.at = now;
          const idx = options.findIndex((o) =>
            o.label.toLowerCase().startsWith(state.text.toLowerCase()),
          );
          if (idx >= 0) setActive(idx);
        }
      }
    }
  };

  // Panel geometry: below the trigger, flipping up when short on space.
  const panelStyle: React.CSSProperties | undefined = rect
    ? (() => {
        const maxHeight = 280;
        const below = window.innerHeight - rect.bottom;
        const flip = below < Math.min(maxHeight, 200) && rect.top > below;
        return {
          position: "fixed",
          left: rect.left,
          width: rect.width,
          maxHeight,
          ...(flip
            ? { bottom: window.innerHeight - rect.top + 4 }
            : { top: rect.bottom + 4 }),
        };
      })()
    : undefined;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openPanel())}
        onKeyDown={onKeyDown}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-card px-3 py-1 text-left text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...(rest as object)}
      >
        <span className={cn("truncate", !current?.label && "text-muted-foreground")}>
          {current?.label || options[0]?.label || ""}
        </span>
        <CaretDown
          size={13}
          className={cn(
            "shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open &&
        createPortal(
          <div
            ref={panelRef}
            role="listbox"
            style={panelStyle}
            className="dropdown-in z-[2100] overflow-y-auto rounded-md border bg-card py-1 shadow-lg"
          >
            {options.map((option, index) => {
              const selected = option.value === String(value ?? "");
              return (
                <div
                  key={`${option.value}-${index}`}
                  role="option"
                  aria-selected={selected}
                  data-index={index}
                  className={cn(
                    "flex cursor-pointer items-center justify-between gap-2 px-3 py-1.5 text-sm transition-colors",
                    index === active && "bg-muted",
                    option.disabled && "cursor-not-allowed opacity-50",
                    selected && "font-medium",
                  )}
                  onMouseEnter={() => setActive(index)}
                  onMouseDown={(e) => {
                    e.preventDefault(); // keep trigger focus
                    select(option);
                  }}
                >
                  <span className="truncate">{option.label}</span>
                  {selected && <Check size={13} className="shrink-0 text-primary" />}
                </div>
              );
            })}
          </div>,
          document.body,
        )}
    </>
  );
}
