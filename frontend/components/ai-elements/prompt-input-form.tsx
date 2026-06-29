/**
 * Prompt input form shell and local attachment state.
 *
 * @fileoverview Keeps submit/drop/file-input behavior separate from presentational prompt input components.
 */

'use client';

import type { FileUIPart } from 'ai';
import { nanoid } from 'nanoid';
import type {
  ChangeEventHandler,
  DragEventHandler,
  FormEvent,
  FormEventHandler,
  HTMLAttributes,
  RefObject,
} from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { InputGroup } from '@/components/ui/input-group';
import { cn } from '@/lib/utils';
import type { AttachmentsContext, PromptInputControllerProps } from './prompt-input-context';
import { LocalAttachmentsContext, useOptionalPromptInputController } from './prompt-input-context';

/** Message payload emitted when the prompt input form submits. */
export type PromptInputMessage = {
  content: string;
  files: FileUIPart[];
};

/** Props for the root prompt input form. */
export type PromptInputProps = Omit<HTMLAttributes<HTMLFormElement>, 'onSubmit' | 'onError'> & {
  accept?: string;
  multiple?: boolean;
  /** Additional classes for the internal InputGroup surface. */
  inputGroupClassName?: string;
  /** When true, accepts drops anywhere on document. */
  globalDrop?: boolean;
  /** Reset the hidden file input when the attachment list becomes empty. */
  syncHiddenInput?: boolean;
  maxFiles?: number;
  maxFileSize?: number;
  onError?: (err: { code: 'max_files' | 'max_file_size' | 'accept'; message: string }) => void;
  onSubmit: (message: PromptInputMessage, event: FormEvent<HTMLFormElement>) => void | Promise<void>;
};

type LocalFilePart = FileUIPart & { id: string };

type PromptInputAttachmentOptions = {
  accept?: string;
  globalDrop?: boolean;
  syncHiddenInput?: boolean;
  maxFiles?: number;
  maxFileSize?: number;
  onError?: PromptInputProps['onError'];
  inputRef: RefObject<HTMLInputElement | null>;
};

type PromptInputAttachmentState = {
  controller: PromptInputControllerProps | null;
  usingProvider: boolean;
  files: LocalFilePart[];
  contextValue: AttachmentsContext;
  ingestSelectedFiles: ChangeEventHandler<HTMLInputElement>;
  handleFormDragOver: DragEventHandler<HTMLFormElement>;
  handleFormDrop: DragEventHandler<HTMLFormElement>;
  clear: () => void;
};

const fileMatchesAccept = (file: File, accept?: string): boolean => {
  if (!accept?.trim()) {
    return true;
  }

  return accept
    .split(',')
    .flatMap((pattern) => {
      const trimmed = pattern.trim();
      return trimmed ? [trimmed] : [];
    })
    .some((pattern) => {
      if (pattern.endsWith('/*')) {
        const prefix = pattern.slice(0, -1);
        return file.type.startsWith(prefix);
      }
      return file.type === pattern;
    });
};

const createFilePart = (file: File): LocalFilePart => ({
  id: nanoid(),
  type: 'file',
  url: URL.createObjectURL(file),
  mediaType: file.type,
  filename: file.name,
});

const revokeFileUrl = (file: { url?: string }) => {
  if (file.url) {
    URL.revokeObjectURL(file.url);
  }
};

const convertBlobUrlToDataUrl = async (url: string): Promise<string | null> => {
  try {
    const response = await fetch(url);
    const blob = await response.blob();
    return await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result as string);
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
};

const normalizeSubmittedFiles = async (files: LocalFilePart[]): Promise<FileUIPart[]> =>
  Promise.all(
    files.map(async ({ id: _id, ...item }) => {
      if (item.url?.startsWith('blob:')) {
        const dataUrl = await convertBlobUrlToDataUrl(item.url);
        return { ...item, url: dataUrl ?? item.url };
      }
      return item;
    })
  );

