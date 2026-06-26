interface SectionHeaderProps {
  /** The section label text (e.g. "Today", "Yesterday"). */
  label: string;
}

/**
 * A non-interactive section label used when a conversation date group
 * is the only group visible (i.e. collapsing is disabled).
 */
export function SectionHeader({ label }: SectionHeaderProps): React.JSX.Element {
  return (
    <li className="flex items-center gap-1.5 px-4 py-2">
      <span aria-hidden="true" className="flex size-3.5 shrink-0 items-center justify-center">
        <span className="size-[6px] rounded-full bg-muted-foreground/25" />
      </span>
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
    </li>
  );
}
