export interface SegOption<T> {
  value: T;
  label: string;
  disabled?: boolean;
}

interface Props<T> {
  options: SegOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  /** Disables every option (e.g. mode switch locked while an answer runs, F9). */
  disabled?: boolean;
}

/** A group of mutually exclusive buttons. The selected one stays visibly highlighted. */
export function Segmented<T extends string | number>({ options, value, onChange, label, disabled }: Props<T>) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => {
        const off = disabled || o.disabled;
        return (
          <button
            key={String(o.value)}
            type="button"
            className={`seg-btn${o.value === value ? " on" : ""}${off ? " dis" : ""}`}
            aria-pressed={o.value === value}
            disabled={off}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