const useLocalAttachmentActions = ({
  accept,
  maxFiles,
  maxFileSize,
  onError,
}: Pick<PromptInputAttachmentOptions, 'accept' | 'maxFiles' | 'maxFileSize' | 'onError'>) => {
  const [items, setItems] = useState<LocalFilePart[]>([]);

  const removeLocal = useCallback(
    (id: string) =>
      setItems((prev) => {
        const found = prev.find((file) => file.id === id);
        if (found) revokeFileUrl(found);
        return prev.filter((file) => file.id !== id);
      }),
    []
  );

  const clearLocal = useCallback(
    () =>
      setItems((prev) => {
        for (const file of prev) revokeFileUrl(file);
        return [];
      }),
    []
  );

  const addLocal = useCallback(
    (fileList: File[] | FileList) => {
      const incoming = Array.from(fileList);
      const accepted = incoming.filter((file) => fileMatchesAccept(file, accept));
      if (incoming.length && accepted.length === 0) {
        onError?.({ code: 'accept', message: 'No files match the accepted types.' });
        return;
      }

      const sized = accepted.filter((file) => (maxFileSize ? file.size <= maxFileSize : true));
      if (accepted.length > 0 && sized.length === 0) {
        onError?.({ code: 'max_file_size', message: 'All files exceed the maximum size.' });
        return;
      }

      setItems((prev) => {
        const capacity = typeof maxFiles === 'number' ? Math.max(0, maxFiles - prev.length) : undefined;
        const capped = typeof capacity === 'number' ? sized.slice(0, capacity) : sized;
        if (typeof capacity === 'number' && sized.length > capacity) {
          onError?.({
            code: 'max_files',
            message: 'Too many files. Some were not added.',
          });
        }
        return prev.concat(capped.map(createFilePart));
      });
    },
    [accept, maxFiles, maxFileSize, onError]
  );

  return { addLocal, clearLocal, items, removeLocal };
};

const hasDraggedFiles = (dataTransfer: DataTransfer): boolean => dataTransfer.types.includes('Files');

const useDocumentDropTarget = ({ add, globalDrop }: { add: AttachmentsContext['add']; globalDrop?: boolean }) => {
  useEffect(() => {
    if (!globalDrop) return;

    const onDragOver = (e: DragEvent) => {
      if (e.dataTransfer && hasDraggedFiles(e.dataTransfer)) {
        e.preventDefault();
      }
    };
    const onDrop = (e: DragEvent) => {
      if (e.dataTransfer && hasDraggedFiles(e.dataTransfer)) {
        e.preventDefault();
      }
      if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
        add(e.dataTransfer.files);
      }
    };
    document.addEventListener('dragover', onDragOver);
    document.addEventListener('drop', onDrop);
    return () => {
      document.removeEventListener('dragover', onDragOver);
      document.removeEventListener('drop', onDrop);
    };
  }, [add, globalDrop]);
};

const usePromptInputAttachmentState = ({
  accept,
  globalDrop,
  syncHiddenInput,
  maxFiles,
  maxFileSize,
  onError,
  inputRef,
}: PromptInputAttachmentOptions): PromptInputAttachmentState => {
  const controller = useOptionalPromptInputController();
  const usingProvider = !!controller;
  const { addLocal, clearLocal, items, removeLocal } = useLocalAttachmentActions({
    accept,
    maxFiles,
    maxFileSize,
    onError,
  });

  const files = usingProvider ? controller.attachments.files : items;
  const filesRef = useRef(files);
  filesRef.current = files;
  const add = usingProvider ? controller.attachments.add : addLocal;
  const remove = usingProvider ? controller.attachments.remove : removeLocal;
  const clear = usingProvider ? controller.attachments.clear : clearLocal;
  const openFileDialog = usingProvider ? controller.attachments.openFileDialog : () => inputRef.current?.click();
  const clearHiddenInput = useCallback((): void => {
    if (syncHiddenInput && inputRef.current) {
      inputRef.current.value = '';
    }
  }, [inputRef, syncHiddenInput]);
  const removeAndSyncInput = useCallback(
    (id: string): void => {
      const removesLastFile = filesRef.current.length === 1 && filesRef.current[0]?.id === id;
      remove(id);
      if (removesLastFile) {
        clearHiddenInput();
      }
    },
    [clearHiddenInput, remove]
  );
  const clearAndSyncInput = useCallback((): void => {
    clear();
    clearHiddenInput();
  }, [clear, clearHiddenInput]);

  useDocumentDropTarget({ add, globalDrop });
  useEffect(() => {
    const ref = filesRef;
    return () => {
      if (!usingProvider) {
        for (const file of ref.current) revokeFileUrl(file);
      }
    };
  }, [usingProvider]);

  const contextValue = useMemo<AttachmentsContext>(
    () => ({
      files: files.map((item) => ({ ...item, id: item.id })),
      add,
      remove: removeAndSyncInput,
      clear: clearAndSyncInput,
      openFileDialog,
      fileInputRef: inputRef,
    }),
    [files, add, removeAndSyncInput, clearAndSyncInput, openFileDialog, inputRef]
  );

  const ingestSelectedFiles: ChangeEventHandler<HTMLInputElement> = (event) => {
    if (event.currentTarget.files) {
      add(event.currentTarget.files);
    }
    event.currentTarget.value = '';
  };

  const handleFormDragOver: DragEventHandler<HTMLFormElement> = (event) => {
    if (!globalDrop && hasDraggedFiles(event.dataTransfer)) {
      event.preventDefault();
    }
  };

  const handleFormDrop: DragEventHandler<HTMLFormElement> = (event) => {
    if (globalDrop) return;
    if (hasDraggedFiles(event.dataTransfer)) {
      event.preventDefault();
    }
    if (event.dataTransfer.files.length > 0) {
      add(event.dataTransfer.files);
    }
  };

  return {
    controller,
    usingProvider,
    files,
    contextValue,
    ingestSelectedFiles,
    handleFormDragOver,
    handleFormDrop,
    clear: clearAndSyncInput,
  };
};

