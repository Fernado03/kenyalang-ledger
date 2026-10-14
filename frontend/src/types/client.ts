/**
 * Wire contract for the client-workspace routes (docs/06_schema_api.md §6.3.5).
 * These routes are mounted WITHOUT the /v1 prefix: `GET/POST /api/clients`.
 */

/** `ClientRead`: one client workspace owned by an accountant. */
export interface Client {
  id: string;
  accountant_id: string;
  business_name: string;
  registration_number: string | null;
  sst_number: string | null;
  industry_category: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** Body of `POST /api/clients`; `accountant_id` always comes from the session. */
export interface ClientCreate {
  business_name: string;
  registration_number: string | null;
  sst_number: string | null;
  industry_category: string | null;
}
