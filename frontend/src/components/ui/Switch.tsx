interface Props {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export function Switch({ label, checked, onChange }: Props) {
  return (
    <button type="button" role="switch" aria-checked={checked} className="switch" onClick={() => onChange(!checked)}>
      <span>{label}</span>
      <span className={`knob${checked ? " on" : ""}`} />
    </button>
  );
}