const usePromptInputSubmitHandler = ({
  clear,
  controller,
  files,
  onSubmit,
  usingProvider,
}: {
  clear: () => void;
  controller: PromptInputControllerProps | null;
  files: LocalFilePart[];
  onSubmit: PromptInputProps['onSubmit'];
  usingProvider: boolean;
}): FormEventHandler<HTMLFormElement> =>
  useCallback(
    (event) => {
      event.preventDefault();

      const form = event.currentTarget;
      const text = usingProvider
        ? (controller?.textInput.value ?? '')
        : ((new FormData(form).get('message') as string) ?? '');

      if (!usingProvider) {
        form.reset();
      }

      normalizeSubmittedFiles(files)
        .then((convertedFiles) => onSubmit({ content: text, files: convertedFiles }, event))
        .then(() => {
          clear();
          if (usingProvider) {
            controller?.textInput.clear();
          }
        })
        .catch(() => {
          // Keep input and attachments so users can retry after submit/conversion errors.
        });
    },
    [clear, controller, files, onSubmit, usingProvider]
  );

/** Root prompt input form with attachment and submit orchestration. */
export const PromptInput = ({
  className,
  accept,
  multiple,
  inputGroupClassName,
  globalDrop,
  syncHiddenInput,
  maxFiles,
  maxFileSize,
  onError,
  onSubmit,
  children,
  onDragOver,
  onDrop,
  ...props
}: PromptInputProps) => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const {
    clear,
    contextValue,
    controller,
    files,
    ingestSelectedFiles,
    handleFormDragOver,
    handleFormDrop,
    usingProvider,
  } = usePromptInputAttachmentState({
    accept,
    globalDrop,
    syncHiddenInput,
    maxFiles,
    maxFileSize,
    onError,
    inputRef,
  });
  const handleSubmit = usePromptInputSubmitHandler({
    clear,
    controller,
    files,
    onSubmit,
    usingProvider,
  });
  const setInputNode = useCallback(
    (node: HTMLInputElement | null): void => {
      inputRef.current = node;
      if (usingProvider) {
        controller?.__registerFileInput(inputRef, () => inputRef.current?.click());
      }
    },
    [controller, usingProvider]
  );

  const inner = (
    <>
      <input
        accept={accept}
        aria-label="Upload files"
        className="hidden"
        multiple={multiple}
        onChange={ingestSelectedFiles}
        ref={setInputNode}
        title="Upload files"
        type="file"
      />
      <form
        className={cn('w-full', className)}
        onDragOver={(event) => {
          onDragOver?.(event);
          handleFormDragOver(event);
        }}
        onDrop={(event) => {
          onDrop?.(event);
          handleFormDrop(event);
        }}
        onSubmit={handleSubmit}
        {...props}
      >
        <InputGroup className={cn('overflow-hidden', inputGroupClassName)}>{children}</InputGroup>
      </form>
    </>
  );

  return usingProvider ? (
    inner
  ) : (
    <LocalAttachmentsContext.Provider value={contextValue}>{inner}</LocalAttachmentsContext.Provider>
  );
};
