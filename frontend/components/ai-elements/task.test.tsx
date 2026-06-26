import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Task, TaskContent, TaskItem, TaskItemFile, TaskTrigger } from './task';

describe('Task', () => {
  it('renders the trigger title + nested item content', () => {
    const { getByText } = render(
      <Task defaultOpen>
        <TaskTrigger title="Refactor" />
        <TaskContent>
          <TaskItem>step one</TaskItem>
        </TaskContent>
      </Task>
    );
    expect(getByText('Refactor')).toBeTruthy();
    expect(getByText('step one')).toBeTruthy();
  });

  it('renders custom trigger children when supplied', () => {
    const { getByText } = render(
      <Task defaultOpen>
        <TaskTrigger title="ignored">
          <span>custom trigger</span>
        </TaskTrigger>
      </Task>
    );
    expect(getByText('custom trigger')).toBeTruthy();
  });
});

describe('TaskItemFile', () => {
  it('renders the file label inside the pill', () => {
    const { getByText } = render(<TaskItemFile>file.tsx</TaskItemFile>);
    expect(getByText('file.tsx')).toBeTruthy();
  });
});
