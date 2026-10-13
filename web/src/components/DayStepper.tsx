import { Minus, Plus } from "lucide-react";
import { plural } from "../format.ts";
import { nextStep } from "../retention.ts";

/** A number of days, changed by − and + through usual values (a week, a month…): no field
 *  to type into. */
export function DayStepper({
  label,
  description,
  value,
  steps,
  min = 1,
  max = Number.POSITIVE_INFINITY,
  isDisabled = false,
  onChange,
}: {
  label: string;
  description?: string;
  value: number;
  steps: readonly number[];
  min?: number;
  max?: number;
  /** Not read yet: shown, not changed. */
  isDisabled?: boolean;
  onChange: (value: number) => void;
}) {
  const down = nextStep(steps, value, false, min, max);
  const up = nextStep(steps, value, true, min, max);
  return (
    <div className="cl-stepper">
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
          disabled={isDisabled || down >= value}
          onClick={() => onChange(down)}
        >
          <Minus size={14} strokeWidth={1.75} aria-hidden />
        </button>
        <output aria-live="polite">{plural(value, "jour", "jours")}</output>
        <button
          type="button"
          aria-label={`${label} : plus`}
          disabled={isDisabled || up <= value}
          onClick={() => onChange(up)}
        >
          <Plus size={14} strokeWidth={1.75} aria-hidden />
        </button>
      </div>
    </div>
  );
}
