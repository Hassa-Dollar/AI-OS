export type Plan = "free" | "pro";

export interface Link {
  id: number;
  user_id: string;
  code: string;
  target_url: string;
  created_at: number;
}

export interface Click {
  id: number;
  link_id: number;
  ts: number;
  referrer: string | null;
  ua: string | null;
  ip_hash: string | null;
}

export interface Subscription {
  user_id: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  plan: Plan;
  status: string | null;
  current_period_end: number | null;
}