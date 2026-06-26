import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Plan, PlanDescription, PlanHeader, PlanTitle } from './plan';

describe('Plan', () => {
  it('renders the title + description copy', () => {
    const { getByText } = render(
      <Plan defaultOpen>
        <PlanHeader>
          <PlanTitle>Refactor pass</PlanTitle>
          <PlanDescription>Tighten the auth flow.</PlanDescription>
        </PlanHeader>
      </Plan>
    );
    expect(getByText('Refactor pass')).toBeTruthy();
    expect(getByText('Tighten the auth flow.')).toBeTruthy();
  });
});
