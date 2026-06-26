import * as React from 'react';

import { cn } from '@/lib/utils';

type TopBarButtonProps = React.ComponentProps<'button'> & {
  isActive?: boolean;
};

export function TopBarButton({
  children,
  className,
  disabled,
  isActive,
  ref,
  ...props
}: TopBarButtonProps): React.JSX.Element {
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled}
      className={cn(
        'flex size-8 items-center justify-center rounded-[6px] transition duration-150',
        'cursor-pointer hover:bg-foreground/5 active:scale-[0.97] focus:outline-none focus-visible:ring-0',
        'disabled:pointer-events-none disabled:opacity-30',
        isActive && 'bg-foreground/5',
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
