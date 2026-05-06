// Performance-optimized Section Wrapper
// Uses React.memo to prevent unnecessary re-renders

import { memo } from 'react';

interface SectionWrapperProps {
  children: React.ReactNode;
  id: string;
  className?: string;
}

// Memoized section wrapper that only re-renders when props change
export const MemoizedSection = memo(function MemoizedSection({
  children,
  id,
  className = ''
}: SectionWrapperProps) {
  return (
    <div id={id} className={`terminal-section ${className}`}>
      {children}
    </div>
  );
});

// Custom comparison function for sections with complex data
export function createSectionComparator<T>(
  propsToCompare: (keyof T)[]
): (prevProps: T, nextProps: T) => boolean {
  return (prevProps, nextProps) => {
    return propsToCompare.every(key => prevProps[key] === nextProps[key]);
  };
}
