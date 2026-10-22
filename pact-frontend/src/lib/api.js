import axios from 'axios';
import { getAccessToken, refreshAccessToken, clearTokens } from './auth';

const baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
});

// Request Interceptor: Attach JWT Bearer token if present
apiClient.interceptors.request.use(
  (config) => {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: Handle 401 Unauthorized with token refresh & retry
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/');

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;
      try {
        const newAccessToken = await refreshAccessToken();
        if (newAccessToken) {
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          return apiClient(originalRequest);
        }
      } catch (refreshErr) {
        // Refresh failed, proceed to logout
      }

      clearTokens();
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
    }

    return Promise.reject(error);
  }
);

/**
 * Extracts a human-readable error message from an Axios error or Django response.
 *
 * @param {Error} error
 * @param {string} fallbackMessage
 * @returns {string}
 */
export function extractErrorMessage(error, fallbackMessage) {
  const data = error.response?.data;
  if (!data) {
    return error.message || fallbackMessage;
  }
  if (typeof data === 'string') {
    return data;
  }
  if (typeof data === 'object') {
    if (data.error) return typeof data.error === 'string' ? data.error : JSON.stringify(data.error);
    if (data.detail) return data.detail;
    if (data.message) return data.message;
    if (data.amount && Array.isArray(data.amount)) return `Amount: ${data.amount.join(', ')}`;
    if (data.payload && Array.isArray(data.payload)) return `Payload: ${data.payload.join(', ')}`;
    const firstKey = Object.keys(data)[0];
    if (firstKey && data[firstKey]) {
      return `${firstKey}: ${Array.isArray(data[firstKey]) ? data[firstKey].join(', ') : data[firstKey]}`;
    }
  }
  return error.message || fallbackMessage;
}

/**
 * Creates a new draft escrow pact and generates a PayPal authorization order.
 *
 * @param {string|number} amount - Escrow funding total in USD.
 * @param {string} [deliverableType="JSON_DATASET"] - Contract deliverable format.
 * @param {string} [qualityRubric=""] - Buyer acceptance guidelines and criteria.
 * @param {number} [confidenceThreshold=0.85] - Required minimum AI confidence score (0.50 - 0.99).
 * @returns {Promise<{ pact: Object, approve_url: string }>}
 */
export async function createPact(
  amount,
  deliverableType = 'JSON_DATASET',
  qualityRubric = '',
  confidenceThreshold = 0.85
) {
  try {
    const response = await apiClient.post('/pacts/create-pact/', {
      amount: parseFloat(amount).toFixed(2),
      currency: 'USD',
      deliverable_type: deliverableType,
      quality_rubric: qualityRubric,
      confidence_threshold: parseFloat(confidenceThreshold).toFixed(2),
    });
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error, 'Failed to create contract'));
  }
}

/**
 * Submits a seller deliverable dataset for asynchronous AI quality and injection verification.
 *
 * @param {string} pactId - The target Pact UUID.
 * @param {Array<Object>} payloadData - The parsed JSON array dataset.
 * @returns {Promise<{ status: string, message: string, pact: Object }>}
 */
export async function submitDeliverable(pactId, payloadData) {
  try {
    const response = await apiClient.post(`/pacts/${pactId}/submit-deliverable/`, {
      payload: payloadData,
    });
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error, 'Failed to submit deliverable'));
  }
}

/**
 * Retrieves the current state and ledger timeline of a specific Pact.
 *
 * @param {string} pactId - The target Pact UUID.
 * @returns {Promise<Object>}
 */
export async function getPact(pactId) {
  try {
    const response = await apiClient.get(`/pacts/${pactId}/`);
    return response.data;
  } catch (error) {
    throw new Error(extractErrorMessage(error, 'Failed to fetch contract data'));
  }
}
