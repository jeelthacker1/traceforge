import { create } from "zustand";
type State = {
  tab: string;
  minutes: number;
  service: string;
  search: string;
  setTab: (tab: string) => void;
  setMinutes: (minutes: number) => void;
  setService: (service: string) => void;
  setSearch: (search: string) => void;
};
export const useStore = create<State>((set) => ({
  tab: "Overview",
  minutes: 60,
  service: "",
  search: "",
  setTab: (tab) => set({ tab }),
  setMinutes: (minutes) => set({ minutes }),
  setService: (service) => set({ service }),
  setSearch: (search) => set({ search }),
}));
