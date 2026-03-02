import { useSyncExternalStore } from 'react';

class TimeStore {
  private now: number = Date.now();
  private listeners: Set<() => void> = new Set();
  private intervalFn: NodeJS.Timeout | null = null;

  private tick = () => {
    this.now = Date.now();
    this.listeners.forEach((listener) => listener());
  };

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    if (this.listeners.size === 1) {
      this.intervalFn = setInterval(this.tick, 10000); // 10s interval
    }
    return () => {
      this.listeners.delete(listener);
      // Clean up interval when no components are listening
      if (this.listeners.size === 0 && this.intervalFn) {
        clearInterval(this.intervalFn);
      }
    };
  };

  getSnapshot = () => this.now;
}

const timeStore = new TimeStore();

export function useGlobalTime(): number {
  return useSyncExternalStore(timeStore.subscribe, timeStore.getSnapshot);
}
