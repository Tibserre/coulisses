import type { ReactNode } from "react";
import { Minus, Plus } from "lucide-react";
import { plural } from "../format.ts";
import { nextStep } from "../retention.ts";

/** A number of days (or minutes, `say`), changed by − and + through usual values (a week,
 *  a month…): no field to type into. */
export function DayStepper({
  label,
  description,
  value,
  steps,
  say = (n: number) => plural(n, "jour", "jours"),
  title,
  icon,
  onChange,
}: {
  label: string;
  description?: string;
  value: number;
  steps: readonly number[];
  /** The value as said: days unless told otherwise. */
  say?: (value: number) => string;
  /** Shown as a card: its name and icon on top, the label then the control under. */
  title?: string;
  icon?: ReactNode;
  onChange: (value: number) => void;
}) {
  const down = nextStep(steps, value, false);
  const up = nextStep(steps, value, true);
  return (
    <div className={title ? "cl-stepper cl-stepper--card" : "cl-stepper"}>
      {title && (
        <div className="cl-stepper__title">
          {icon && <span className="cl-icon-disc">{icon}</span>}
          <span>{title}</span>
        </div>
      )}
      <div className="cl-stepper__what">
        <span className="cl-stepper__label">{label}</span>
        {description && (
          <span className="cl-stepper__description">{description}</span>
        )}
      </div>
      <div className="cl-stepper__control" role="group" aria-label={label}>
        <button
          type="button"
          aria-label={`${label} : moins`}
          disabled={down >= value}
          onClick={() => onChange(down)}
        >
          <Minus size={14} strokeWidth={1.75} aria-hidden />
        </button>
        <output aria-live="polite">{say(value)}</output>
        <button
          type="button"
          aria-label={`${label} : plus`}
          disabled={up <= value}
          onClick={() => onChange(up)}
        >
          <Plus size={14} strokeWidth={1.75} aria-hidden />
        </button>
      </div>
    </div>
  );
}
