// Cliente de API do domínio de anti-compartilhamento (registro de incidentes).
import { authFetch } from "@/lib/authApi";

export type IncidentType = "printscreen" | "copy_blocked" | "context_menu_blocked" | "print_blocked";

export const securityApi = {
  reportIncident: (data: { incident_type: IncidentType; page?: string; context?: Record<string, unknown> }) =>
    authFetch<{ detail: string; incident_count_24h: number }>("/security/incident", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
