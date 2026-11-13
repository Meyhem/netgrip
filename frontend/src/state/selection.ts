import { useCallback } from "react";
import { createStore, useStore, type StoreApi } from "zustand";

/** The board's one selection (ScreenControlBoard: one selection, three panes). `null` means
 * nothing is selected, and the inspector shows the root. */
interface SelectionState { selectedId: string | null }

const stores = new Map<string, StoreApi<SelectionState>>();

function storeFor(id: string): StoreApi<SelectionState> {
  let store = stores.get(id);
  if (!store) stores.set(id, (store = createStore<SelectionState>(() => ({ selectedId: null }))));
  return store;
}

/** Drop the selection kept for `id` (after deleting it, and between tests). */
export function forgetSelection(id: string): void {
  stores.delete(id);
}

/** The investigation's shared selection: every pane reads and sets the same one. */
export function useSelection(investigationId: string): { selectedId: string | null; select: (id: string | null) => void } {
  const store = storeFor(investigationId);
  const selectedId = useStore(store, (s) => s.selectedId);
  const select = useCallback((id: string | null) => store.setState({ selectedId: id }), [store]);
  return { selectedId, select };
}
