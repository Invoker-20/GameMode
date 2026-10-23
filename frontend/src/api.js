/**
 * GameMode Lab REST API Client.
 */

const BASE_URL = '';

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const message = errorBody.detail || `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return response.json();
}

export async function fetchStatus() {
  return request('/api/status');
}

export async function toggleMode(enabled) {
  return request('/api/mode', {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
}

export async function fetchProcesses() {
  return request('/api/processes');
}

export async function fetchHistory() {
  return request('/api/history');
}

export async function startBenchmark({ label, repetitions = 5, synthetic_contention = false }) {
  return request('/api/benchmarks', {
    method: 'POST',
    body: JSON.stringify({
      label,
      repetitions: Number(repetitions),
      synthetic_contention: Boolean(synthetic_contention),
    }),
  });
}

export async function fetchBenchmarks() {
  return request('/api/benchmarks');
}

export async function fetchBenchmark(id) {
  return request(`/api/benchmarks/${id}`);
}

export async function compareBenchmarks(idA, idB) {
  return request(`/api/benchmarks/compare?a=${idA}&b=${idB}`);
}
