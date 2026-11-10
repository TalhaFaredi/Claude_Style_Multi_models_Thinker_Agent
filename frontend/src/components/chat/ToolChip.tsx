import { Icon } from "../ui/Icon";

/** "Web search: running" then "3 sources used". */
export function ToolChip({ label }: { label: string }) {
  return (
    <span className="status">
      <Icon name="search" size={14} />
      {label}
    </span>
  );
}
