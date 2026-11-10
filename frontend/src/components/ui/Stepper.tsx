interface Props {
  value: number;
  onDown: () => void;
  onUp: () => void;
  downLabel: string;
  upLabel: string;
}

/** Limits (F3) live in the store action, not here: the buttons just call it. */
export function Stepper({ value, onDown, onUp, downLabel, upLabel }: Props) {
  return (
    <div className="stepper">
      <button type="button" aria-label={downLabel} onClick={onDown}>-</button>
      <span className="stepper-val" aria-live="polite">{value}</span>
      <button type="button" aria-label={upLabel} onClick={onUp}>+</button>
    </div>
  );
}
