/**
 * Client-side authentication utilities for managing JWT tokens in localStorage.
 */

const ACCESS_TOKEN_KEY = 'pact_access_token';
const REFRESH_TOKEN_KEY = 'pact_refresh_token';

/**
 * Retrieves the stored JWT access token from localStorage.
 *
 * @returns {string|null} The access token or null if unauthenticated or on SSR.
 */
export function getAccessToken() {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

/**
 * Retrieves the stored JWT refresh token from localStorage.
 *
 * @returns {string|null} The refresh token or null if unavailable.
 */
export function getRefreshToken() {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

/**
 * Stores the JWT access and refresh tokens in localStorage.
 *
 * @param {string} access - The JWT access token.
 * @param {string} [refresh] - The optional JWT refresh token.
 */
export function setTokens(access, refresh) {
  if (typeof window === 'undefined') return;
  if (access) {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
  }
  if (refresh) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  }
}

/**
 * Clears all stored JWT authentication tokens from localStorage.
 */
export function clearTokens() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

/**
 * Checks whether an active access token exists in localStorage.
 *
 * @returns {boolean} True if authenticated, false otherwise.
 */
export function isLoggedIn() {
  if (typeof window === 'undefined') return false;
  return Boolean(localStorage.getItem(ACCESS_TOKEN_KEY));
}

/**
 * Calls the backend refresh endpoint with the stored refresh token to obtain
 * a new access token. If refresh fails (401 or invalid), clears tokens and returns null.
 *
 * @returns {Promise<string|null>} The refreshed access token or null on failure.
 */
export async function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) {
    clearTokens();
    return null;
  }

  const baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

  try {
    const response = await fetch(`${baseURL}/auth/refresh/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh }),
    });

    if (!response.ok) {
      clearTokens();
      return null;
    }

    const data = await response.json();
    if (data.access) {
      setTokens(data.access, data.refresh);
      return data.access;
    }

    clearTokens();
    return null;
  } catch (error) {
    clearTokens();
    return null;
  }
}
