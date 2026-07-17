import axios, { type AxiosRequestConfig } from 'axios';
import { API_BASE_URL } from '../utils/constants';
import { attachParsedApiError } from './error';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

type StockPulseRequestConfig = AxiosRequestConfig & {
  handleUnauthorizedLocally?: boolean;
};

/** Keep a recoverable resource 401 in-page instead of forcing navigation. */
export function locallyRecoverableResourceConfig(): StockPulseRequestConfig {
  return { handleUnauthorizedLocally: true };
}

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestConfig = error.config as StockPulseRequestConfig | undefined;
    if (error.response?.status === 401 && !requestConfig?.handleUnauthorizedLocally) {
      const path = window.location.pathname + window.location.search;
      if (!path.startsWith('/login')) {
        const redirect = encodeURIComponent(path);
        window.location.assign(`/login?redirect=${redirect}`);
      }
    }
    attachParsedApiError(error);
    return Promise.reject(error);
  }
);

export default apiClient;
