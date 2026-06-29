'use client';

/**
 * @fileoverview Host-row submenu components and grouping logic for
 * `ModelSelectorPopover`. Extracted to keep the popover file under the
 * 500-line budget while preserving the three-level walk:
 * host → (optional vendor) → model.
 */

import { DropdownSubmenu, DropdownSubmenuContent, DropdownSubmenuTrigger } from '@octavian-tocan/react-dropdown';
import type * as React from 'react';
import { cn } from '@/lib/utils';
import { hostLabel, vendorLabel } from './model-picker-labels';
import type { HostMenuRowRenderProps, MultiVendorHostMenuRowRenderProps } from './model-selector-types';
import { vendorLogo } from './vendor-logos';

// ---------------------------------------------------------------------------
// Internal sub-components
// ---------------------------------------------------------------------------

/** Render-only wrapper that resolves the vendor logo from the canonical map. */
function VendorLogo({ vendor, className }: { vendor: string; className?: string }): React.JSX.Element {
  const Logo = vendorLogo(vendor);
  return <Logo className={cn('size-3', className)} />;
}

// ---------------------------------------------------------------------------
// Host-row components
// ---------------------------------------------------------------------------

/**
 * Flyout submenu for a single host that has only one vendor.
 *
 * The intermediate vendor screen is skipped — models render directly inside
 * the host's submenu panel, with the single vendor's logo shown in the trigger.
 */
export function SingleVendorHostMenuRow({
  group,
  isActiveHost,
  selectedModelId,
  onSelectModel,
  renderModelRow,
}: HostMenuRowRenderProps): React.JSX.Element | null {
  const onlyVendor = group.vendors[0];
  if (!onlyVendor) return null;

  return (
    <DropdownSubmenu>
      {/* `DropdownSubmenuTrigger` bakes in its own flyout chevron — rendering an
			    explicit ChevronRightIcon here used to produce two arrows side-by-side. We
			    only emit the "active host" check now; the library's chevron handles the
			    "expand" affordance for every row. */}
      <DropdownSubmenuTrigger
        className={cn(
          'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
          isActiveHost && 'bg-foreground/[0.07]'
        )}
      >
        <VendorLogo vendor={onlyVendor.vendor} />
        <span className="min-w-0 flex-1 truncate text-left">{hostLabel(group.host)}</span>
      </DropdownSubmenuTrigger>
      <DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled min-w-64 p-1">
        {onlyVendor.entries.map((model) =>
          renderModelRow({
            model,
            isSelected: selectedModelId === model.id,
            onSelect: onSelectModel,
          })
        )}
      </DropdownSubmenuContent>
    </DropdownSubmenu>
  );
}

/**
 * Flyout submenu for a host that carries multiple vendors.
 *
 * Root trigger opens the vendor list; each vendor entry opens its own model list.
 */
export function MultiVendorHostMenuRow({
  group,
  isActiveHost,
  selectedModel,
  selectedModelId,
  onSelectModel,
  renderModelRow,
}: MultiVendorHostMenuRowRenderProps): React.JSX.Element {
  return (
    <DropdownSubmenu>
      <DropdownSubmenuTrigger
        className={cn(
          'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
          isActiveHost && 'bg-foreground/[0.07]'
        )}
      >
        <span className="min-w-0 flex-1 truncate text-left">{hostLabel(group.host)}</span>
      </DropdownSubmenuTrigger>
      <DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled min-w-56 p-1">
        {group.vendors.map((vendorGroup) => {
          const isActiveVendor = selectedModel?.host === group.host && selectedModel?.vendor === vendorGroup.vendor;
          return (
            <DropdownSubmenu key={vendorGroup.vendor}>
              <DropdownSubmenuTrigger
                className={cn(
                  'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
                  isActiveVendor && 'bg-foreground/[0.07]'
                )}
              >
                <VendorLogo vendor={vendorGroup.vendor} />
                <span className="min-w-0 flex-1 truncate text-left">{vendorLabel(vendorGroup.vendor)}</span>
              </DropdownSubmenuTrigger>
              <DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled min-w-64 p-1">
                {vendorGroup.entries.map((model) =>
                  renderModelRow({
                    model,
                    isSelected: selectedModelId === model.id,
                    onSelect: onSelectModel,
                  })
                )}
              </DropdownSubmenuContent>
            </DropdownSubmenu>
          );
        })}
      </DropdownSubmenuContent>
    </DropdownSubmenu>
  );
}
