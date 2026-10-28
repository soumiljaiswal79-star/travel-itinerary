export type TravelStyle = "relaxed" | "balanced" | "packed";
export type StopKind = "attraction" | "dining" | "experience";

export interface User {
  id: string;
  email: string;
}

export interface Session {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

export interface Stop {
  time: string;
  kind: StopKind;
  title: string;
  description: string;
  location: string;
  latitude: number | null;
  longitude: number | null;
  duration_minutes: number;
  estimated_cost: number;
  image_url: string | null;
}

export interface ItineraryDay {
  day_number: number;
  date: string;
  theme: string;
  stops: Stop[];
  accommodation: {
    name: string;
    neighborhood: string;
    nightly_cost: number;
    notes: string;
  };
  transportation: string[];
  estimated_cost: number;
}

export interface Trip {
  id: string;
  user_id: string;
  title: string;
  destination: string;
  start_date: string;
  end_date: string;
  budget: number;
  currency: string;
  interests: string[];
  travel_style: TravelStyle;
  group_size: number;
  total_estimated_cost: number;
  summary: string;
  days: ItineraryDay[];
  role: "owner" | "editor" | "viewer";
  created_at: string | null;
  updated_at: string | null;
}

export interface Member {
  user_id: string;
  role: "editor" | "viewer";
  created_at: string;
  profiles?: { email: string; display_name: string | null };
}

export interface TripForm {
  destination: string;
  start_date: string;
  end_date: string;
  budget: number;
  currency: string;
  interests: string[];
  travel_style: TravelStyle;
  group_size: number;
}

export interface ApiSessionResponse {
  user: User;
  session: Session | null;
}
