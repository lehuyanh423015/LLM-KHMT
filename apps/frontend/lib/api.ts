const API_URL = "http://localhost:8000";

export async function sendMessage(message: string, sessionId: string) {
  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!response.ok) {
    throw new Error("Failed to send message to the server");
  }

  return response.json();
}

export async function fetchProfileMemory(sessionId: string) {
  const response = await fetch(`${API_URL}/customer-profile/${sessionId}`);
  if (!response.ok) {
    throw new Error("Failed to fetch profile");
  }
  return response.json();
}

export async function fetchHealth() {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) {
    throw new Error("Failed to fetch health status");
  }
  return response.json();
}

export async function setExperiment(
  enableMemory: boolean,
  enableRecentContext: boolean,
  enableProductContext: boolean
) {
  const response = await fetch(`${API_URL}/config/experiment`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      enable_memory: enableMemory,
      enable_recent_context: enableRecentContext,
      enable_product_context: enableProductContext,
    }),
  });
  if (!response.ok) {
    throw new Error("Failed to change experiment toggles");
  }
  return response.json();
}
