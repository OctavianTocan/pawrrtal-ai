import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PromptInputProps } from './prompt-input';
import { PromptInput, PromptInputAttachment, PromptInputAttachments, PromptInputTextarea } from './prompt-input';

type PromptInputOnError = NonNullable<PromptInputProps['onError']>;
type PromptInputOnSubmit = PromptInputProps['onSubmit'];

const renderPromptInput = ({
  accept,
  maxFiles,
  maxFileSize,
  onError = vi.fn<PromptInputOnError>(),
  onSubmit = vi.fn<PromptInputOnSubmit>(),
}: {
  accept?: string;
  maxFiles?: number;
  maxFileSize?: number;
  onError?: PromptInputOnError;
  onSubmit?: PromptInputOnSubmit;
} = {}) => {
  render(
    <PromptInput accept={accept} maxFileSize={maxFileSize} maxFiles={maxFiles} onError={onError} onSubmit={onSubmit}>
      <PromptInputTextarea aria-label="Message" />
      <PromptInputAttachments>{(attachment) => <PromptInputAttachment data={attachment} />}</PromptInputAttachments>
      <button type="submit">Send</button>
    </PromptInput>
  );

  return {
    fileInput: screen.getByLabelText('Upload files') as HTMLInputElement,
    messageInput: screen.getByLabelText('Message'),
    onError,
    onSubmit,
  };
};

describe('PromptInput', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('blob urls unavailable in jsdom')));
    // Only override the two URL.* helpers we exercise. Replacing `URL`
    // wholesale with a plain object breaks `new URL(...)` constructor
    // calls inside next/image's getImgProps (used by the attachment
    // preview component this test renders).
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:prompt-input-test');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  });

  it('submits accepted uploaded files with the message text', async () => {
    const onSubmit = vi.fn();
    const { fileInput, messageInput } = renderPromptInput({
      accept: 'image/*',
      onSubmit,
    });

    fireEvent.change(fileInput, {
      target: {
        files: [new File(['avatar'], 'avatar.png', { type: 'image/png' })],
      },
    });
    fireEvent.change(messageInput, { target: { value: 'Describe this image' } });

    expect(await screen.findByText('avatar.png')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          content: 'Describe this image',
          files: [
            expect.objectContaining({
              filename: 'avatar.png',
              mediaType: 'image/png',
              type: 'file',
              url: 'blob:prompt-input-test',
            }),
          ],
        }),
        expect.anything()
      );
    });
  });

  it('reports an accept error without attaching rejected files', () => {
    const onError = vi.fn();
    const onSubmit = vi.fn();
    const { fileInput } = renderPromptInput({
      accept: 'image/*',
      onError,
      onSubmit,
    });

    fireEvent.change(fileInput, {
      target: {
        files: [new File(['notes'], 'notes.txt', { type: 'text/plain' })],
      },
    });

    expect(onError).toHaveBeenCalledWith({
      code: 'accept',
      message: 'No files match the accepted types.',
    });
    expect(screen.queryByText('notes.txt')).not.toBeInTheDocument();
  });
});
