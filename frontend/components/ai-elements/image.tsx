/**
 * Renders generated image parts from the AI SDK.
 *
 * @fileoverview AI Elements — `image`.
 */

import type { Experimental_GeneratedImage } from 'ai';
import NextImage from 'next/image';
import { cn } from '@/lib/utils';

export type ImageProps = Experimental_GeneratedImage & {
  className?: string;
  alt?: string;
};

export const Image = ({ base64, uint8Array, mediaType, alt = '', ...props }: ImageProps) => (
  <NextImage
    {...props}
    alt={alt}
    className={cn('h-auto max-w-full overflow-hidden rounded-md', props.className)}
    height={1024}
    src={`data:${mediaType};base64,${base64}`}
    unoptimized
    width={1024}
  />
);
