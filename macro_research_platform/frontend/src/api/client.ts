import axios, { AxiosInstance, AxiosError } from 'axios';
import { DashboardData } from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 503) {
          console.error('Data not available. Run pipeline first.');
        } else if (error.response?.status === 500) {
          console.error('Server error:', error.response.data);
        }
        return Promise.reject(error);
      }
    );
  }

  // Dashboard API
  async getDashboardData(): Promise<DashboardData> {
    const response = await this.client.get<DashboardData>('/dashboard');
    return response.data;
  }

  // Regime API
  async getRegimeData() {
    const response = await this.client.get('/regime');
    return response.data;
  }

  // Metrics API
  async getKeyMetrics() {
    const response = await this.client.get('/metrics/key');
    return response.data;
  }

  // Signals API
  async getSignals() {
    const response = await this.client.get('/signals');
    return response.data;
  }

  // Sector Allocation API
  async getSectorAllocation() {
    const response = await this.client.get('/sectors');
    return response.data;
  }

  // Risk Indicators API
  async getRiskIndicators() {
    const response = await this.client.get('/risk');
    return response.data;
  }

  // Advanced Indicators API
  async getAdvancedIndicators() {
    const response = await this.client.get('/advanced');
    return response.data;
  }

  // Business Layer API
  async getBusinessLayer() {
    const response = await this.client.get('/business');
    return response.data;
  }

  // Health check
  async healthCheck(): Promise<{ status: string; mode?: string }> {
    const response = await this.client.get('/health');
    return response.data;
  }

  // Generic POST method
  async post<T = any>(url: string, data: any): Promise<{ data: T }> {
    return this.client.post(url, data);
  }
}

export const api = new ApiClient();
